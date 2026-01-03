from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from config.manager import ConfigManager
from ui.core.brand import BrandColors
from ui.widgets.components import Description, Divider, StyledButton
from ..universal.working_dialog import WorkingDialog
from utils.config_backup import create_config_backup_zip, import_config_backup_zip
from utils.logger import Logger


class BackupImportWindow(QMainWindow):
    settings_reloaded = Signal()

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Backup & Import Settings")
        self.resize(560, 500)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG};")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Backup & Import Settings")
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
                "Create a .zip backup of your current config directory (settings/key/profiles), "
                "or import a backup to restore them.\n\n"
                "Import replaces your active config directory contents, then reloads settings automatically."
            )
        )

        layout.addWidget(Divider("Active Config Directory"))

        self.path_label = QLabel(self._get_config_dir_label())
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.path_label.setStyleSheet(
            f"""
            QLabel {{
                color: {BrandColors.TEXT_PRIMARY};
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            """
        )
        layout.addWidget(self.path_label)

        layout.addWidget(Divider("Backup / Import"))

        row = QHBoxLayout()
        row.setSpacing(10)

        self.backup_btn = StyledButton("Backup to .zip")
        self.backup_btn.clicked.connect(self._backup_to_zip)
        row.addWidget(self.backup_btn, stretch=1)

        self.import_btn = StyledButton("Import from .zip")
        self.import_btn.clicked.connect(self._import_from_zip)
        row.addWidget(self.import_btn, stretch=1)

        layout.addLayout(row)

        layout.addWidget(Divider())

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = StyledButton("Close")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def _get_config_dir_label(self) -> str:
        try:
            return str(Path(getattr(self.config_manager, "config_dir", "config_data")).resolve())
        except Exception:
            return str(getattr(self.config_manager, "config_dir", "config_data"))

    def _reload_settings(self) -> None:
        try:
            self.config_manager.reload_from_disk()
        except Exception as e:
            Logger.warning(f"Failed to reload config after backup/import: {e}")
        self.path_label.setText(self._get_config_dir_label())
        self.settings_reloaded.emit()

    def _backup_to_zip(self) -> None:
        try:
            self.config_manager.save_settings()
        except Exception:
            pass

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_name = f"intenserp-next-config-backup-{ts}.zip"
        default_path = str(Path.home() / default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Settings Backup",
            default_path,
            "Zip Archives (*.zip)",
        )
        if not file_path:
            return

        ok, message = WorkingDialog.run_task(
            parent=self,
            title="Backing Up...",
            message="Creating backup zip...",
            task_fn=lambda: create_config_backup_zip(self.config_manager.config_dir, file_path),
        )
        if ok:
            Logger.success("Settings backup created.")
            QMessageBox.information(self, "Backup Created", message)
            self._reload_settings()
        else:
            Logger.warning(f"Settings backup failed: {message}")
            QMessageBox.warning(self, "Backup Failed", message)

    def _import_from_zip(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup Zip",
            str(Path.home()),
            "Zip Archives (*.zip)",
        )
        if not file_path:
            return

        confirm = QMessageBox(self)
        confirm.setWindowTitle("Import Settings")
        confirm.setIcon(QMessageBox.Warning)
        confirm.setText(
            "This will replace your active config directory contents using the selected .zip backup.\n\n"
            "If Persistent Sessions are enabled and the browser/services are running, import may fail "
            "because profile files can be in use.\n\n"
            "After importing, settings reload automatically.\n\n"
            "Continue?"
        )
        confirm.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        confirm.setDefaultButton(QMessageBox.Cancel)

        if confirm.exec() != QMessageBox.Ok:
            return

        ok, message = WorkingDialog.run_task(
            parent=self,
            title="Importing...",
            message="Restoring config directory from zip...",
            task_fn=lambda: import_config_backup_zip(file_path, self.config_manager.config_dir),
        )
        if not ok:
            Logger.warning(f"Settings import failed: {message}")
            QMessageBox.warning(self, "Import Failed", message)
            return

        Logger.success("Settings import completed.")
        self._reload_settings()
        QMessageBox.information(self, "Import Complete", message)
