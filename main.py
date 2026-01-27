import sys
import asyncio
import uvicorn
import logging
import os
import threading
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, 
    QHBoxLayout, QSizePolicy, QSplitter, QMessageBox, QSystemTrayIcon
)
from PySide6.QtCore import Signal, Slot, Qt, QProcess
from PySide6.QtCore import QTimer
import qasync

from drivers.factory import create_driver
from api import API
from config.manager import ConfigManager
from ui.windows.settings_window import SettingsWindow
from ui.windows.console_window import ConsoleWindow
from ui.windows.help_window import HelpWindow
from ui.widgets.mini_console import MiniConsole
from ui.widgets.request_queue_preview import RequestQueuePreview
from ui.core.brand import BrandColors
from ui.core.icons import IconUtils, IconType
from ui.niche.update_available_dialog import UpdateAvailableDialog, UpdateAvailableInfo
from ui.niche.update_installed_dialog import UpdateInstalledDialog, UpdateInstalledInfo
from utils.logger import Logger, LogLevel
from utils.update_checker import check_for_updates
from utils.version_file import parse_version_file
import shutil
import time


def _parse_update_cleanup_args(argv: list[str]) -> tuple[list[str], bool, str | None]:
    """
    Parse and remove internal updater cleanup args from argv.

    Supported forms:
      --deleteupdater
      --updaterpath <path>
      --updaterpath=<path>
    """
    remaining: list[str] = []
    delete_updater = False
    updater_path: str | None = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--deleteupdater":
            delete_updater = True
            i += 1
            continue

        if arg == "--updaterpath":
            if i + 1 < len(argv):
                updater_path = argv[i + 1]
                i += 2
                continue
            i += 1
            continue

        if arg.startswith("--updaterpath="):
            updater_path = arg.split("=", 1)[1] or None
            i += 1
            continue

        remaining.append(arg)
        i += 1

    return remaining, delete_updater, updater_path


def _delete_updater_best_effort(cleanup_path: Path) -> None:
    """
    Clean up the temp extraction directory left behind by the updater.
    
    The updater now passes its temp directory path directly (e.g.,
    C:/Users/.../Temp/intenserp-update-extract-xyz/), so we just delete it.
    """
    try:
        p = cleanup_path.expanduser()
        try:
            p = p.resolve()
        except Exception:
            p = p.absolute()
    except Exception:
        return

    if not p.exists():
        return

    # Wait a bit for the updater process to fully exit
    time.sleep(1.0)

    # Try to delete the entire temp directory tree
    for attempt in range(30):  # ~15 seconds of retries
        try:
            shutil.rmtree(p)
            return  # Success!
        except Exception:
            time.sleep(0.5)


def _resolve_resource_path(*parts: str) -> Path:
    """
    Resolve a resource path in both dev and PyInstaller-frozen runs.

    We try, in order:
    - PyInstaller extraction/bundle dir (sys._MEIPASS)
    - Executable directory (where users often place loose data)
    - Source checkout directory (relative to this file)
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / Path(*parts))
        candidates.append(Path(sys.executable).resolve().parent / Path(*parts))

    candidates.append(Path(__file__).resolve().parent / Path(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[-1]


def get_version():
    """Read version from version.json file."""
    version_file = _resolve_resource_path("version.json")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            info = parse_version_file(f.read(), default_version="unknown", default_auto_updateable=True, default_severity=2)
            return info.version.strip() or "unknown"
    except FileNotFoundError:
        return "unknown"


POSTUPDATE_FLAG_FILENAME = "postupdate_notes_url.txt"


def _release_notes_url_for_version(version: str) -> str:
    value = (version or "").strip()
    if value.lower().startswith("v"):
        value = value[1:].strip()
    if not value or value.lower() == "unknown":
        return "https://github.com/LyubomirT/intense-rp-next/releases"
    return f"https://github.com/LyubomirT/intense-rp-next/releases/tag/v{value}"


def _consume_postupdate_installed_info() -> UpdateInstalledInfo | None:
    try:
        if getattr(sys, "frozen", False):
            app_root = Path(sys.executable).resolve().parent
        else:
            app_root = Path(__file__).resolve().parent
    except Exception:
        return None

    flag_path = app_root / POSTUPDATE_FLAG_FILENAME
    try:
        if not flag_path.is_file():
            return None
    except Exception:
        return None

    try:
        version = get_version()
    except Exception:
        version = "unknown"

    try:
        release_notes_url = _release_notes_url_for_version(version)
    except Exception:
        release_notes_url = "https://github.com/LyubomirT/intense-rp-next/releases"

    try:
        flag_path.unlink()
    except Exception:
        pass

    return UpdateInstalledInfo(version=version, release_notes_url=release_notes_url)


class MainWindow(QMainWindow):
    update_available_found = Signal(object)
    DEFAULT_WINDOW_WIDTH = 450
    DEFAULT_WINDOW_HEIGHT = 500

    def __init__(self):
        super().__init__()
        version = get_version()
        self.setWindowTitle(f"IntenseRP Next v{version}")
        self.resize(self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG}; color: {BrandColors.TEXT_PRIMARY};")

        self.config_manager = ConfigManager()
        self._queue_preview_min_width = 300
        self._queue_preview_handle_width = 12

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        outer_layout = QHBoxLayout(self.central_widget)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        outer_layout.setSpacing(0)
        self._outer_layout = outer_layout

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(0)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {BrandColors.WINDOW_BG}; }}")
        outer_layout.addWidget(self.splitter)

        self.main_panel = QWidget()
        self.main_panel.setStyleSheet("background-color: transparent;")
        self.main_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.layout = QVBoxLayout(self.main_panel)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(12)

        self.queue_preview = RequestQueuePreview(self.central_widget)
        self.queue_preview.setVisible(False)
        self.queue_preview.setMinimumWidth(0)
        self.queue_preview.setMaximumWidth(0)
        self.queue_preview.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self.splitter.addWidget(self.main_panel)
        self.splitter.setCollapsible(0, False)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        # 1. Title Area
        title_label = QLabel(f"Welcome to IntenseRP Next (v{version})!")
        title_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_TITLE};
            font-weight: bold;
            color: {BrandColors.TEXT_PRIMARY};
        """)
        title_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(title_label)

        # 1.5. Readiness Status
        self.status_label = QLabel("● Ready")
        self.status_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: bold;
            color: {BrandColors.SUCCESS};
            padding: 8px;
            background-color: {BrandColors.SIDEBAR_BG};
            border-radius: 6px;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)

        # 2. Mini-Console Area
        self.mini_console = MiniConsole()
        self.mini_console.setMinimumHeight(250)
        self.mini_console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.mini_console)

        # 3. Control Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.start_button = QPushButton("Start")
        self.start_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.ACCENT};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 12px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QPushButton:hover {{
                background-color: #4a80e0;
            }}
            QPushButton:disabled {{
                background-color: {BrandColors.TEXT_DISABLED};
            }}
        """)
        IconUtils.apply_icon(self.start_button, IconType.START, BrandColors.TEXT_PRIMARY)
        self.start_button.setCursor(Qt.PointingHandCursor)
        self.start_button.clicked.connect(self.on_start_clicked)
        button_layout.addWidget(self.start_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 12px 20px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
        """)
        IconUtils.apply_icon(self.settings_button, IconType.SETTINGS, BrandColors.TEXT_PRIMARY)
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(self.open_settings)
        button_layout.addWidget(self.settings_button)
        
        self.layout.addLayout(button_layout)

        self.help_button = QPushButton("Help")
        self.help_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 12px 20px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
        """)
        IconUtils.apply_icon(self.help_button, IconType.HELP, BrandColors.TEXT_PRIMARY)
        self.help_button.setCursor(Qt.PointingHandCursor)
        self.help_button.clicked.connect(self.open_help)
        self.layout.addWidget(self.help_button)

        self._queue_preview_enabled = False
        self._queue_preview_last_width = 360
        self._queue_preview_refresh_inflight = False
        self._queue_preview_last_rendered = None
        self._queue_preview_timer = QTimer()
        self._queue_preview_timer.setInterval(500)
        self._queue_preview_timer.timeout.connect(self._schedule_queue_preview_refresh)

        self.driver = None
        self.api = None
        self.server = None
        self._stop_task: asyncio.Task | None = None
        self._shutdown_task: asyncio.Task | None = None
        self.settings_window = None
        self.console_window = None
        self.help_window = None
        self._main_logging_enabled = True
        
        # Initialize logging based on settings
        self._setup_logging()
        
        # Always set the log callback for the mini-console
        Logger.set_console_callback(self._on_log_message)
        self.update_available_found.connect(self._show_update_available_dialog)

        self._tray_icon = None
        try:
            if QSystemTrayIcon.isSystemTrayAvailable():
                tray_icon = QSystemTrayIcon(self)
                icon = self.windowIcon() if not self.windowIcon().isNull() else QApplication.windowIcon()
                if not icon.isNull():
                    tray_icon.setIcon(icon)
                tray_icon.setToolTip(self.windowTitle())
                tray_icon.show()
                self._tray_icon = tray_icon
        except Exception:
            self._tray_icon = None

        self._post_update_info = _consume_postupdate_installed_info()
        self._maybe_show_update_installed_dialog()

        self._maybe_check_for_updates_on_startup()
        self._apply_queue_preview_setting(force=True)

    def _cleanup_tray_icon(self) -> None:
        tray_icon = getattr(self, "_tray_icon", None)
        if not tray_icon:
            return

        try:
            tray_icon.hide()
        except Exception:
            pass

        try:
            tray_icon.setVisible(False)
        except Exception:
            pass

        try:
            tray_icon.deleteLater()
        except Exception:
            pass

        self._tray_icon = None

    def _request_application_quit(self, force_after_s: float = 8.0) -> None:
        """
        Best-effort request to quit both the Qt app and the qasync/asyncio loop.

        Some shutdown paths can leave the window closed but the process still alive;
        this makes quitting more deterministic and includes a last-resort forced exit.
        """
        import os
        import threading

        def _force_exit() -> None:
            try:
                os._exit(0)
            except Exception:
                return

        # Last-resort: hard-exit if we still haven't quit after a grace period
        try:
            timer = threading.Timer(float(force_after_s), _force_exit)
            timer.daemon = True
            timer.start()
        except Exception:
            pass

        try:
            loop = asyncio.get_event_loop()
            loop.call_soon(loop.stop)
        except Exception:
            pass

        try:
            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception:
            pass

    def _notify_user(self, title: str, message: str, level: str = "info") -> None:
        title = str(title or "Notification")
        message = str(message or "")
        level_norm = str(level or "info").strip().lower()

        is_focused = bool(self.isVisible() and self.isActiveWindow())
        if is_focused:
            dialog = QMessageBox(self)
            if level_norm in {"warn", "warning"}:
                dialog.setIcon(QMessageBox.Warning)
            elif level_norm in {"err", "error", "critical"}:
                dialog.setIcon(QMessageBox.Critical)
            else:
                dialog.setIcon(QMessageBox.Information)
            dialog.setWindowTitle(title)
            dialog.setText(message)
            dialog.setStandardButtons(QMessageBox.Ok)
            dialog.open()
            return

        tray_icon = getattr(self, "_tray_icon", None)
        if tray_icon and tray_icon.isVisible():
            icon = QSystemTrayIcon.Information
            if level_norm in {"warn", "warning"}:
                icon = QSystemTrayIcon.Warning
            elif level_norm in {"err", "error", "critical"}:
                icon = QSystemTrayIcon.Critical

            try:
                tray_icon.showMessage(title, message, icon)
                return
            except Exception:
                pass

        Logger.warning(f"{title}: {message}")

    def _maybe_show_update_installed_dialog(self) -> None:
        info = getattr(self, "_post_update_info", None)
        if info is None:
            return

        def show() -> None:
            if getattr(self, "_post_update_dialog_open", False):
                return

            if not self.isVisible():
                QTimer.singleShot(50, show)
                return

            self._post_update_dialog_open = True
            try:
                dialog = UpdateInstalledDialog(info, parent=self)
                dialog.exec()
            finally:
                self._post_update_dialog_open = False
                self._post_update_info = None

        QTimer.singleShot(0, show)

    @Slot(object)
    def _show_update_available_dialog(self, info: UpdateAvailableInfo):
        if getattr(self, "_update_dialog_open", False):
            return

        def show():
            if getattr(self, "_update_dialog_open", False):
                return
            if not self.isVisible():
                return

            self._update_dialog_open = True
            try:
                dialog = UpdateAvailableDialog(
                    info,
                    parent=self,
                )
                dialog.exec()
            finally:
                self._update_dialog_open = False

        # make sure the dialog is shown from the running UI event loop to avoid
        # early-startup edge cases (startup update checks complete very quickly)
        QTimer.singleShot(0, show)

    def _maybe_check_for_updates_on_startup(self):
        try:
            enabled = bool(
                self.config_manager.get_setting(
                    "application_settings", "check_for_updates_on_startup"
                )
            )
        except Exception:
            enabled = False

        if not enabled:
            return

        def worker():
            result = check_for_updates()
            if result.error:
                Logger.warning(f"Update check failed: {result.error}")
                return

            if result.update_available:
                Logger.warning(
                    f"Update available: {result.local_version} -> {result.remote_version}"
                )
                if result.remote_version is not None:
                    self.update_available_found.emit(
                        UpdateAvailableInfo(
                            local_version=str(result.local_version or "unknown"),
                            remote_version=str(result.remote_version or "unknown"),
                            remote_auto_updateable=result.remote_auto_updateable,
                            remote_severity=result.remote_severity,
                        )
                    )
                return

            Logger.info(f"Up to date (v{result.local_version}).")

        threading.Thread(target=worker, daemon=True).start()

    def _setup_logging(self):
        """Setup logging (console and file) based on settings."""
        # Console window (separate from mini-console)
        enable_console = self.config_manager.get_setting("console_settings", "enable_console")

        # Routing options (only user-toggleable when console is enabled)
        log_to_main = self.config_manager.get_effective_setting("console_settings", "log_to_main")
        log_to_stdout = self.config_manager.get_effective_setting("console_settings", "log_to_stdout")

        Logger.set_stdout_enabled(bool(log_to_stdout))
        self._main_logging_enabled = bool(log_to_main)
        self.mini_console.set_main_logging_enabled(self._main_logging_enabled)
        if enable_console:
            self._show_console()
        else:
            self._hide_console()
            
        # File Logging
        enable_files = self.config_manager.get_setting("logfiles", "enable_logfiles")
        log_dir = self.config_manager.get_setting("logfiles", "log_dir")
        max_files = self.config_manager.get_setting("logfiles", "max_files")
        max_size_val = self.config_manager.get_setting("logfiles", "size_val")
        size_unit = self.config_manager.get_setting("logfiles", "size_unit")
        
        # Defaults
        if log_dir is None: log_dir = "logs"
        if max_files is None: max_files = 5
        if max_size_val is None: max_size_val = 10
        if size_unit is None: size_unit = "MB"
        
        Logger.configure_file_logging(bool(enable_files), str(log_dir), int(max_files) if max_files is not None else 5, int(max_size_val) if max_size_val is not None else 10, str(size_unit))
    
    def _show_console(self):
        """Show the console window."""
        if not self.console_window:
            self.console_window = ConsoleWindow(self.config_manager)
        
        self.console_window.show()
        Logger.info("Console initialized.")
    
    def _hide_console(self):
        """Hide the console window."""
        if self.console_window:
            self.console_window.force_close()
            self.console_window = None
    
    def _on_log_message(self, level: LogLevel, message: str):
        """Callback for logger to send messages to console."""
        if self.console_window:
            self.console_window.append_log(level.value, message)
        
        # Also route to mini-console when enabled (DEBUG is filtered inside)
        if self._main_logging_enabled:
            self.mini_console.add_log(level, message)
    
    def _update_status(self, text: str, status_type: str = "info"):
        """Update the status label with appropriate styling."""
        color_map = {
            "ready": BrandColors.SUCCESS,
            "running": BrandColors.ACCENT,
            "warning": BrandColors.WARNING,
            "error": BrandColors.DANGER,
            "info": BrandColors.TEXT_SECONDARY,
        }
        color = color_map.get(status_type, BrandColors.TEXT_SECONDARY)
        
        # Add status indicator dot
        dot = "●" if status_type in ["ready", "running"] else "○"
        
        self.status_label.setText(f"{dot} {text}")
        self.status_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: bold;
            color: {color};
            padding: 8px;
            background-color: {BrandColors.SIDEBAR_BG};
            border-radius: 6px;
        """)

    def _on_splitter_moved(self, pos: int, index: int):
        if not getattr(self, "queue_preview", None):
            return
        if not self.queue_preview.isVisible():
            return

        try:
            sizes = self.splitter.sizes()
            if len(sizes) >= 2:
                self._queue_preview_last_width = max(self._queue_preview_min_width, int(sizes[0]))
        except Exception:
            pass

    def _rebuild_splitter(self, include_queue_preview: bool) -> None:
        outer_layout = getattr(self, "_outer_layout", None)
        if outer_layout is None:
            return

        old_splitter = getattr(self, "splitter", None)
        if old_splitter is not None:
            # Detach widgets we keep so deleting the splitter does not delete them
            for widget in (getattr(self, "main_panel", None), getattr(self, "queue_preview", None)):
                if widget is not None and widget.parent() is old_splitter:
                    widget.setParent(self.central_widget)

            outer_layout.removeWidget(old_splitter)
            old_splitter.setParent(None)
            old_splitter.deleteLater()

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(self._queue_preview_handle_width if include_queue_preview else 0)
        splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {BrandColors.WINDOW_BG}; }}")
        splitter.splitterMoved.connect(self._on_splitter_moved)
        outer_layout.addWidget(splitter)
        self.splitter = splitter

        if include_queue_preview:
            splitter.addWidget(self.queue_preview)
            splitter.addWidget(self.main_panel)
            splitter.setCollapsible(0, False)
            splitter.setCollapsible(1, False)
            return

        splitter.addWidget(self.main_panel)
        splitter.setCollapsible(0, False)

    def _apply_queue_preview_setting(self, force: bool = False):
        enabled = bool(self.config_manager.get_setting("system_settings", "show_request_queue_preview"))

        if (not force) and enabled == getattr(self, "_queue_preview_enabled", False):
            return

        was_visible = bool(getattr(self, "queue_preview", None) and self.queue_preview.isVisible())
        self._queue_preview_enabled = enabled

        if enabled:
            desired_width = max(int(getattr(self, "_queue_preview_last_width", 360) or 360), self._queue_preview_min_width)
            if not was_visible:
                self.resize(self.width() + desired_width, self.height())

            if self.splitter.indexOf(self.queue_preview) == -1:
                self.splitter.insertWidget(0, self.queue_preview)
                self.splitter.setCollapsible(0, False)
                self.splitter.setCollapsible(1, False)

            self.queue_preview.setMaximumWidth(16777215)
            self.queue_preview.setMinimumWidth(self._queue_preview_min_width)
            self.queue_preview.setVisible(True)
            self.splitter.setHandleWidth(self._queue_preview_handle_width)
            self._queue_preview_last_rendered = None
            self._queue_preview_timer.start()
            self._schedule_queue_preview_refresh()

            def apply_sizes():
                if not self.queue_preview.isVisible():
                    return
                total = sum(self.splitter.sizes())
                main_width = max(0, total - desired_width)
                self.splitter.setSizes([desired_width, main_width])

            QTimer.singleShot(0, apply_sizes)
            return

        # Disabled
        try:
            sizes = self.splitter.sizes()
            if self.queue_preview.isVisible() and len(sizes) >= 2:
                self._queue_preview_last_width = max(self._queue_preview_min_width, int(sizes[0]))
        except Exception:
            pass

        self.queue_preview.setVisible(False)
        self.queue_preview.setMinimumWidth(0)
        self.queue_preview.setMaximumWidth(0)
        self._queue_preview_timer.stop()
        self._queue_preview_last_rendered = None

        # Rebuild the splitter without the preview widget to avoid stale size/minimum constraints
        # keeping the main window wide after the panel is disabled
        self._rebuild_splitter(include_queue_preview=False)

        # Clear any layout-driven minimums that may have been raised while the preview was present
        try:
            self.central_widget.setMinimumSize(0, 0)
            self.splitter.setMinimumSize(0, 0)
        except Exception:
            pass

        QTimer.singleShot(
            0,
            lambda: self.resize(self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT),
        )

    def _schedule_queue_preview_refresh(self):
        if not getattr(self, "_queue_preview_enabled", False):
            return
        if not getattr(self, "queue_preview", None) or not self.queue_preview.isVisible():
            return
        if getattr(self, "_queue_preview_refresh_inflight", False):
            return

        self._queue_preview_refresh_inflight = True
        asyncio.create_task(self._refresh_queue_preview())

    async def _refresh_queue_preview(self):
        try:
            if not getattr(self, "_queue_preview_enabled", False):
                return
            if not getattr(self, "queue_preview", None) or not self.queue_preview.isVisible():
                return

            entries = []
            api = getattr(self, "api", None)
            if api and getattr(api, "request_queue", None):
                current = getattr(api, "current_entry", None)
                if current:
                    entries.append(("processing", current))

                queued = await api.request_queue.snapshot()
                for entry in queued:
                    status = "cancelled" if entry.abort_event.is_set() else "pending"
                    entries.append((status, entry))

            rendered = []
            for idx, (status, entry) in enumerate(entries, start=1):
                req = getattr(entry, "request", None)
                try:
                    msg_count = len(getattr(req, "messages", []) or [])
                except Exception:
                    msg_count = 0

                rendered.append(
                    {
                        "position": idx,
                        "id": getattr(entry, "id", ""),
                        "queued_at": getattr(entry, "queued_at", 0.0),
                        "status": status,
                        "message_count": msg_count,
                        "api_key_name": getattr(entry, "api_key_name", None),
                        "model": getattr(req, "model", "") if req else "",
                        "stream": bool(getattr(req, "stream", False)) if req else False,
                    }
                )

            if getattr(self, "_queue_preview_last_rendered", None) == rendered:
                return
            self._queue_preview_last_rendered = rendered
            self.queue_preview.set_requests(rendered)
        finally:
            self._queue_preview_refresh_inflight = False

    def open_settings(self):
        if not self.settings_window:
            # Pass None as parent to make it a top-level window with its own taskbar icon
            self.settings_window = SettingsWindow(self.config_manager, None)
            self.settings_window.settings_saved.connect(self.on_settings_saved)
            self.settings_window.restart_requested.connect(self.on_restart_requested)
        elif not self.settings_window.isVisible():
            self.settings_window.refresh_from_config()
        self.settings_window.show()
        self.settings_window.activateWindow() # Bring to front

    def open_help(self):
        if not self.help_window:
            self.help_window = HelpWindow(self.config_manager, None)
            self.help_window.settings_reloaded.connect(self.on_settings_reloaded)
        self.help_window.show()
        self.help_window.activateWindow()

    def on_settings_saved(self):
        Logger.info("Settings saved.")
        # Handle logging toggle
        self._setup_logging()
        self._apply_queue_preview_setting()
        
        # Update console settings if it exists
        # Rule 43 of The Internet: If it exists, then it exists
        if self.console_window:
            self.console_window.apply_settings()
            
        # If driver is running, it will pick up changes on next generation
        # All thanks to the config manager being dynamic

    def on_settings_reloaded(self):
        Logger.info("Settings reloaded.")
        self._setup_logging()

        if self.console_window:
            self.console_window.apply_settings()

        if self.settings_window and self.settings_window.isVisible():
            # Importing settings is effectively an external change; force refresh
            self.settings_window.refresh_from_config(force=True)

    def on_restart_requested(self):
        asyncio.create_task(self._restart_application())

    async def _restart_application(self):
        Logger.info("Restarting application...")
        try:
            await asyncio.wait_for(self.stop_services(), timeout=10)
        except asyncio.TimeoutError:
            Logger.warning("Restart cleanup timed out; forcing restart.")
        except Exception as e:
            Logger.error(f"Error during restart cleanup: {e}")

        try:
            # Prefer replacing the current process to avoid orphaned/lingering windows.
            if getattr(sys, "frozen", False):
                argv = [sys.executable] + sys.argv[1:]
            else:
                script = Path(sys.argv[0]).expanduser()
                try:
                    script = script.resolve()
                except Exception:
                    script = script.absolute()
                argv = [sys.executable, str(script)] + sys.argv[1:]

            os.execv(argv[0], argv)
        except Exception as e:
            Logger.error(f"execv restart failed: {e}")

        # Fallback: spawn a detached process and hard-exit this one.
        try:
            if getattr(sys, "frozen", False):
                program = sys.executable
                args = sys.argv[1:]
            else:
                program = sys.executable
                args = [str(Path(sys.argv[0]).expanduser().resolve())] + sys.argv[1:]

            QProcess.startDetached(program, args)
        finally:
            os._exit(0)

    @Slot()
    def on_start_clicked(self):
        if self.start_button.text() == "Start":
            self.start_button.setEnabled(False)
            self._update_status("Starting...", "info")
            # Schedule the start_services coroutine
            asyncio.create_task(self.start_services())
        else:
            self.start_button.setEnabled(False)
            self._update_status("Stopping...", "info")
            asyncio.create_task(self.stop_services())

    async def start_services(self):
        if (
            getattr(self, "api", None) is not None
            or getattr(self, "server", None) is not None
            or getattr(self, "server_task", None) is not None
            or getattr(self, "driver", None) is not None
        ):
            Logger.warning("Start requested while services still exist; cleaning up first.")
            try:
                await self.stop_services(update_ui=False)
            except Exception as e:
                Logger.error(f"Pre-start cleanup failed: {e}")

        try:
            # Pass config manager to driver
            self.driver = create_driver(self.config_manager)
            self.driver.notify_user_callback = self._notify_user
            self.driver.on_crash_callback = self.on_browser_crashed

            # Configure Uvicorn
            port_setting = self.config_manager.get_setting("network_settings", "port")
            try:
                port = int(port_setting) if port_setting else 7777
            except (TypeError, ValueError):
                port = 7777

            available_on_lan = self.config_manager.get_setting("network_settings", "available_on_lan")
            host = "0.0.0.0" if available_on_lan else "127.0.0.1"

            # Silence uvicorn loggers to avoid noisy console output.
            for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
                logger = logging.getLogger(logger_name)
                logger.handlers = [logging.NullHandler()]
                logger.setLevel(logging.CRITICAL)
                logger.propagate = False
                logger.disabled = True
            
            # Start Driver (with status callback for browser installation/launch updates)
            self._update_status("Launching Browser...", "info")
            await self.driver.start(status_callback=lambda msg: self._update_status(msg, "info"))

            # Optional provider UI language check (provider-specific enforcement; safe to no-op)
            # If the user cancels, stop startup gracefully
            if not await self._ensure_driver_ui_language_is_compatible():
                await self.stop_services()
                return

            self.api = API(self.driver)

            # Configure Uvicorn with log_config=None to avoid "Unable to configure formatter 'default'" error
            config = uvicorn.Config(
                app=self.api.app,
                host=host,
                port=port,
                log_level="critical",
                log_config=None,
                access_log=False,
            )

            self.server = uvicorn.Server(config)
            
            # Start API Server
            self._update_status("Starting API Server...", "info")
            # We run server.serve() as a task because it blocks
            self.server_task = asyncio.create_task(self.server.serve())
            
            self._update_status(f"Running (Port {port})", "running")
            self.start_button.setText("Stop")
            IconUtils.apply_icon(self.start_button, IconType.STOP, BrandColors.TEXT_PRIMARY)
            self.start_button.setEnabled(True)
            
        except Exception as e:
            self._update_status(f"Error: {e}", "error")
            Logger.error(f"Error starting services: {e}")
            try:
                await self.stop_services(update_ui=False)
            except Exception as cleanup_error:
                Logger.error(f"Error cleaning up after failed start: {cleanup_error}")
            self.start_button.setText("Start")
            IconUtils.apply_icon(self.start_button, IconType.START, BrandColors.TEXT_PRIMARY)
            self.start_button.setEnabled(True)

    async def _ensure_driver_ui_language_is_compatible(self) -> bool:
        driver = getattr(self, "driver", None)
        if not driver:
            return True

        async def _exec_message_box(dialog: QMessageBox) -> int:
            loop = asyncio.get_running_loop()
            future: asyncio.Future[int] = loop.create_future()

            def on_button_clicked(button) -> None:
                if future.done():
                    return
                try:
                    future.set_result(int(dialog.standardButton(button)))
                except Exception:
                    future.set_result(int(QMessageBox.Cancel))

            def on_finished(_result: int) -> None:
                if future.done():
                    return
                future.set_result(int(QMessageBox.Cancel))

            dialog.buttonClicked.connect(on_button_clicked)
            dialog.finished.connect(on_finished)
            dialog.open()

            try:
                return await future
            finally:
                try:
                    dialog.buttonClicked.disconnect(on_button_clicked)
                except Exception:
                    pass
                try:
                    dialog.finished.disconnect(on_finished)
                except Exception:
                    pass
                dialog.deleteLater()

        provider_label = getattr(driver, "provider_label", None) or "Provider"
        required_label = getattr(driver, "required_ui_language_label", None) or "English (en-US)"

        while True:
            try:
                is_ok = await driver.check_ui_language()
            except Exception as e:
                Logger.warning(f"Failed to detect {provider_label} UI language: {e}")
                return True

            if is_ok:
                return True

            detected = getattr(driver, "last_document_lang", None) or "<unset>"
            self._update_status(f"{provider_label} UI language must be {required_label}", "warning")

            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle(f"{provider_label} UI Language")
            dialog.setText(f"{provider_label} UI language is not {required_label}.")
            dialog.setInformativeText(
                f"Detected <html lang>: {detected}\n\n"
                f"IntenseRP currently requires the {provider_label} UI language to be {required_label}. "
                "Some automation relies on expected UI text, and an unsupported interface language can make it break.\n\n"
                f"Please change the language to {required_label} in the {provider_label} browser window, then click Retry."
            )
            dialog.setStandardButtons(QMessageBox.Retry | QMessageBox.Cancel)
            dialog.setDefaultButton(QMessageBox.Retry)

            choice = await _exec_message_box(dialog)
            if choice == int(QMessageBox.Cancel):
                Logger.warning(f"Start cancelled: {provider_label} UI language is not {required_label}.")
                return False

            # Give the page a moment in case changing language triggers a reload
            await asyncio.sleep(0.25)

    async def stop_services(self, update_ui: bool = True):
        existing = getattr(self, "_stop_task", None)
        if existing and (not existing.done()):
            await existing
            return

        async def _stop_impl() -> None:
            Logger.info("Stopping services...")
            had_warnings = False

            api = getattr(self, "api", None)
            if api is not None:
                try:
                    await asyncio.wait_for(api.stop(), timeout=5.0)
                except asyncio.TimeoutError:
                    had_warnings = True
                    Logger.warning("Timeout while stopping API worker.")
                except asyncio.CancelledError:
                    had_warnings = True
                    Logger.warning("API stop cancelled.")
                except Exception as e:
                    had_warnings = True
                    Logger.error(f"Error stopping API worker: {e}")
                finally:
                    self.api = None

            server = getattr(self, "server", None)
            server_task = getattr(self, "server_task", None)
            if server is not None:
                try:
                    server.should_exit = True
                except Exception:
                    pass

            if server_task is not None:
                try:
                    await asyncio.wait_for(server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    had_warnings = True
                    Logger.warning("Timeout while stopping API server; cancelling server task.")
                    try:
                        server_task.cancel()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(server_task, timeout=2.0)
                    except asyncio.TimeoutError:
                        Logger.warning("Server task did not cancel in time.")
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        Logger.debug(f"Error while cancelling server task: {e}")
                except asyncio.CancelledError:
                    had_warnings = True
                    Logger.warning("API server stop cancelled.")
                except Exception as e:
                    had_warnings = True
                    Logger.error(f"Error stopping API server: {e}")
                finally:
                    self.server_task = None

            self.server = None

            driver = getattr(self, "driver", None)
            if driver is not None:
                try:
                    await asyncio.wait_for(driver.close(), timeout=20.0)
                except asyncio.TimeoutError:
                    had_warnings = True
                    Logger.warning("Timeout while closing browser driver.")
                except asyncio.CancelledError:
                    had_warnings = True
                    Logger.warning("Driver close cancelled.")
                except Exception as e:
                    had_warnings = True
                    Logger.error(f"Error closing driver: {e}")
                finally:
                    self.driver = None

            if update_ui:
                self._update_status("Stopped", "ready")
                self.start_button.setText("Start")
                IconUtils.apply_icon(self.start_button, IconType.START, BrandColors.TEXT_PRIMARY)
                self.start_button.setEnabled(True)
            if had_warnings:
                Logger.warning("Services stopped with warnings.")
            else:
                Logger.success("Services stopped.")

        self._stop_task = asyncio.create_task(_stop_impl())
        try:
            await self._stop_task
        finally:
            self._stop_task = None

    async def on_browser_crashed(self):
        """
        Callback for when the browser crashes or is closed manually.
        """
        Logger.warning("Browser crash callback received.")
        self._update_status("Browser Closed/Crashed", "warning")
        
        # We need to clean up all services including playwright
        try:
            api = getattr(self, "api", None)
            if api is not None:
                try:
                    await asyncio.wait_for(api.stop(), timeout=5.0)
                except asyncio.TimeoutError:
                    Logger.warning("Timeout while stopping API worker after crash.")
                except asyncio.CancelledError:
                    Logger.warning("API stop cancelled after crash.")
                except Exception as e:
                    Logger.error(f"Error stopping API worker after crash: {e}")
                finally:
                    self.api = None

            server = getattr(self, "server", None)
            server_task = getattr(self, "server_task", None)
            if server is not None:
                try:
                    server.should_exit = True
                except Exception:
                    pass

            if server_task is not None:
                try:
                    await asyncio.wait_for(server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    Logger.warning("Timeout while stopping API server after crash; cancelling server task.")
                    try:
                        server_task.cancel()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(server_task, timeout=2.0)
                    except asyncio.TimeoutError:
                        Logger.warning("Server task did not cancel in time after crash.")
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        Logger.debug(f"Error while cancelling server task after crash: {e}")
                except asyncio.CancelledError:
                    Logger.warning("API server stop cancelled after crash.")
                except Exception as e:
                    Logger.error(f"Error stopping API server after crash: {e}")
                finally:
                    self.server_task = None

            self.server = None
            
            # The driver's close() method handles None checks for context/browser, theoretically that is enough
            if self.driver:
                try:
                    await asyncio.wait_for(self.driver.close(), timeout=20.0)
                except asyncio.TimeoutError:
                    Logger.warning("Timeout while closing driver after crash.")
                except asyncio.CancelledError:
                    Logger.warning("Driver close cancelled after crash.")
                except Exception as e:
                    Logger.error(f"Error closing driver after crash: {e}")
                finally:
                    self.driver = None
            
            # Reset UI
            self.start_button.setText("Start")
            IconUtils.apply_icon(self.start_button, IconType.START, BrandColors.TEXT_PRIMARY)
            self.start_button.setEnabled(True)
            
        except Exception as e:
            Logger.error(f"Error handling crash cleanup: {e}")
            self._update_status(f"Error: {e}", "error")
            self.start_button.setEnabled(True)

    def closeEvent(self, event):
        # Cleanup on close
        Logger.info("Window closing, shutting down...")
        # qasync loop runs until the window closes usually, but we need to await the cleanup.
        
        # If the settings window is open, close it too. If the user cancels the
        # "unsaved changes" prompt, abort quitting the app.
        if self.settings_window and self.settings_window.isVisible():
            if not self.settings_window.close():
                event.ignore()
                return
        
        status_text = self.status_label.text()
        if any(state in status_text for state in ["Stopped", "Ready", "Browser Closed/Crashed"]):
            # Close console window if open
            if self.console_window:
                self.console_window.force_close()
                self.console_window = None

            self._cleanup_tray_icon()
            self._request_application_quit()
            event.accept()
            return

        shutdown_task = getattr(self, "_shutdown_task", None)
        if shutdown_task and (not shutdown_task.done()):
            event.ignore()
            return

        event.ignore()
        self._update_status("Shutting down...", "info")
        
        async def cleanup_and_close():
            await self.stop_services()
            # Now we can close
            # We need to call close again, but bypass this check
            # We can reset the status label
            self._update_status("Stopped", "ready")
            
            # Close console window if open
            if self.console_window:
                self.console_window.force_close()
                self.console_window = None
            
            # If the settings window got opened during shutdown, try to close it.
            if self.settings_window and self.settings_window.isVisible():
                if not self.settings_window.close():
                    return

            self.close()
            
        self._shutdown_task = asyncio.create_task(cleanup_and_close())

def main():
    import os
    import signal
    # If frozen, force Playwright/Patchright to use the global cache directory
    # instead of looking for bundled browsers in the internal _MEIPASS/package directories.
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            # Windows: %LOCALAPPDATA%\ms-playwright
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                global_path = os.path.join(local_app_data, "ms-playwright")
                if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = global_path
                if "PATCHRIGHT_BROWSERS_PATH" not in os.environ:
                    os.environ["PATCHRIGHT_BROWSERS_PATH"] = global_path
        else:
            # Linux/macOS: ~/.cache/ms-playwright
            home = Path.home()
            global_path = str(home / ".cache" / "ms-playwright")
            if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = global_path
            if "PATCHRIGHT_BROWSERS_PATH" not in os.environ:
                os.environ["PATCHRIGHT_BROWSERS_PATH"] = global_path

    # Handle module execution request (e.g. for patchright subprocesses in frozen app)
    if len(sys.argv) > 2 and sys.argv[1] == "-m":
        import runpy
        # Remove exe and -m, keeping module name and args
        # argv becomes ['module_name', 'arg1', ...]
        sys.argv = sys.argv[2:]
        module_name = sys.argv[0]
        try:
            # We must use alter_sys=True so the module sees the correct argv
            runpy.run_module(module_name, run_name="__main__", alter_sys=True)
            sys.exit(0)
        except SystemExit:
            raise
        except Exception as e:
            print(f"Failed to run module {module_name}: {e}")
            sys.exit(1)

    remaining_args, delete_updater, updater_path = _parse_update_cleanup_args(sys.argv[1:])
    sys.argv = [sys.argv[0]] + remaining_args

    app = QApplication(sys.argv)

    from ui.core.app_icon import get_app_icon
    from PySide6.QtWidgets import QStyleFactory

    # Force a consistent style between running-from-source and packaged(PyInstaller) builds. 
    # Style availability can differ when plugins aren't bundled the same way.
    available_styles = {name.lower(): name for name in QStyleFactory.keys()}
    for preferred in ("fusion", "windowsvista", "windows"):
        style_name = available_styles.get(preferred.lower())
        if style_name:
            app.setStyle(style_name)
            break

    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    
    # Load Fonts
    from PySide6.QtGui import QFontDatabase, QFont
    import os
    
    font_dir = _resolve_resource_path("ui", "fonts")
    if font_dir.exists():
        for filename in os.listdir(font_dir):
            if filename.endswith(".ttf"):
                QFontDatabase.addApplicationFont(str(font_dir / filename))
    
    # Set Global Font
    font = QFont(BrandColors.FONT_FAMILY)
    app.setFont(font)
    
    # Enforce Dark Mode Palette (or try to)
    app.setStyleSheet(f"""
        QWidget {{
            font-family: '{BrandColors.FONT_FAMILY}';
            background-color: {BrandColors.WINDOW_BG};
            color: {BrandColors.TEXT_PRIMARY};
        }}
    """)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    def _request_quit() -> None:
        try:
            if window.isVisible():
                window.close()
                return
        except Exception:
            pass

        try:
            app.quit()
        except Exception:
            pass

    try:
        app.aboutToQuit.connect(window._cleanup_tray_icon)
    except Exception:
        pass

    def _sigint_handler(_signum, _frame) -> None:
        try:
            QTimer.singleShot(0, _request_quit)
        except Exception:
            try:
                app.quit()
            except Exception:
                pass

    try:
        signal.signal(signal.SIGINT, _sigint_handler)
    except Exception:
        pass

    if delete_updater and updater_path:
        try:
            target = Path(updater_path)

            def worker() -> None:
                _delete_updater_best_effort(target)

            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            pass

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
