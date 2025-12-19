import sys
import asyncio
import uvicorn
import logging
import os
import threading
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, 
    QHBoxLayout, QSizePolicy
)
from PySide6.QtCore import Signal, Slot, Qt, QProcess
from PySide6.QtCore import QTimer
import qasync

from deepseek_driver import DeepSeekDriver
from api import API
from config.manager import ConfigManager
from ui.settings_window import SettingsWindow
from ui.console_window import ConsoleWindow
from ui.help_window import HelpWindow
from ui.mini_console import MiniConsole
from ui.brand import BrandColors
from ui.icons import IconUtils, IconType
from ui.update_available_dialog import UpdateAvailableDialog, UpdateAvailableInfo
from utils.logger import Logger, LogLevel
from utils.update_checker import check_for_updates
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
    """Read version from version.txt file."""
    version_file = _resolve_resource_path("version.txt")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "unknown"


class MainWindow(QMainWindow):
    update_available_found = Signal(str, str)

    def __init__(self):
        super().__init__()
        version = get_version()
        self.setWindowTitle(f"IntenseRP Next v{version}")
        self.resize(450, 500)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG}; color: {BrandColors.TEXT_PRIMARY};")

        self.config_manager = ConfigManager()

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

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

        self.driver = None
        self.api = None
        self.server = None
        self.settings_window = None
        self.console_window = None
        self.help_window = None
        self._main_logging_enabled = True
        
        # Initialize logging based on settings
        self._setup_logging()
        
        # Always set the log callback for the mini-console
        Logger.set_console_callback(self._on_log_message)
        self.update_available_found.connect(self._show_update_available_dialog)

        self._maybe_check_for_updates_on_startup()

    @Slot(str, str)
    def _show_update_available_dialog(self, local_version: str, remote_version: str):
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
                    UpdateAvailableInfo(local_version=local_version, remote_version=remote_version),
                    parent=self,
                )
                dialog.exec()
            finally:
                self._update_dialog_open = False

        # make sure the dialog is shown from the running UI event loop to avoid
        # early-startup edge cases (startup update checks complete very quickly).
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
                    self.update_available_found.emit(result.local_version, result.remote_version)
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
        self.help_window.show()
        self.help_window.activateWindow()

    def on_settings_saved(self):
        Logger.info("Settings saved.")
        # Handle logging toggle
        self._setup_logging()
        
        # Update console settings if it exists
        # Rule 43 of The Internet: If it exists, then it exists
        if self.console_window:
            self.console_window.apply_settings()
            
        # If driver is running, it will pick up changes on next generation
        # All thanks to the config manager being dynamic

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
        try:
            # Pass config manager to driver
            self.driver = DeepSeekDriver(self.config_manager)
            self.driver.on_crash_callback = self.on_browser_crashed
            
            self.api = API(self.driver)
            
            # Configure Uvicorn
            port_setting = self.config_manager.get_setting("network_settings", "port")
            try:
                port = int(port_setting) if port_setting else 7777
            except (TypeError, ValueError):
                port = 7777

            available_on_lan = self.config_manager.get_setting("network_settings", "available_on_lan")
            host = "0.0.0.0" if available_on_lan else "127.0.0.1"

            # Configure Uvicorn with log_config=None to avoid "Unable to configure formatter 'default'" error
            config = uvicorn.Config(
                app=self.api.app,
                host=host,
                port=port,
                log_level="critical",
                log_config=None,
                access_log=False,
            )
            
            # Silence uvicorn loggers to avoid noisy console output.
            for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
                logger = logging.getLogger(logger_name)
                logger.handlers = [logging.NullHandler()]
                logger.setLevel(logging.CRITICAL)
                logger.propagate = False
                logger.disabled = True

            self.server = uvicorn.Server(config)
            
            # Start Driver (with status callback for browser installation/launch updates)
            self._update_status("Launching Browser...", "info")
            await self.driver.start(status_callback=lambda msg: self._update_status(msg, "info"))
            
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
            self.start_button.setEnabled(True)
            self.start_button.setText("Start")
            IconUtils.apply_icon(self.start_button, IconType.START, BrandColors.TEXT_PRIMARY)
            Logger.error(f"Error starting services: {e}")

    async def stop_services(self):
        Logger.info("Stopping services...")
        try:
            if self.api:
                await self.api.stop()
                
            if self.server:
                self.server.should_exit = True
                if hasattr(self, 'server_task'):
                    await self.server_task
            
            if self.driver:
                await self.driver.close()
                
            self._update_status("Stopped", "ready")
            self.start_button.setText("Start")
            IconUtils.apply_icon(self.start_button, IconType.START, BrandColors.TEXT_PRIMARY)
            self.start_button.setEnabled(True)
            Logger.success("Services stopped.")
        except Exception as e:
            Logger.error(f"Error stopping services: {e}")
            self._update_status(f"Error stopping: {e}", "error")
            self.start_button.setEnabled(True)

    async def on_browser_crashed(self):
        """
        Callback for when the browser crashes or is closed manually.
        """
        Logger.warning("Browser crash callback received.")
        self._update_status("Browser Closed/Crashed", "warning")
        
        # We need to clean up all services including playwright
        try:
            if self.api:
                await self.api.stop()
                
            if self.server:
                self.server.should_exit = True
                if hasattr(self, 'server_task'):
                    await self.server_task
            
            # The driver's close() method handles None checks for context/browser, theoretically that is enough
            if self.driver:
                try:
                    await self.driver.close()
                except Exception as e:
                    Logger.error(f"Error closing driver after crash: {e}")
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
            event.accept()
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
            
        asyncio.create_task(cleanup_and_close())

def main():
    import os
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

    from ui.app_icon import get_app_icon
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
