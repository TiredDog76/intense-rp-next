from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..brand import BrandColors
from ..icons import IconType, IconUtils
from .update_method_dialog import UpdateMethodDialog
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

        desc = QLabel("An update is available. You can install it or skip for now.")
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

    def _on_install_clicked(self) -> None:
        dialog = UpdateMethodDialog(parent=self)
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
