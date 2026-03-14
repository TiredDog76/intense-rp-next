from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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
        self._help_hovered = False
        self.help_button = None
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

        if self._docs_url and docs_handler:
            self.help_button = DocsHelpButton(self._docs_url, self)
            self.help_button.clicked.connect(docs_handler)
            self.help_button.hide()
            title_row_layout.addWidget(self.help_button, 0, Qt.AlignVCenter)
            self._tag_docs_widget(self)
            self._tag_docs_widget(title_label)
            self._tag_docs_widget(self.help_button)

            app = QApplication.instance()
            if app is not None:
                app.focusChanged.connect(self._on_app_focus_changed)

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

    def _has_focus_within(self) -> bool:
        app = QApplication.instance()
        focus_widget = app.focusWidget() if app is not None else None
        return bool(focus_widget and (focus_widget is self.help_button or self.isAncestorOf(focus_widget)))

    def _update_help_button_visibility(self) -> None:
        if not self.help_button:
            return
        self.help_button.setVisible(self._help_hovered or self._has_focus_within())

    def _on_app_focus_changed(self, _old, _new) -> None:
        self._update_help_button_visibility()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._help_hovered = True
        self._update_help_button_visibility()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._help_hovered = False
        self._update_help_button_visibility()
