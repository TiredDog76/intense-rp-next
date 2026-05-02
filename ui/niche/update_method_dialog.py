from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.core.brand import BrandColors
from ui.core.icons import IconUtils


@dataclass(frozen=True)
class UpdateMethodAvailability:
    git_enabled: bool
    auto_enabled: bool
    git_reason: str = ""
    auto_reason: str = ""


def default_update_method_availability() -> UpdateMethodAvailability:
    frozen = bool(getattr(sys, "frozen", False))

    # From source runs can be updated via Git; PyInstaller builds do not have a git checkout.
    git_enabled = not frozen
    git_reason = "" if git_enabled else "You aren't on a source run."

    # Auto-update is available for packaged builds on Windows and Linux.
    auto_enabled = frozen
    auto_reason = "" if auto_enabled else "Not available on source runs."

    return UpdateMethodAvailability(
        git_enabled=git_enabled,
        auto_enabled=auto_enabled,
        git_reason=git_reason,
        auto_reason=auto_reason,
    )


class UpdateMethodDialog(QDialog):
    """
    Ask the user which update method to use.

    Returns selected_method in {"git", "auto"} when accepted; otherwise None.
    """

    def __init__(self, availability: Optional[UpdateMethodAvailability] = None, parent=None):
        super().__init__(parent)
        self.selected_method: Optional[str] = None

        self.setWindowTitle("Choose Update Method")
        self.setModal(True)
        self.setFixedWidth(520)
        self.setFixedHeight(310)

        availability = availability or default_update_method_availability()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("updateMethodCard")
        card.setStyleSheet(
            f"""
            QFrame#updateMethodCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        title = QLabel("How do you want to update?")
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

        subtitle = QLabel("Pick a method based on how you installed the app.")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            """
        )
        layout.addWidget(subtitle)

        layout.addWidget(self._build_method_row(availability))

        buttons = self._build_bottom_row()
        layout.addWidget(buttons)

    def _build_method_row(self, availability: UpdateMethodAvailability) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(10)

        auto_btn = self._create_method_button(
            title="Auto-Update",
            subtitle="Recommended for packaged builds.",
            icon="download-cloud.svg",
            enabled=availability.auto_enabled,
            disabled_reason=availability.auto_reason,
        )
        auto_btn.clicked.connect(lambda: self._select("auto"))

        git_btn = self._create_method_button(
            title="Git",
            subtitle="Update a source checkout using the terminal.",
            icon="terminal.svg",
            enabled=availability.git_enabled,
            disabled_reason=availability.git_reason,
        )
        git_btn.clicked.connect(lambda: self._select("git"))

        layout.addWidget(auto_btn, 1)
        layout.addWidget(git_btn, 1)
        return row

    def _build_bottom_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(
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
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel, 1)
        return row

    def _select(self, method: str) -> None:
        self.selected_method = method
        self.accept()

    def _create_method_button(
        self,
        *,
        title: str,
        subtitle: str,
        icon: str,
        enabled: bool,
        disabled_reason: str,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setEnabled(enabled)
        btn.setMinimumHeight(92)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 10px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.ACCENT};
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.ITEM_SELECTED};
            }}
            QPushButton:disabled {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                color: {BrandColors.TEXT_DISABLED};
            }}
            """
        )

        content = QVBoxLayout(btn)
        content.setContentsMargins(14, 12, 14, 12)
        content.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        icon_label = QLabel()
        icon_label.setStyleSheet("background-color: transparent;")
        icon_size = 24
        icon_color = BrandColors.TEXT_PRIMARY if enabled else BrandColors.TEXT_DISABLED
        pixmap = IconUtils.get_pixmap(
            icon,
            color=icon_color,
            size=icon_size,
            dpr=self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(QSize(icon_size, icon_size))
        top.addWidget(icon_label, 0, Qt.AlignVCenter)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        title_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: 800;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        if not enabled:
            title_label.setStyleSheet(
                f"""
                font-size: {BrandColors.FONT_SIZE_LARGE};
                font-weight: 800;
                color: {BrandColors.TEXT_DISABLED};
                background-color: transparent;
                """
            )
        top.addWidget(title_label, 1)
        content.addLayout(top)

        sub = QLabel(subtitle if enabled else disabled_reason or subtitle)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding-left: 34px;
            """
        )
        if not enabled:
            sub.setStyleSheet(
                f"""
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                color: {BrandColors.TEXT_DISABLED};
                background-color: transparent;
                padding-left: 34px;
                """
            )
        content.addWidget(sub)

        return btn
