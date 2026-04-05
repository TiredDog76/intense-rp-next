from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from ui.core.animation_settings import animations_disabled
from ui.core.brand import BrandColors
from ui.core.icons import IconUtils


@dataclass(frozen=True)
class IconOptionMenuItem:
    key: str
    label: str
    icon_file: str | None = None
    danger: bool = False


class _IconOptionMenuRow(QFrame):
    triggered = Signal(str)

    def __init__(self, item: IconOptionMenuItem, parent=None) -> None:
        super().__init__(parent)
        self._item = item
        self.setObjectName("iconOptionMenuRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("background-color: transparent;")
        self._icon_label.setFixedSize(18, 18)
        if item.icon_file:
            pixmap = IconUtils.get_pixmap(
                item.icon_file,
                color=BrandColors.DANGER if item.danger else BrandColors.TEXT_PRIMARY,
                size=16,
                dpr=self.devicePixelRatioF(),
            )
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

        self._text_label = QLabel(item.label)
        self._text_label.setStyleSheet(
            f"""
            color: {BrandColors.DANGER if item.danger else BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            font-weight: 500;
            """
        )
        layout.addWidget(self._text_label, 1, Qt.AlignVCenter)

        hover_border = BrandColors.DANGER if item.danger else BrandColors.CATEGORY_ACTIVE_BORDER
        self.setStyleSheet(
            f"""
            QFrame#iconOptionMenuRow {{
                background-color: {BrandColors.INPUT_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
            }}
            QFrame#iconOptionMenuRow:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {hover_border};
            }}
            """
        )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.triggered.emit(self._item.key)
        super().mouseReleaseEvent(event)


class IconOptionMenu(QFrame):
    actionTriggered = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self._items: list[IconOptionMenuItem] = []
        self._pending_hide = False

        self.setObjectName("iconOptionMenu")
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.hide()
        self.setStyleSheet(
            f"""
            QFrame#iconOptionMenu {{
                background-color: {BrandColors.WINDOW_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 10px;
            }}
            """
        )

        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(140)
        self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(140)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(self._pos_anim)
        self._anim_group.addAnimation(self._opacity_anim)
        self._anim_group.finished.connect(self._on_animation_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        layout.addLayout(self._content_layout)

    def set_items(self, items: list[IconOptionMenuItem]) -> None:
        self._items = list(items or [])
        self._rebuild_rows()

    def toggle_for(self, anchor) -> None:
        if self.isVisible():
            self.animate_hide()
            return
        self.popup_for(anchor)

    def popup_for(self, anchor) -> None:
        if anchor is None:
            return

        self._rebuild_rows()
        hint = self.sizeHint()
        popup_width = max(168, int(hint.width()))
        popup_height = max(68, int(hint.height()))
        self.resize(popup_width, popup_height)

        popup_pos = anchor.mapToGlobal(QPoint(anchor.width() - popup_width, anchor.height() + 6))

        app = QApplication.instance()
        if app is not None:
            screen = app.screenAt(popup_pos) or app.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                if popup_pos.x() < available.left():
                    popup_pos.setX(available.left())
                if popup_pos.x() + popup_width > available.right():
                    popup_pos.setX(max(available.left(), available.right() - popup_width))
                if popup_pos.y() + popup_height > available.bottom():
                    above_y = anchor.mapToGlobal(QPoint(anchor.width() - popup_width, -popup_height - 6)).y()
                    popup_pos.setY(max(available.top(), above_y))

        self.animate_show(popup_pos)

    def animate_show(self, final_pos: QPoint) -> None:
        self._anim_group.stop()
        self._pending_hide = False
        self.setEnabled(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        if animations_disabled():
            self.setWindowOpacity(1.0)
            self.move(final_pos)
            self.show()
            self.raise_()
            return

        start_pos = QPoint(final_pos.x(), final_pos.y() - 8)
        self.setWindowOpacity(0.0)
        self.move(start_pos)
        self.show()
        self.raise_()

        self._pos_anim.setStartValue(start_pos)
        self._pos_anim.setEndValue(final_pos)
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._anim_group.start()

    def animate_hide(self) -> None:
        if not self.isVisible():
            return

        self._anim_group.stop()
        self.setEnabled(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        if animations_disabled():
            self.hide()
            self.setEnabled(True)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.setWindowOpacity(1.0)
            return

        current_pos = self.pos()
        end_pos = QPoint(current_pos.x(), current_pos.y() - 8)
        self._pending_hide = True
        self._pos_anim.setStartValue(current_pos)
        self._pos_anim.setEndValue(end_pos)
        self._opacity_anim.setStartValue(float(self.windowOpacity()))
        self._opacity_anim.setEndValue(0.0)
        self._anim_group.start()

    def _on_animation_finished(self) -> None:
        if not self._pending_hide:
            return
        self._pending_hide = False
        self.hide()
        self.setEnabled(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setWindowOpacity(1.0)

    def _rebuild_rows(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for item in self._items:
            row = _IconOptionMenuRow(item, self)
            row.triggered.connect(self._emit_action)
            self._content_layout.addWidget(row)

    def _emit_action(self, key: str) -> None:
        self.actionTriggered.emit(key)
        self.animate_hide()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.animate_hide()
            event.accept()
            return
        super().keyPressEvent(event)
