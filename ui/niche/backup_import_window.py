from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.manager import ConfigManager
from ui.core.brand import BrandColors
from ui.widgets.components import Description, Divider, StyledButton, Tumbler
from ..universal.working_dialog import WorkingDialog
from utils.config_backup import ConfigBackupOptions, create_config_backup_zip, import_config_backup_zip
from utils.logger import Logger


class _BackupOptionRow(QFrame):
    def __init__(self, label: str, checked: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("backupOptionRow")
        self.setStyleSheet(
            f"""
            QFrame#backupOptionRow {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.label = QLabel(label)
        self.label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-weight: 600;
            background-color: transparent;
            """
        )
        layout.addWidget(self.label, stretch=1)

        self.tumbler = Tumbler()
        self.tumbler.setChecked(checked)
        layout.addWidget(self.tumbler)


class BackupImportCustomizeDialog(QDialog):
    def __init__(self, options: ConfigBackupOptions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Backup & Import")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Customize")
        title.setStyleSheet(
            f"""
            font-size: 20px;
            font-weight: bold;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        layout.addWidget(title)

        description = Description(
            "Choose which parts are included when backing up, and which parts are used when importing."
        )
        description.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(description)

        self.settings_row = _BackupOptionRow("Settings & State", options.settings_state)
        self.profiles_row = _BackupOptionRow("Profiles", options.profiles)
        self.credentials_row = _BackupOptionRow("Credentials", options.credentials)

        for row in (self.settings_row, self.profiles_row, self.credentials_row):
            row.tumbler.toggled.connect(self._refresh_apply_state)
            layout.addWidget(row)

        self.warning_label = QLabel("Select at least one category.")
        self.warning_label.setStyleSheet(
            f"""
            color: {BrandColors.WARNING};
            font-size: {BrandColors.FONT_SIZE_SMALL};
            background-color: transparent;
            """
        )
        layout.addWidget(self.warning_label)

        button_row = QHBoxLayout()
        button_row.addStretch()

        cancel_btn = StyledButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)

        self.apply_btn = StyledButton("Apply")
        self.apply_btn.clicked.connect(self.accept)
        button_row.addWidget(self.apply_btn)

        layout.addLayout(button_row)
        self._refresh_apply_state()

    def selected_options(self) -> ConfigBackupOptions:
        return ConfigBackupOptions(
            settings_state=self.settings_row.tumbler.isChecked(),
            profiles=self.profiles_row.tumbler.isChecked(),
            credentials=self.credentials_row.tumbler.isChecked(),
        )

    def _refresh_apply_state(self) -> None:
        has_selection = self.selected_options().any_enabled()
        self.apply_btn.setEnabled(has_selection)
        self.warning_label.setVisible(not has_selection)


class BackupImportWindow(QMainWindow):
    settings_reloaded = Signal()

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.backup_options = ConfigBackupOptions()
        self.setWindowTitle("Backup & Import Settings")
        self.resize(600, 560)
        self.setMinimumSize(540, 520)
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

        self.description_label = Description(
            "Create a .zip backup of your current config directory, or import a backup to restore it.\n\n"
            "Use Customize to include only settings/state, profiles, credentials, or any mix of them."
        )
        self.description_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self.description_label)

        layout.addWidget(Divider("Active Config Directory"))

        self.path_label = QLabel(self._get_config_dir_label())
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
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

        customize_row = QHBoxLayout()
        customize_row.setSpacing(10)

        self.options_summary_label = QLabel("")
        self.options_summary_label.setWordWrap(True)
        self.options_summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.options_summary_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_SECONDARY};
            font-size: {BrandColors.FONT_SIZE_SMALL};
            background-color: transparent;
            """
        )
        customize_row.addWidget(self.options_summary_label, stretch=1)

        self.customize_btn = StyledButton("Customize")
        self.customize_btn.clicked.connect(self._customize_options)
        customize_row.addWidget(self.customize_btn)

        layout.addLayout(customize_row)

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
        self._refresh_options_summary()
        self._reserve_wrapped_label_heights()

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

    def _options_summary(self) -> str:
        labels = self.backup_options.labels()
        return ", ".join(labels) if labels else "None"

    def _refresh_options_summary(self) -> None:
        self.options_summary_label.setText(f"Included: {self._options_summary()}")
        self._reserve_wrapped_label_heights()

    def _reserve_wrapped_label_heights(self) -> None:
        for label in (
            getattr(self, "description_label", None),
            getattr(self, "path_label", None),
            getattr(self, "options_summary_label", None),
        ):
            if label is None:
                continue
            width = max(1, label.width())
            if label.hasHeightForWidth():
                height = label.heightForWidth(width)
            else:
                height = label.sizeHint().height()
            label.setMinimumHeight(max(1, height))
            label.updateGeometry()

        central_widget = self.centralWidget()
        if central_widget is not None:
            central_widget.updateGeometry()
            hint = central_widget.sizeHint()
            if hint.isValid():
                self.setMinimumHeight(max(520, hint.height()))

    def _customize_options(self) -> None:
        dialog = BackupImportCustomizeDialog(self.backup_options, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.backup_options = dialog.selected_options()
        self._refresh_options_summary()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reserve_wrapped_label_heights()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reserve_wrapped_label_heights)

    def _backup_to_zip(self) -> None:
        if not self.backup_options.any_enabled():
            QMessageBox.warning(self, "Backup Settings", "Select at least one category to back up.")
            return

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
            task_fn=lambda: create_config_backup_zip(
                self.config_manager.config_dir,
                file_path,
                self.backup_options,
            ),
        )
        if ok:
            Logger.success("Settings backup created.")
            QMessageBox.information(self, "Backup Created", message)
            self._reload_settings()
        else:
            Logger.warning(f"Settings backup failed: {message}")
            QMessageBox.warning(self, "Backup Failed", message)

    def _import_from_zip(self) -> None:
        if not self.backup_options.any_enabled():
            QMessageBox.warning(self, "Import Settings", "Select at least one category to import.")
            return

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
        if self.backup_options.all_enabled():
            confirm_text = (
                "This will replace your active config directory contents using the selected .zip backup.\n\n"
                "If Persistent Sessions are enabled and the browser/services are running, import may fail "
                "because profile files can be in use.\n\n"
                "After importing, settings reload automatically.\n\n"
                "Continue?"
            )
        else:
            confirm_text = (
                "This will import only the selected data from the .zip backup:\n\n"
                f"{self._options_summary()}\n\n"
                "Other config data will be left in place. After importing, settings reload automatically.\n\n"
                "Continue?"
            )
            if self.backup_options.profiles:
                confirm_text = (
                    "If Persistent Sessions are enabled and the browser/services are running, profile import "
                    "may fail because profile files can be in use.\n\n"
                    + confirm_text
                )
        confirm.setText(confirm_text)
        confirm.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        confirm.setDefaultButton(QMessageBox.Cancel)

        if confirm.exec() != QMessageBox.Ok:
            return

        ok, message = WorkingDialog.run_task(
            parent=self,
            title="Importing...",
            message="Restoring config directory from zip...",
            task_fn=lambda: import_config_backup_zip(
                file_path,
                self.config_manager.config_dir,
                self.backup_options,
            ),
        )
        if not ok:
            Logger.warning(f"Settings import failed: {message}")
            QMessageBox.warning(self, "Import Failed", message)
            return

        Logger.success("Settings import completed.")
        self._reload_settings()
        QMessageBox.information(self, "Import Complete", message)
