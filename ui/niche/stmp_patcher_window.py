from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QFileDialog,
)

from ui.brand import BrandColors
from ui.components import StyledButton, Description, Divider
from utils.logger import Logger
from utils.stmp_patcher import patch_stmp_installation, scan_stmp_installation


class STMPPatcherWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RossAscends's STMP Patcher")
        self.resize(560, 480)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG};")

        self._selected_root: Path | None = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("RossAscends's STMP Patcher")
        title.setStyleSheet(
            f"""
            font-size: 24px;
            font-weight: bold;
            color: {BrandColors.TEXT_PRIMARY};
            """
        )
        layout.addWidget(title)

        layout.addWidget(
            Description(
                "Patch RossAscends's SillyTavern MultiPlayer (STMP) so it includes per-message names in Chat Completion payloads. "
                "This lets IntenseRP detect user/character names via Message Objects."
            )
        )

        layout.addWidget(Divider("Select RossAscends's STMP Folder"))

        self.path_label = QLabel("No folder selected.")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            """
        )
        layout.addWidget(self.path_label)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_SMALL};
            """
        )
        layout.addWidget(self.status_label)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.select_btn = StyledButton("Select STMP folder")
        self.select_btn.clicked.connect(self._select_folder)
        row.addWidget(self.select_btn, stretch=2)

        self.patch_btn = StyledButton("Apply patch")
        self.patch_btn.setEnabled(False)
        self.patch_btn.clicked.connect(self._apply_patch)
        row.addWidget(self.patch_btn, stretch=1)

        layout.addLayout(row)

        layout.addWidget(Divider())

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = StyledButton("Close")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def _select_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select RossAscends's STMP Folder")
        if not directory:
            return

        scan = scan_stmp_installation(directory)

        if not scan.server_js.is_file():
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "This folder does not look like RossAscends's STMP (missing server.js).",
            )
            self._selected_root = None
            self.path_label.setText("No folder selected.")
            self.status_label.setText("")
            self.patch_btn.setEnabled(False)
            return

        if scan.api_calls is None:
            QMessageBox.warning(
                self,
                "Unsupported Layout",
                "Could not find src/api-calls.js inside this RossAscends STMP folder.",
            )
            self._selected_root = None
            self.path_label.setText("No folder selected.")
            self.status_label.setText("")
            self.patch_btn.setEnabled(False)
            return

        self._selected_root = scan.stmp_root
        self.path_label.setText(str(scan.stmp_root))

        status_parts = []
        if scan.is_patched:
            status_parts.append("Status: already patched")
        else:
            status_parts.append("Status: not patched")

        if scan.has_legacy_irp_next_field and not scan.is_patched:
            status_parts.append("(legacy 'irp-next' field detected)")

        status_parts.append(f"Target file: {scan.api_calls}")
        self.status_label.setText(" ".join(status_parts))

        self.patch_btn.setEnabled(not scan.is_patched)

    def _apply_patch(self):
        if self._selected_root is None:
            return

        scan = scan_stmp_installation(self._selected_root)
        if scan.api_calls is None or not scan.api_calls.is_file():
            QMessageBox.warning(self, "Missing File", "Could not find src/api-calls.js. Please re-select the folder.")
            self.patch_btn.setEnabled(False)
            return

        confirm = QMessageBox(self)
        confirm.setWindowTitle("Apply RossAscends's STMP Patch")
        confirm.setIcon(QMessageBox.Warning)
        confirm.setText(
            "This will modify RossAscends's STMP api-calls.js to add a 'name' field to message objects.\n\n"
            "A backup copy will be created next to the file.\n\n"
            f"Target: {scan.api_calls}\n\n"
            "Continue?"
        )
        confirm.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        confirm.setDefaultButton(QMessageBox.Cancel)

        if confirm.exec() != QMessageBox.Ok:
            return

        success, message = patch_stmp_installation(self._selected_root)

        if success:
            Logger.success(message)
            QMessageBox.information(self, "Patch Result", message)
        else:
            Logger.warning(message)
            QMessageBox.warning(self, "Patch Result", message)

        self._select_folder_refresh()

    def _select_folder_refresh(self):
        if self._selected_root is None:
            return

        scan = scan_stmp_installation(self._selected_root)
        if scan.api_calls is None:
            self.status_label.setText("Status: unknown (missing src/api-calls.js)")
            self.patch_btn.setEnabled(False)
            return

        status_parts = []
        status_parts.append("Status: already patched" if scan.is_patched else "Status: not patched")
        status_parts.append(f"Target file: {scan.api_calls}")
        self.status_label.setText(" ".join(status_parts))
        self.patch_btn.setEnabled(not scan.is_patched)
