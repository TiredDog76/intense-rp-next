from PySide6.QtWidgets import QScrollArea
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, QPoint


class SmoothScrollArea(QScrollArea):
    """
    QScrollArea with interpolated (smooth) scrolling.

    Wheel events are intercepted and animated via QPropertyAnimation
    instead of jumping instantly, giving a modern scroll feel.
    """

    SCROLL_DURATION_MS = 350
    SCROLL_STEP_PX = 80  # base pixels per wheel notch (120 delta units)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll_animation = QPropertyAnimation(self, b"vscroll_pos")
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.setDuration(self.SCROLL_DURATION_MS)

        self._target_value = 0

    def smooth_scroll_to(self, target_value: int, *, duration_ms: int | None = None) -> bool:
        v_bar = self.verticalScrollBar()
        target_value = int(target_value)
        target_value = max(v_bar.minimum(), min(target_value, v_bar.maximum()))

        start_value = int(v_bar.value())
        if start_value == target_value:
            return False

        self._target_value = target_value
        self._scroll_animation.stop()
        self._scroll_animation.setDuration(self.SCROLL_DURATION_MS if duration_ms is None else int(duration_ms))
        self._scroll_animation.setStartValue(start_value)
        self._scroll_animation.setEndValue(target_value)
        self._scroll_animation.start()
        return True

    def smooth_ensure_widget_visible(
        self,
        child_widget,
        *,
        y_margin: int = 50,
        duration_ms: int | None = None,
    ) -> bool:
        if child_widget is None:
            return False

        viewport = self.viewport()
        v_bar = self.verticalScrollBar()
        current = int(v_bar.value())

        top_left = child_widget.mapTo(viewport, QPoint(0, 0))
        top = int(top_left.y())

        height = int(child_widget.height())
        if height <= 0:
            try:
                height = int(child_widget.sizeHint().height())
            except Exception:
                height = 0

        bottom = top + height
        view_h = int(viewport.height())
        y_margin = max(0, int(y_margin))

        target = current
        if top < y_margin:
            target = current + top - y_margin
        elif bottom > view_h - y_margin:
            target = current + bottom - (view_h - y_margin)

        target = max(v_bar.minimum(), min(int(target), v_bar.maximum()))
        return self.smooth_scroll_to(target, duration_ms=duration_ms)

    # (this qt property is used by the animation to get/set scroll position)
    # -----------------------------------------------

    def _get_vscroll_pos(self) -> int:
        return self.verticalScrollBar().value()

    def _set_vscroll_pos(self, value: int):
        self.verticalScrollBar().setValue(int(value))

    vscroll_pos = Property(int, _get_vscroll_pos, _set_vscroll_pos)

    # -----------------------------------------------
    # (end)

    def wheelEvent(self, event):
        # +/-120 per notch
        delta = event.angleDelta().y()
        if delta == 0:
            # DON'T do that for horizontal scroll
            super().wheelEvent(event)
            return

        v_bar = self.verticalScrollBar()

        if self._scroll_animation.state() != QPropertyAnimation.Running:
            self._target_value = v_bar.value()

        #  convert wheel delta into pixel offset
        # Negative delta = scroll down, positive = scroll up
        pixels = -int(delta / 120.0 * self.SCROLL_STEP_PX)
        self._target_value = max(
            v_bar.minimum(),
            min(self._target_value + pixels, v_bar.maximum()),
        )

        # start animation from current position to new target
        # essentially a restart if already running
        self._scroll_animation.stop()
        self._scroll_animation.setDuration(self.SCROLL_DURATION_MS)
        self._scroll_animation.setStartValue(v_bar.value())
        self._scroll_animation.setEndValue(self._target_value)
        self._scroll_animation.start()

        event.accept()
