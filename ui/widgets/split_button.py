from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QMenu, QSizePolicy
from PySide6.QtCore import Signal, Qt, QPoint
from ui.core.brand import BrandColors
from ui.core.icons import IconUtils, IconType


CHEVRON_WIDTH = 28


class SplitButton(QWidget):
    """
    A button with an optional chevron dropdown overlaid on the right edge.

    The chevron does NOT shift the main button's icon/text! It's
    positioned as a child of the container (not in the layout) and
    placed over the rightmost pixels of the main button via resizeEvent.
    """

    clicked = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main button fills the widget horizontally but keeps its natural height
        self.main_button = QPushButton(text)
        self.main_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.main_button)
        self.main_button.clicked.connect(self.clicked.emit)

        # parented to self, NOT in the layout
        self.chevron_button = QPushButton(self)
        self.chevron_button.setFixedWidth(CHEVRON_WIDTH)
        self.chevron_button.setCursor(Qt.PointingHandCursor)
        self.chevron_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-left: 1px solid rgba(255, 255, 255, 0.2);
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
            QPushButton:disabled {{
                background-color: transparent;
            }}
        """)
        self._apply_chevron_icon()
        self.chevron_button.hide()

        # Dropdown menu
        self.menu = QMenu(self)
        self.menu.setWindowFlags(self.menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.menu.setAttribute(Qt.WA_TranslucentBackground)
        self.menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 6px;
                padding: 4px 0;
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QMenu::item {{
                color: {BrandColors.TEXT_PRIMARY};
                padding: 8px 20px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QMenu::item:selected {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            QMenu::item:disabled {{
                color: {BrandColors.TEXT_DISABLED};
            }}
        """)
        self.chevron_button.clicked.connect(self._show_menu)

        self._chevron_visible = False

    # ------------------------------------------------------------------
    # Chevron visibility
    # ------------------------------------------------------------------

    def set_chevron_visible(self, visible: bool):
        self._chevron_visible = visible
        self.chevron_button.setVisible(visible)
        if visible:
            self.chevron_button.setEnabled(self.main_button.isEnabled())

    # ------------------------------------------------------------------
    # QPushButton facade (keeps MainWindow code largely unchanged)
    # ------------------------------------------------------------------

    def setText(self, text: str):
        self.main_button.setText(text)

    def text(self) -> str:
        return self.main_button.text()

    def setEnabled(self, enabled: bool):
        self.main_button.setEnabled(enabled)
        if self._chevron_visible:
            self.chevron_button.setEnabled(enabled)

    def setStyleSheet(self, ss: str):
        self.main_button.setStyleSheet(ss)

    def setCursor(self, cursor):
        self.main_button.setCursor(cursor)

    def apply_icon(self, icon_type: IconType, color: str = None, size: int = 16, y_offset: int = 0):
        IconUtils.apply_icon(self.main_button, icon_type, color, size, y_offset)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        btn_h = self.main_button.height()
        self.chevron_button.setFixedHeight(btn_h)
        self.chevron_button.move(self.width() - CHEVRON_WIDTH, 0)

    def _show_menu(self):
        pos = self.chevron_button.mapToGlobal(
            QPoint(0, self.chevron_button.height())
        )
        self.menu.popup(pos)

    def _apply_chevron_icon(self):
        icon = IconUtils.get_icon(
            "chevron-down.svg",
            color=BrandColors.TEXT_PRIMARY,
            size=14,
            widget=self.chevron_button,
        )
        if not icon.isNull():
            self.chevron_button.setIcon(icon)
