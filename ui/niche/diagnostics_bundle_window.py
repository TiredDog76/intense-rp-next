from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from ui.widgets.components import Description, Divider, StyledButton
from ui.universal.working_dialog import WorkingDialog
from utils.diagnostics import (
    create_diagnostics_bundle_zip,
    diagnostics_internal_log_enabled,
    diagnostics_prompt_capture_enabled,
    get_latest_internal_log_path,
    list_prompt_snapshots,
)
from utils.logger import Logger


class _DiagnosticsCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("diagnosticsCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setStyleSheet(
            f"""
            QFrame#diagnosticsCard {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 10px;
            }}
            """
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(8)

        self._title = QLabel(str(title or ""))
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: 700;
            background-color: transparent;
            """
        )
        self._layout.addWidget(self._title)

    @property
    def body_layout(self) -> QVBoxLayout:
        return self._layout


class _StatusRow(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._label = QLabel(str(label or ""))
        self._label.setWordWrap(True)
        self._label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_SECONDARY};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            background-color: transparent;
            font-weight: 600;
            """
        )
        self._label.setMinimumWidth(170)
        self._label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(self._label, 0)

        self._value = QLabel("")
        self._value.setWordWrap(True)
        self._value.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            background-color: transparent;
            """
        )
        self._value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self._value, 1)

    def set_value(self, value: str) -> None:
        self._value.setText(str(value or ""))


class DiagnosticsBundleWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Bug Report")
        self.resize(660, 560)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG};")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Bug Report")
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
                "Create a quick .zip bundle from the internal diagnostics log and the latest saved prompt snapshots. "
                "This is meant for bug reports, not general backups."
            )
        )

        self.warning_card = _DiagnosticsCard("Sensitive Info")
        warning_text = QLabel(
            "Prompt capture stores the provider-ready prompt text, and the internal diagnostics log can still "
            "include redacted account or session details. Only share this zip if you are comfortable sending that."
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet(
            f"""
            QLabel {{
                color: {BrandColors.TEXT_PRIMARY};
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                background-color: transparent;
            }}
            """
        )
        self.warning_card.body_layout.addWidget(warning_text)
        layout.addWidget(self.warning_card)

        self.status_card = _DiagnosticsCard("Available Data")
        self._internal_log_enabled_row = _StatusRow("Internal diagnostics log")
        self._latest_log_row = _StatusRow("Latest saved log")
        self._prompt_capture_row = _StatusRow("Prompt capture")
        self._prompt_snapshot_row = _StatusRow("Saved prompt snapshots")
        for row in (
            self._internal_log_enabled_row,
            self._latest_log_row,
            self._prompt_capture_row,
            self._prompt_snapshot_row,
        ):
            self.status_card.body_layout.addWidget(row)
        layout.addWidget(self.status_card)

        self.help_card = _DiagnosticsCard("How This Works")
        self.help_label = QLabel("")
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet(
            f"""
            QLabel {{
                color: {BrandColors.TEXT_PRIMARY};
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                background-color: transparent;
            }}
            """
        )
        self.help_card.body_layout.addWidget(self.help_label)
        layout.addWidget(self.help_card)

        layout.addWidget(Divider("Create Zip"))

        self.create_btn = StyledButton("Create Bug Report Zip")
        self.create_btn.setMinimumHeight(48)
        self.create_btn.clicked.connect(self._create_bundle)
        layout.addWidget(self.create_btn)

        layout.addStretch()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = StyledButton("Close")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._refresh_status()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_status()

    def _refresh_status(self) -> None:
        internal_log_enabled = diagnostics_internal_log_enabled(self.config_manager)
        prompt_capture_enabled = diagnostics_prompt_capture_enabled(self.config_manager)
        latest_log = get_latest_internal_log_path(self.config_manager.config_dir)
        prompt_snapshots = list_prompt_snapshots(self.config_manager.config_dir)

        self._internal_log_enabled_row.set_value("Enabled" if internal_log_enabled else "Disabled")
        self._latest_log_row.set_value(latest_log.name if latest_log else "None yet")
        self._prompt_capture_row.set_value("Enabled" if prompt_capture_enabled else "Disabled")
        self._prompt_snapshot_row.set_value(str(len(prompt_snapshots)))

        any_feature_enabled = bool(internal_log_enabled or prompt_capture_enabled)
        self.create_btn.setEnabled(any_feature_enabled)
        if any_feature_enabled:
            self.help_label.setText(
                "Pick a save location, then IntenseRP will snapshot whatever diagnostics data is currently available "
                "and package it into one .zip file."
            )
        else:
            self.help_label.setText(
                "Turn on Bug Reports in Settings > Logs and Troubleshooting first. "
                "If you prefer not to enable this, you can still collect public log files and prompt text manually."
            )

    def _create_bundle(self) -> None:
        internal_log_enabled = diagnostics_internal_log_enabled(self.config_manager)
        prompt_capture_enabled = diagnostics_prompt_capture_enabled(self.config_manager)
        if not (internal_log_enabled or prompt_capture_enabled):
            QMessageBox.warning(
                self,
                "Bug Report",
                "Bug Reports are disabled in Settings > Logs and Troubleshooting.\n\n"
                "Enable the internal log and/or last prompt capture first, or collect the files manually instead.",
            )
            return

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_name = f"irp-bug-report-{ts}.zip"
        default_path = str(Path.home() / default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Bug Report Zip",
            default_path,
            "Zip Archives (*.zip)",
        )
        if not file_path:
            return

        ok, message = WorkingDialog.run_task(
            parent=self,
            title="Creating Bug Report...",
            message="Collecting diagnostics and creating the zip file...",
            task_fn=lambda: create_diagnostics_bundle_zip(self.config_manager, file_path),
        )
        if ok:
            Logger.success("Bug report bundle created.")
            QMessageBox.information(self, "Bug Report", message)
        else:
            Logger.warning(f"Bug report bundle creation failed: {message}")
            QMessageBox.warning(self, "Bug Report", message)

        self._refresh_status()
