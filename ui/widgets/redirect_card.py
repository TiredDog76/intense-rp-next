from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.core.brand import BrandColors
from ui.widgets.components import DocsHelpButton


class RedirectCard(QFrame):
    """
    A settings-friendly redirect card: title + description + CTA button.
    """

    clicked = Signal()

    def __init__(
        self,
        title: str,
        description: str,
        button_text: str,
        docs_url: str = None,
        docs_handler=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("redirectCard")
        self._docs_url = str(docs_url or "").strip()
        self._docs_handler = docs_handler
        self._help_hovered = False
        self._help_focus_visible = False
        self.help_button = None
        self._help_slot = None
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

        title_row = QWidget()
        title_row.setStyleSheet("background-color: transparent;")
        title_row_layout = QHBoxLayout(title_row)
        title_row_layout.setContentsMargins(0, 0, 0, 0)
        title_row_layout.setSpacing(6)

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
        title_row_layout.addWidget(title_label, 0, Qt.AlignVCenter)

        if self._docs_url:
            self._help_slot = QWidget(self)
            self._help_slot.setStyleSheet("background-color: transparent;")
            self._help_slot.setFixedSize(16, 16)
            title_row_layout.addWidget(self._help_slot, 0, Qt.AlignVCenter)
            self._tag_docs_widget(self)
            self._tag_docs_widget(title_label)

        title_row_layout.addStretch(1)
        left.addWidget(title_row)

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
        self._tag_docs_widget(self.button)

    def _tag_docs_widget(self, widget) -> None:
        if widget is None or not self._docs_url:
            return
        widget.setProperty("docsUrl", self._docs_url)

    def _ensure_help_button(self) -> None:
        if self.help_button is not None or not self._docs_url or not self._help_slot:
            return

        slot_layout = QHBoxLayout(self._help_slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.setSpacing(0)

        self.help_button = DocsHelpButton(self._docs_url, self._help_slot)
        if self._docs_handler:
            self.help_button.clicked.connect(self._docs_handler)
        self.help_button.hide()
        slot_layout.addWidget(self.help_button, 0, Qt.AlignCenter)
        self._tag_docs_widget(self.help_button)

    def _update_help_button_visibility(self) -> None:
        should_show = self._help_hovered or self._help_focus_visible
        if should_show:
            self._ensure_help_button()
        if self.help_button:
            self.help_button.setVisible(should_show)

    def set_help_focus_visible(self, visible: bool) -> None:
        self._help_focus_visible = bool(visible)
        self._update_help_button_visibility()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._help_hovered = True
        self._update_help_button_visibility()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._help_hovered = False
        self._update_help_button_visibility()
