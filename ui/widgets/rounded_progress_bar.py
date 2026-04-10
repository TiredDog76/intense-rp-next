from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ui.core.brand import BrandColors


class RoundedProgressBar(QWidget):
    """Paint a rounded progress bar with the fill clipped inside the track."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 100
        self._value = 0

        self._track_color = QColor(BrandColors.SIDEBAR_BG)
        self._border_color = QColor(BrandColors.INPUT_BORDER)
        self._fill_color = QColor(BrandColors.ACCENT)

        self._border_width = 1.0
        self._inner_padding = 1.0
        self._indeterminate_offset = 0.0

        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(16)
        self._animation_timer.timeout.connect(self._advance_indeterminate)

        self.setMinimumHeight(14)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(180, 14)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(80, 14)

    def setTextVisible(self, _visible: bool) -> None:
        """Compatibility shim so existing call sites can treat this like QProgressBar."""

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = int(minimum)
        self._maximum = int(maximum)
        if self._maximum > self._minimum:
            self._value = max(self._minimum, min(self._value, self._maximum))
        self._sync_animation_state()
        self.update()

    def maximum(self) -> int:
        return self._maximum

    def minimum(self) -> int:
        return self._minimum

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        self._value = int(value)
        if self._maximum > self._minimum:
            self._value = max(self._minimum, min(self._value, self._maximum))
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._sync_animation_state()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        outer_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if outer_rect.width() <= 0 or outer_rect.height() <= 0:
            return

        outer_radius = outer_rect.height() / 2.0
        outer_path = QPainterPath()
        outer_path.addRoundedRect(outer_rect, outer_radius, outer_radius)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillPath(outer_path, self._track_color)

        inner_rect = self._inner_rect(outer_rect)
        if inner_rect.width() > 0 and inner_rect.height() > 0:
            inner_radius = min(inner_rect.height() / 2.0, inner_rect.width() / 2.0)
            inner_path = QPainterPath()
            inner_path.addRoundedRect(inner_rect, inner_radius, inner_radius)

            fill_rect = self._fill_rect(inner_rect)
            if fill_rect is not None and fill_rect.width() > 0 and fill_rect.height() > 0:
                fill_radius = min(fill_rect.height() / 2.0, fill_rect.width() / 2.0)
                fill_path = QPainterPath()
                fill_path.addRoundedRect(fill_rect, fill_radius, fill_radius)
                painter.save()
                painter.setClipPath(inner_path)
                painter.fillPath(fill_path, self._fill_color)
                painter.restore()

        border_pen = QPen(self._border_color)
        border_pen.setWidthF(self._border_width)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(outer_path)
        painter.end()

    def _sync_animation_state(self) -> None:
        should_animate = self.isVisible() and self._maximum <= self._minimum
        if should_animate:
            if not self._animation_timer.isActive():
                self._animation_timer.start()
        else:
            self._animation_timer.stop()
            self._indeterminate_offset = 0.0

    def _advance_indeterminate(self) -> None:
        outer_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        inner_rect = self._inner_rect(outer_rect)
        if inner_rect.width() <= 0:
            return

        segment_width = self._indeterminate_width(inner_rect)
        travel = inner_rect.width() + segment_width
        step = max(2.0, inner_rect.width() * 0.03)
        self._indeterminate_offset = (self._indeterminate_offset + step) % travel
        self.update()

    def _inner_rect(self, outer_rect: QRectF) -> QRectF:
        inset = self._border_width + self._inner_padding
        return outer_rect.adjusted(inset, inset, -inset, -inset)

    def _fill_rect(self, inner_rect: QRectF) -> QRectF | None:
        if self._maximum <= self._minimum:
            segment_width = self._indeterminate_width(inner_rect)
            left = inner_rect.left() - segment_width + self._indeterminate_offset
            return QRectF(left, inner_rect.top(), segment_width, inner_rect.height())

        span = self._maximum - self._minimum
        if span <= 0:
            return None

        progress = (self._value - self._minimum) / float(span)
        progress = max(0.0, min(1.0, progress))
        return QRectF(inner_rect.left(), inner_rect.top(), inner_rect.width() * progress, inner_rect.height())

    @staticmethod
    def _indeterminate_width(inner_rect: QRectF) -> float:
        return min(inner_rect.width(), max(inner_rect.height() * 2.8, inner_rect.width() * 0.3))
