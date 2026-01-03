from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.core.brand import BrandColors
from ui.core.icons import IconType, IconUtils


def _format_version(version: str) -> str:
    value = (version or "").strip()
    if not value:
        return "unknown"
    if value.lower().startswith("v"):
        value = value[1:].strip() or "unknown"
    if value.lower() == "unknown":
        return "unknown"
    return f"v{value}"


@dataclass(frozen=True)
class UpdateInstalledInfo:
    version: str
    release_notes_url: str


class UpdateInstalledDialog(QDialog):
    def __init__(self, info: UpdateInstalledInfo, parent=None):
        super().__init__(parent)
        self._info = info

        self.setWindowTitle("Update Installed")
        self.setModal(True)
        self.setFixedWidth(440)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("updateInstalledCard")
        card.setStyleSheet(
            f"""
            QFrame#updateInstalledCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Update Installed!")
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

        version_text = _format_version(self._info.version)
        subtitle = QLabel(f"Update {version_text} successfully installed.")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 4px 4px;
            """
        )
        layout.addWidget(subtitle)

        layout.addWidget(self._build_button_row())

    def _build_button_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
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
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn, 1)

        notes_btn = QPushButton("Release Notes")
        notes_btn.setCursor(Qt.PointingHandCursor)
        notes_btn.setStyleSheet(
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
        notes_btn.clicked.connect(self._on_release_notes_clicked)
        IconUtils.apply_icon(notes_btn, IconType.HELP, BrandColors.TEXT_PRIMARY, size=14)
        notes_btn.setIconSize(QSize(16, 16))
        layout.addWidget(notes_btn, 1)

        return row

    def _on_release_notes_clicked(self) -> None:
        url = (self._info.release_notes_url or "").strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.accept()
