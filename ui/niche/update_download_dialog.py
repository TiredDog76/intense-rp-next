from __future__ import annotations

import sys
import tempfile
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QThread, Signal, QObject, QProcess, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QMessageBox,
    QApplication,
)

from ui.core.brand import BrandColors
from ui.core.icons import IconType, IconUtils
from utils.auto_update import AutoUpdateError, PreparedUpdate, prepare_update_from_github, DownloadProgress


class MissingUpdaterError(RuntimeError):
    pass


def _find_staged_updater(prepared: PreparedUpdate) -> Path:
    """Find the updater binary in the staged update package."""
    package_root = prepared.extracted_app_root.resolve().parent
    if sys.platform.startswith("win"):
        updater_name = "updater.exe"
    else:
        updater_name = "updater"
    updater_path = package_root / "optional" / updater_name
    if updater_path.exists():
        return updater_path
    raise MissingUpdaterError(f"Update package does not contain {updater_path}")


def _format_bytes(n: Optional[int]) -> str:
    if n is None:
        return "?"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _format_speed(bps: float) -> str:
    if not bps or bps < 1:
        return "0 KB/s"
    return f"{_format_bytes(int(bps))}/s"


class _AutoUpdateWorker(QObject):
    status = Signal(str)
    progress = Signal(int, int, float)  # downloaded, total(-1 unknown), speed_bps
    finished = Signal(object)  # PreparedUpdate
    failed = Signal(str)

    def __init__(self, remote_version: str, expected_exe_name: str, parent=None):
        super().__init__(parent)
        self._remote_version = remote_version
        self._expected_exe_name = expected_exe_name
        self._cancelled = False

        self._download_dir = Path(tempfile.mkdtemp(prefix="intenserp-update-dl-"))
        self._extract_dir = Path(tempfile.mkdtemp(prefix="intenserp-update-extract-"))

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            self.status.emit("Contacting GitHub…")

            def should_cancel() -> bool:
                return bool(self._cancelled)

            def on_progress(p: DownloadProgress) -> None:
                total = p.total_bytes if p.total_bytes is not None else -1
                self.progress.emit(p.bytes_downloaded, total, float(p.speed_bytes_per_s))

            self.status.emit("Downloading update…")
            prepared = prepare_update_from_github(
                remote_version=self._remote_version,
                expected_exe_name=self._expected_exe_name,
                download_dir=self._download_dir,
                extract_dir=self._extract_dir,
                progress_cb=on_progress,
                should_cancel=should_cancel,
            )

            self.status.emit("Download complete.")
            self.finished.emit(prepared)
        except AutoUpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDownloadDialog(QDialog):
    """
    Downloads and prepares an update from GitHub.

    On success, sets self.prepared_update and enables the install action (implemented in follow-up).
    """

    def __init__(self, remote_version: str, parent=None):
        super().__init__(parent)
        self._remote_version = remote_version
        self.prepared_update: Optional[PreparedUpdate] = None

        self.setWindowTitle("Downloading Update")
        self.setModal(True)
        self.setFixedWidth(520)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("updateDownloadCard")
        card.setStyleSheet(
            f"""
            QFrame#updateDownloadCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Downloading update…")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_TITLE};
            font-weight: 800;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        layout.addWidget(title)

        self._status_label = QLabel("Preparing…")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            """
        )
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(14)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 7px;
            }}
            QProgressBar::chunk {{
                background-color: {BrandColors.ACCENT};
                border-radius: 7px;
            }}
            """
        )
        layout.addWidget(self._progress)

        self._details_label = QLabel("0 MB / ?  •  0 KB/s")
        self._details_label.setAlignment(Qt.AlignCenter)
        self._details_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_SMALL};
            color: {BrandColors.TEXT_DISABLED};
            background-color: transparent;
            """
        )
        layout.addWidget(self._details_label)

        self._asset_label = QLabel("")
        self._asset_label.setAlignment(Qt.AlignCenter)
        self._asset_label.setWordWrap(True)
        self._asset_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_SMALL};
            color: {BrandColors.TEXT_DISABLED};
            background-color: transparent;
            """
        )
        layout.addWidget(self._asset_label)

        layout.addWidget(self._build_button_row())

        self._start_worker()

    def closeEvent(self, event):
        # Best-effort cancellation when the user closes the dialog.
        self._cancel_worker()
        super().closeEvent(event)

    def _build_button_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 14px;
                border-radius: 8px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            """
        )
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self._cancel_btn, 1)

        self._install_btn = QPushButton("Install && Restart")
        self._install_btn.setCursor(Qt.PointingHandCursor)
        self._install_btn.setEnabled(False)
        self._install_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.ACCENT};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 14px;
                border-radius: 8px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 800;
            }}
            QPushButton:hover {{
                background-color: #4a80e0;
            }}
            QPushButton:pressed {{
                background-color: #3c6ac3;
            }}
            QPushButton:disabled {{
                background-color: {BrandColors.TEXT_DISABLED};
                color: {BrandColors.TEXT_PRIMARY};
            }}
            """
        )
        IconUtils.apply_icon(self._install_btn, IconType.BACKUP, BrandColors.TEXT_PRIMARY, size=16)
        self._install_btn.setIconSize(QSize(16, 16))
        self._install_btn.clicked.connect(self._on_install_clicked)
        layout.addWidget(self._install_btn, 1)
        return row

    def _start_worker(self) -> None:
        if not sys.platform.startswith(("win", "linux")):
            QMessageBox.warning(self, "Auto-Update", "Auto-update is supported only on Windows and Linux.")
            self.reject()
            return

        if not getattr(sys, "frozen", False):
            QMessageBox.warning(
                self, "Auto-Update", "Auto-update is available only in the packaged (PyInstaller) build."
            )
            self.reject()
            return

        expected_exe_name = Path(sys.executable).name
        self._thread = QThread(self)
        self._worker = _AutoUpdateWorker(
            remote_version=self._remote_version, expected_exe_name=expected_exe_name
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _cancel_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        thread = getattr(self, "_thread", None)
        if worker is not None:
            try:
                worker.cancel()
            except Exception:
                pass
        if thread is not None:
            try:
                thread.quit()
                thread.wait(1500)
            except Exception:
                pass

    def _on_status(self, text: str) -> None:
        self._status_label.setText(text or "")

    def _on_progress(self, downloaded: int, total: int, speed_bps: float) -> None:
        total_bytes = None if total < 0 else int(total)
        self._details_label.setText(
            f"{_format_bytes(downloaded)} / {_format_bytes(total_bytes)}  •  {_format_speed(speed_bps)}"
        )
        if total_bytes is None or total_bytes <= 0:
            self._progress.setRange(0, 0)  # indeterminate
            return
        if self._progress.maximum() == 0:
            self._progress.setRange(0, 100)
        pct = int((downloaded / total_bytes) * 100) if total_bytes else 0
        self._progress.setValue(max(0, min(100, pct)))

    def _on_finished(self, prepared: PreparedUpdate) -> None:
        self.prepared_update = prepared
        self._cancel_btn.setText("Close")
        self._status_label.setText("Ready to install.")
        self._install_btn.setEnabled(True)
        self._asset_label.setText(f"{prepared.tag}  •  {prepared.asset_name}")
        self._cancel_worker()

    def _on_failed(self, message: str) -> None:
        self._cancel_worker()
        QMessageBox.warning(
            self,
            "Auto-Update",
            "Failed to download the update.\n\n"
            f"{message}",
        )
        self.reject()

    def _on_cancel_clicked(self) -> None:
        if self.prepared_update is not None:
            self.accept()
            return
        self._cancel_worker()
        self.reject()

    def _on_install_clicked(self) -> None:
        prepared = self.prepared_update
        if prepared is None:
            return

        reply = QMessageBox.question(
            self,
            "Install Update",
            "The app will close to install the update and then relaunch.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        install_dir = Path(sys.executable).resolve().parent
        exe_name = Path(sys.executable).name
        try:
            updater_exe = _find_staged_updater(prepared)
        except Exception as exc:
            QMessageBox.warning(self, "Auto-Update", f"Update package is missing the updater.\n\n{exc}")
            return

        args = [
            "--install-dir",
            str(install_dir),
            "--app-pid",
            str(os.getpid()),
            "--exe-name",
            str(exe_name),
            "--payload-dir",
            str(prepared.extracted_app_root),
        ]

        detached_result = QProcess.startDetached(str(updater_exe), args, tempfile.gettempdir())
        ok = detached_result[0] if isinstance(detached_result, tuple) else bool(detached_result)
        if not ok:
            QMessageBox.warning(
                self,
                "Auto-Update",
                "Failed to start the updater.\n\n"
                "You can still download manually from the release page.",
            )
            from PySide6.QtCore import QUrl

            QDesktopServices.openUrl(QUrl(prepared.release_html_url))
            return

        # The updater waits for our process to exit before performing the update,
        # so we can safely force-exit without async cleanup (which can hang/crash).
        self._status_label.setText("Running Updater...")
        self._install_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._progress.setRange(0, 0)  # indeterminate spinner

        def force_exit():
            os._exit(0)

        QTimer.singleShot(500, force_exit)

    # Icon rendering is handled centrally by IconUtils
