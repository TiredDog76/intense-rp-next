from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QVBoxLayout

from ui.core.brand import BrandColors
from ui.widgets.rounded_progress_bar import RoundedProgressBar


class _WorkingWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, task_fn: Callable[[], Tuple[bool, str]], parent=None):
        super().__init__(parent)
        self._task_fn = task_fn

    def run(self) -> None:
        try:
            ok, message = self._task_fn()
            self.finished.emit(bool(ok), str(message))
        except Exception as e:
            self.finished.emit(False, str(e))


class WorkingDialog(QDialog):
    """
    Small modal dialog with an indeterminate progress bar.

    Runs a task on a QThread and closes automatically when the task finishes.
    """

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(480)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)

        self.result_ok: Optional[bool] = None
        self.result_message: str = ""
        self._running = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("workingDialogCard")
        card.setStyleSheet(
            f"""
            QFrame#workingDialogCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_TITLE};
            font-weight: 800;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        layout.addWidget(self._title)

        self._status = QLabel(message)
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            """
        )
        layout.addWidget(self._status)

        self._progress = RoundedProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(14)
        self._progress.setRange(0, 0)  # indeterminate
        layout.addWidget(self._progress)

    def set_status(self, text: str) -> None:
        self._status.setText(text or "")

    def closeEvent(self, event):
        if self._running:
            event.ignore()
            return
        super().closeEvent(event)

    def _cleanup_worker(self) -> None:
        thread = getattr(self, "_thread", None)
        worker = getattr(self, "_worker", None)

        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass

        if thread is not None:
            try:
                thread.quit()
                thread.wait(1500)
            except Exception:
                pass
            try:
                thread.deleteLater()
            except Exception:
                pass

        self._thread = None
        self._worker = None

    def start(self, task_fn: Callable[[], Tuple[bool, str]]) -> None:
        self._running = True
        self._thread = QThread(self)
        self._worker = _WorkingWorker(task_fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _on_finished(self, ok: bool, message: str) -> None:
        self.result_ok = bool(ok)
        self.result_message = str(message or "")
        self._running = False
        self._cleanup_worker()
        self.accept()

    @staticmethod
    def run_task(parent, title: str, message: str, task_fn: Callable[[], Tuple[bool, str]]) -> Tuple[bool, str]:
        dialog = WorkingDialog(title=title, message=message, parent=parent)
        dialog.start(task_fn)
        dialog.exec()
        ok = bool(dialog.result_ok)
        return ok, str(dialog.result_message or "")
