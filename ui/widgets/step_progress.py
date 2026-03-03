from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.core.brand import BrandColors


class StepProgressBar(QWidget):
    def __init__(self, steps: int, parent=None) -> None:
        super().__init__(parent)
        self._steps = max(1, int(steps))
        self._current = 0

        self._circle_radius = 14
        self._line_thickness = 3

        self.setFixedHeight(44)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(420, 44)

    def set_current_step(self, step_index: int) -> None:
        idx = int(step_index)
        idx = max(0, min(idx, self._steps - 1))
        if idx == self._current:
            return
        self._current = idx
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = int(self.width())
        h = int(self.height())
        y = int(h / 2)

        margin = self._circle_radius + 10
        if self._steps <= 1:
            positions = [int(w / 2)]
        else:
            usable = max(1, w - (2 * margin))
            step_px = usable / float(self._steps - 1)
            positions = [int(round(margin + (i * step_px))) for i in range(self._steps)]

        # Connecting line
        for i in range(self._steps - 1):
            completed = i < self._current
            color = BrandColors.ACCENT if completed else BrandColors.INPUT_BORDER
            pen = QPen(QColor(color))
            pen.setWidth(self._line_thickness)
            painter.setPen(pen)
            painter.drawLine(positions[i], y, positions[i + 1], y)

        # Steps
        font = QFont(BrandColors.FONT_FAMILY)
        font.setBold(True)
        painter.setFont(font)

        for i, x in enumerate(positions):
            if i < self._current:
                fill = BrandColors.ACCENT
                border = BrandColors.ACCENT
                text = BrandColors.TEXT_PRIMARY
            elif i == self._current:
                fill = BrandColors.SIDEBAR_BG
                border = BrandColors.ACCENT
                text = BrandColors.ACCENT
            else:
                fill = BrandColors.SIDEBAR_BG
                border = BrandColors.INPUT_BORDER
                text = BrandColors.TEXT_SECONDARY

            r = self._circle_radius
            painter.setBrush(QColor(fill))
            pen = QPen(QColor(border))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawEllipse(x - r, y - r, 2 * r, 2 * r)

            painter.setPen(QColor(text))
            painter.drawText(x - r, y - r, 2 * r, 2 * r, Qt.AlignCenter, str(i + 1))

        painter.end()

