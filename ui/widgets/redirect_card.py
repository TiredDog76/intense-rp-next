from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.core.brand import BrandColors


class RedirectCard(QFrame):
    """
    A settings-friendly redirect card: title + description + CTA button.
    """

    clicked = Signal()

    def __init__(self, title: str, description: str, button_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("redirectCard")
        self.setStyleSheet(
            f"""
            QFrame#redirectCard {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: 2px solid {BrandColors.ACCENT};
                border-radius: 10px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(4)

        title_label = QLabel(str(title or ""))
        title_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: 700;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        left.addWidget(title_label)

        desc_label = QLabel(str(description or ""))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_SMALL};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            """
        )
        desc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        left.addWidget(desc_label)

        layout.addLayout(left, 1)

        self.button = QPushButton(str(button_text or "Open"))
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setIconSize(QSize(16, 16))
        self.button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.ACCENT};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 16px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: #4a80e0;
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.CATEGORY_ACTIVE_BG};
            }}
            """
        )
        self.button.clicked.connect(self.clicked.emit)
        layout.addWidget(self.button, 0, Qt.AlignVCenter)
