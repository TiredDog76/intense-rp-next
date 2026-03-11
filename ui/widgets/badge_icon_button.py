from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton

from ui.core.brand import BrandColors


class BadgeIconButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._badge_visible = False
        self._badge_diameter = 10
        self._badge_margin_top = 6
        self._badge_margin_right = 6

    def set_badge_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if self._badge_visible == visible:
            return
        self._badge_visible = visible
        self.update()

    def badge_visible(self) -> bool:
        return self._badge_visible

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().paintEvent(event)
        if not self._badge_visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(BrandColors.DANGER))
        painter.setPen(QPen(QColor(BrandColors.SIDEBAR_BG), 2))

        x = self.width() - self._badge_diameter - self._badge_margin_right
        y = self._badge_margin_top
        painter.drawEllipse(x, y, self._badge_diameter, self._badge_diameter)
        painter.end()
