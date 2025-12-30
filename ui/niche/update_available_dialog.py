from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..brand import BrandColors
from ..icons import IconType, IconUtils
from .update_method_dialog import UpdateMethodAvailability, UpdateMethodDialog, default_update_method_availability
from .update_git_instructions_dialog import UpdateGitInstructionsDialog
from .update_download_dialog import UpdateDownloadDialog


def _format_version(version: Optional[str]) -> str:
    value = (version or "").strip()
    if not value:
        return "unknown"
    if value.lower().startswith("v"):
        value = value[1:].strip() or "unknown"
    if value.lower() == "unknown":
        return "unknown"
    return f"v{value}"


@dataclass(frozen=True)
class UpdateAvailableInfo:
    local_version: str
    remote_version: str
    remote_auto_updateable: Optional[bool] = None
    remote_severity: Optional[int] = None

    @property
    def release_notes_url(self) -> str:
        remote = (self.remote_version or "").strip()
        if remote.lower().startswith("v"):
            remote = remote[1:].strip()
        if not remote or remote.lower() == "unknown":
            return "https://github.com/LyubomirT/intense-rp-next/releases"
        return f"https://github.com/LyubomirT/intense-rp-next/releases/tag/v{remote}"


class UpdateAvailableDialog(QDialog):
    def __init__(self, info: UpdateAvailableInfo, parent=None):
        super().__init__(parent)
        self._info = info
        self._install_button: QPushButton | None = None

        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setFixedWidth(440)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("updateCard")
        card.setStyleSheet(
            f"""
            QFrame#updateCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Update Available!")
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

        versions = self._build_version_row()
        layout.addWidget(versions, 0, Qt.AlignHCenter)

        meta = self._build_meta_row()
        layout.addWidget(meta, 0, Qt.AlignHCenter)

        desc_text = "An update is available. You can install it or skip for now."
        if info.remote_auto_updateable is False:
            desc_text = (
                "An update is available, but Auto-Update is disabled for this release. "
                "Use Git (source runs) or download manually from the release page."
            )

        desc = QLabel(desc_text)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 4px 4px;
            """
        )
        layout.addWidget(desc)

        buttons = self._build_button_row()
        layout.addWidget(buttons)

        view_release_notes = QPushButton("View Release Notes")
        view_release_notes.setCursor(Qt.PointingHandCursor)
        view_release_notes.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.INPUT_BORDER};
                padding: 10px 14px;
                border-radius: 8px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.ACCENT};
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
            }}
            """
        )
        view_release_notes.clicked.connect(self._open_release_notes)
        layout.addWidget(view_release_notes)

    def _build_version_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        local_label = QLabel(_format_version(self._info.local_version))
        local_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: 700;
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            """
        )
        layout.addWidget(local_label, 0, Qt.AlignVCenter)

        arrow = QLabel()
        arrow.setStyleSheet("background-color: transparent;")
        arrow.setPixmap(self._get_icon_pixmap("chevron-right.svg", 18))
        layout.addWidget(arrow, 0, Qt.AlignVCenter)

        remote_label = QLabel(_format_version(self._info.remote_version))
        remote_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: 800;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        layout.addWidget(remote_label, 0, Qt.AlignVCenter)

        return row

    def _build_meta_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        severity_text, severity_color = self._severity_text_and_color()
        severity_badge = QLabel(f"Severity: {severity_text}")
        severity_badge.setStyleSheet(
            f"""
            background-color: {BrandColors.SIDEBAR_BG};
            border: 1px solid {BrandColors.INPUT_BORDER};
            border-radius: 10px;
            padding: 6px 10px;
            font-size: {BrandColors.FONT_SIZE_SMALL};
            font-weight: 800;
            color: {severity_color};
            """
        )
        layout.addWidget(severity_badge, 0, Qt.AlignVCenter)

        if self._info.remote_auto_updateable is False:
            aua_badge = QLabel("Auto-Update: Disabled")
            aua_badge.setStyleSheet(
                f"""
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 10px;
                padding: 6px 10px;
                font-size: {BrandColors.FONT_SIZE_SMALL};
                font-weight: 800;
                color: {BrandColors.WARNING};
                """
            )
            layout.addWidget(aua_badge, 0, Qt.AlignVCenter)

        return row

    def _build_button_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(10)

        not_yet = QPushButton("Not Yet")
        not_yet.setCursor(Qt.PointingHandCursor)
        not_yet.setStyleSheet(
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
        IconUtils.apply_icon(not_yet, IconType.CANCEL, BrandColors.TEXT_PRIMARY, size=14)
        not_yet.setIconSize(QSize(14, 14))
        not_yet.clicked.connect(self.reject)
        layout.addWidget(not_yet, 1)

        install = QPushButton("Install")
        install.setCursor(Qt.PointingHandCursor)
        install.setStyleSheet(
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
            """
        )
        install.setIcon(QIcon(self._icon_path("download-cloud.svg")))
        install.setIconSize(QSize(16, 16))
        layout.addWidget(install, 1)
        install.clicked.connect(self._on_install_clicked)
        self._install_button = install

        return row

    def _severity_text_and_color(self) -> tuple[str, str]:
        mapping = {
            1: ("Optional", BrandColors.ACCENT),
            2: ("Normal", "#f0d154"),
            3: ("Important", "#8854f0"),
            4: ("Critical", BrandColors.DANGER),
        }
        sev = self._info.remote_severity
        if sev is None:
            return "Unknown", BrandColors.TEXT_DISABLED
        try:
            sev_int = int(sev)
        except Exception:
            return "Unknown", BrandColors.TEXT_DISABLED
        return mapping.get(sev_int, ("Unknown", BrandColors.TEXT_DISABLED))

    def _on_install_clicked(self) -> None:
        availability = default_update_method_availability()
        if self._info.remote_auto_updateable is False:
            availability = UpdateMethodAvailability(
                git_enabled=availability.git_enabled,
                auto_enabled=False,
                git_reason=availability.git_reason,
                auto_reason="Auto-Update is disabled for this release.",
            )

        if not availability.auto_enabled and not availability.git_enabled:
            self._open_release_notes()
            return

        dialog = UpdateMethodDialog(availability=availability, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        method = (dialog.selected_method or "").strip().lower()
        if method == "git":
            UpdateGitInstructionsDialog(parent=self).exec()
            return

        if method == "auto":
            UpdateDownloadDialog(remote_version=self._info.remote_version, parent=self).exec()
            return

    def _open_release_notes(self) -> None:
        QDesktopServices.openUrl(QUrl(self._info.release_notes_url))

    def _icon_path(self, filename: str) -> str:
        return os.path.join(os.path.dirname(__file__), "..", "assets", "icons", filename)

    def _get_icon_pixmap(self, filename: str, size: int) -> object:
        return QIcon(self._icon_path(filename)).pixmap(QSize(size, size))
