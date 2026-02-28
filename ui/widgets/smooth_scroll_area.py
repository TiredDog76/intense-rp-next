from PySide6.QtWidgets import QScrollArea
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve


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
        self._scroll_animation.setStartValue(v_bar.value())
        self._scroll_animation.setEndValue(self._target_value)
        self._scroll_animation.start()

        event.accept()
