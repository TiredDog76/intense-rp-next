from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PySide6.QtCore import (
    QPoint,
    Qt,
    QSize,
    Signal,
    QEvent,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
)
from PySide6.QtGui import QKeyEvent, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.core.brand import BrandColors
from ui.core.animation_settings import animations_disabled
from ui.core.icons import IconType, IconUtils
from ui.widgets.smooth_scroll_area import SmoothScrollArea


@dataclass(frozen=True)
class MarshmallowOption:
    key: str
    label: str
    icon_file: str | None = None


def _blend_hex_colors(color_a: str, color_b: str, ratio: float) -> str:
    ratio = max(0.0, min(float(ratio), 1.0))
    inv = 1.0 - ratio
    first = QColor(color_a)
    second = QColor(color_b)
    return QColor(
        int(round(first.red() * inv + second.red() * ratio)),
        int(round(first.green() * inv + second.green() * ratio)),
        int(round(first.blue() * inv + second.blue() * ratio)),
        int(round(first.alpha() * inv + second.alpha() * ratio)),
    ).name()


class _MarshmallowOptionRow(QFrame):
    selected = Signal(str)
    delete_requested = Signal(str)

    def __init__(
        self,
        option: MarshmallowOption,
        *,
        is_current: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._option = option
        self._is_current = bool(is_current)
        self.setObjectName("marshmallowOptionRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("background-color: transparent;")
        self._icon_label.setFixedSize(18, 18)
        if option.icon_file:
            pixmap = IconUtils.get_pixmap(
                option.icon_file,
                color=BrandColors.TEXT_PRIMARY,
                size=16,
                dpr=self.devicePixelRatioF(),
            )
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

        self._text_label = QLabel(option.label)
        self._text_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            font-weight: 500;
            """
        )
        layout.addWidget(self._text_label, 1, Qt.AlignVCenter)

        self._delete_button = QPushButton()
        self._delete_button.setCursor(Qt.PointingHandCursor)
        self._delete_button.setFixedSize(20, 20)
        delete_policy = self._delete_button.sizePolicy()
        delete_policy.setRetainSizeWhenHidden(True)
        self._delete_button.setSizePolicy(delete_policy)
        self._delete_button.setVisible(False)
        self._delete_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            """
        )
        self._delete_button.setIconSize(QSize(14, 14))
        self._delete_button.installEventFilter(self)
        self._refresh_delete_button_icon(hovered=False)
        self._delete_button.clicked.connect(self._emit_delete_requested)
        layout.addWidget(self._delete_button, 0, Qt.AlignVCenter)

        self._apply_style()

    def _apply_style(self) -> None:
        if self._is_current:
            background = BrandColors.CATEGORY_ACTIVE_BG
            border = BrandColors.CATEGORY_ACTIVE_BORDER
            hover = _blend_hex_colors(BrandColors.CATEGORY_ACTIVE_BG, BrandColors.ACCENT, 0.26)
        else:
            background = BrandColors.INPUT_BG
            border = BrandColors.INPUT_BORDER
            hover = BrandColors.ITEM_HOVER

        self.setStyleSheet(
            f"""
            QFrame#marshmallowOptionRow {{
                background-color: {background};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QFrame#marshmallowOptionRow:hover {{
                background-color: {hover};
                border: 1px solid {BrandColors.CATEGORY_ACTIVE_BORDER};
            }}
            """
        )

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._delete_button.setVisible(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._delete_button.setVisible(False)

    def eventFilter(self, obj, event):
        if obj is self._delete_button:
            if event.type() in {QEvent.Enter, QEvent.HoverEnter, QEvent.FocusIn}:
                self._refresh_delete_button_icon(hovered=True)
            elif event.type() in {QEvent.Leave, QEvent.HoverLeave, QEvent.FocusOut}:
                self._refresh_delete_button_icon(hovered=False)
        return super().eventFilter(obj, event)

    def _refresh_delete_button_icon(self, *, hovered: bool) -> None:
        IconUtils.apply_icon(
            self._delete_button,
            "trash-2.svg",
            BrandColors.DANGER if hovered else BrandColors.TEXT_SECONDARY,
            size=14,
            include_disabled=True,
        )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.selected.emit(self._option.key)
        super().mouseReleaseEvent(event)

    def _emit_delete_requested(self) -> None:
        self.delete_requested.emit(self._option.key)


class _MarshmallowAddRow(QWidget):
    add_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editing = False

        self.setStyleSheet("background-color: transparent;")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

        self._add_button = QPushButton("Add New Loadout")
        self._add_button.setCursor(Qt.PointingHandCursor)
        self._add_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.INPUT_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
                padding: 10px 12px;
                text-align: left;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
                font-weight: 700;
            }}
            QPushButton:hover {{
                border: 1px solid {BrandColors.ACCENT};
                background-color: {BrandColors.ITEM_HOVER};
            }}
            """
        )
        IconUtils.apply_icon(
            self._add_button,
            IconType.PLUS,
            BrandColors.TEXT_PRIMARY,
            size=14,
            include_disabled=True,
        )
        self._add_button.setIconSize(QSize(14, 14))
        self._add_button.clicked.connect(self.start_editing)
        self._layout.addWidget(self._add_button)

        self._editor_wrap = QWidget()
        self._editor_wrap.setVisible(False)
        editor_layout = QHBoxLayout(self._editor_wrap)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("New loadout name")
        self._input.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {BrandColors.INPUT_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
                font-weight: 500;
            }}
            """
        )
        self._input.returnPressed.connect(self._submit)
        editor_layout.addWidget(self._input, 1)

        self._confirm_button = QPushButton()
        self._confirm_button.setCursor(Qt.PointingHandCursor)
        self._confirm_button.setFixedSize(24, 24)
        self._confirm_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            """
        )
        IconUtils.apply_icon(
            self._confirm_button,
            IconType.CONFIRM,
            BrandColors.SUCCESS,
            size=16,
            include_disabled=True,
        )
        self._confirm_button.setIconSize(QSize(16, 16))
        self._confirm_button.clicked.connect(self._submit)
        editor_layout.addWidget(self._confirm_button, 0, Qt.AlignVCenter)

        self._layout.addWidget(self._editor_wrap)

    def start_editing(self) -> None:
        self._editing = True
        self._add_button.setVisible(False)
        self._editor_wrap.setVisible(True)
        self._input.clear()
        self._input.setFocus(Qt.PopupFocusReason)

    def reset(self) -> None:
        self._editing = False
        self._input.clear()
        self._editor_wrap.setVisible(False)
        self._add_button.setVisible(True)

    def _submit(self) -> None:
        name = str(self._input.text() or "").strip()
        if not name:
            self.reset()
            return
        self.add_requested.emit(name)
        self.reset()


class _MarshmallowPopup(QFrame):
    option_selected = Signal(str)
    add_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._options: list[MarshmallowOption] = []
        self._current_key: str | None = None
        self._pending_hide = False

        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background-color: transparent; border: none;")
        self.hide()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._panel = QFrame(self)
        self._panel.setObjectName("marshmallowPopupPanel")
        self._panel.setAttribute(Qt.WA_StyledBackground, True)
        self._panel.setStyleSheet(
            f"""
            QFrame#marshmallowPopupPanel {{
                background-color: {BrandColors.WINDOW_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 10px;
            }}
            """
        )
        outer_layout.addWidget(self._panel)

        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(150)
        self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(150)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(self._pos_anim)
        self._anim_group.addAnimation(self._opacity_anim)
        self._anim_group.finished.connect(self._on_animation_finished)

        layout = QVBoxLayout(self._panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._scroll = SmoothScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            """
        )

        self._content = QWidget()
        self._content.setStyleSheet("background-color: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 10, 0)
        self._content_layout.setSpacing(8)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        self._add_row = _MarshmallowAddRow()
        self._add_row.add_requested.connect(self._emit_add_requested)
        layout.addWidget(self._add_row)

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
        self.repaint()
        QApplication.processEvents()

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

    def set_options(self, options: list[MarshmallowOption], current_key: str | None) -> None:
        self._options = list(options or [])
        self._current_key = str(current_key or "").strip() or None
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for option in self._options:
            row = _MarshmallowOptionRow(
                option,
                is_current=option.key == self._current_key,
            )
            row.selected.connect(self._emit_option_selected)
            row.delete_requested.connect(self._confirm_delete)
            self._content_layout.addWidget(row)

        self._content_layout.addStretch(1)
        self._add_row.reset()

    def _emit_option_selected(self, key: str) -> None:
        self.option_selected.emit(key)
        self.animate_hide()

    def _emit_add_requested(self, name: str) -> None:
        self.add_requested.emit(name)
        self.animate_hide()

    def _confirm_delete(self, key: str) -> None:
        option = next((item for item in self._options if item.key == key), None)
        label = option.label if option is not None else key
        owner = self.parentWidget().window() if self.parentWidget() is not None else self
        reply = QMessageBox.question(
            owner,
            "Delete Loadout",
            "Are you sure you want to delete this loadout?\n\n"
            f"{label}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.delete_requested.emit(key)
        self.animate_hide()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.animate_hide()
            event.accept()
            return
        super().keyPressEvent(event)


class _MarshmallowMultiSelectOptionRow(QFrame):
    toggled = Signal(str)

    def __init__(
        self,
        option: MarshmallowOption,
        *,
        selected: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._option = option
        self._selected = bool(selected)
        self.setObjectName("marshmallowMultiSelectOptionRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("background-color: transparent;")
        self._icon_label.setFixedSize(18, 18)
        if option.icon_file:
            pixmap = IconUtils.get_pixmap(
                option.icon_file,
                color=BrandColors.TEXT_PRIMARY,
                size=16,
                dpr=self.devicePixelRatioF(),
            )
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

        self._text_label = QLabel(option.label)
        self._text_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            font-weight: 500;
            """
        )
        layout.addWidget(self._text_label, 1, Qt.AlignVCenter)

        self._check_label = QLabel()
        self._check_label.setStyleSheet("background-color: transparent;")
        self._check_label.setFixedSize(18, 18)
        self._check_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._check_label, 0, Qt.AlignVCenter)

        self._refresh_check_icon()
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        next_selected = bool(selected)
        if next_selected == self._selected:
            return
        self._selected = next_selected
        self._refresh_check_icon()
        self._apply_style()

    def _refresh_check_icon(self) -> None:
        if not self._selected:
            self._check_label.clear()
            return

        pixmap = IconUtils.get_pixmap(
            IconType.CONFIRM,
            color=BrandColors.TEXT_PRIMARY,
            size=16,
            dpr=self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            self._check_label.setPixmap(pixmap)

    def _apply_style(self) -> None:
        if self._selected:
            background = BrandColors.CATEGORY_ACTIVE_BG
            border = BrandColors.CATEGORY_ACTIVE_BORDER
            hover = _blend_hex_colors(BrandColors.CATEGORY_ACTIVE_BG, BrandColors.ACCENT, 0.26)
        else:
            background = BrandColors.INPUT_BG
            border = BrandColors.INPUT_BORDER
            hover = BrandColors.ITEM_HOVER

        self.setStyleSheet(
            f"""
            QFrame#marshmallowMultiSelectOptionRow {{
                background-color: {background};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QFrame#marshmallowMultiSelectOptionRow:hover {{
                background-color: {hover};
                border: 1px solid {BrandColors.CATEGORY_ACTIVE_BORDER};
            }}
            """
        )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.toggled.emit(self._option.key)
        super().mouseReleaseEvent(event)


class _MarshmallowMultiSelectPopup(QFrame):
    selection_changed = Signal(list)

    def __init__(self, parent=None, *, title: str | None = None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._title = str(title or "").strip()
        self._options: list[MarshmallowOption] = []
        self._selected_keys: set[str] = set()
        self._pending_hide = False

        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background-color: transparent; border: none;")
        self.hide()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._panel = QFrame(self)
        self._panel.setObjectName("marshmallowMultiSelectPopupPanel")
        self._panel.setAttribute(Qt.WA_StyledBackground, True)
        self._panel.setStyleSheet(
            f"""
            QFrame#marshmallowMultiSelectPopupPanel {{
                background-color: {BrandColors.WINDOW_BG};
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 10px;
            }}
            """
        )
        outer_layout.addWidget(self._panel)

        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._pos_anim.setDuration(150)
        self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(150)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(self._pos_anim)
        self._anim_group.addAnimation(self._opacity_anim)
        self._anim_group.finished.connect(self._on_animation_finished)

        layout = QVBoxLayout(self._panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        if self._title:
            title_label = QLabel(self._title)
            title_label.setWordWrap(True)
            title_label.setStyleSheet(
                f"""
                color: {BrandColors.TEXT_PRIMARY};
                background-color: transparent;
                font-size: {BrandColors.FONT_SIZE_LARGE};
                font-family: {BrandColors.FONT_FAMILY};
                font-weight: 800;
                padding: 0px 2px 4px 2px;
                """
            )
            layout.addWidget(title_label)

        self._scroll = SmoothScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            """
        )

        self._content = QWidget()
        self._content.setStyleSheet("background-color: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 10, 0)
        self._content_layout.setSpacing(8)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

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
        self.repaint()
        QApplication.processEvents()

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

    def set_options(self, options: list[MarshmallowOption], selected_keys: Iterable[str] | None) -> None:
        self._options = list(options or [])
        valid_keys = {option.key for option in self._options}
        self._selected_keys = {
            key
            for key in self._normalize_keys(selected_keys)
            if key in valid_keys
        }
        self._rebuild_rows()

    def selected_keys(self) -> list[str]:
        return self._ordered_selected_keys()

    def _normalize_keys(self, keys: Iterable[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for key in keys or []:
            safe = str(key or "").strip()
            if not safe or safe in seen:
                continue
            normalized.append(safe)
            seen.add(safe)
        return normalized

    def _ordered_selected_keys(self) -> list[str]:
        return [option.key for option in self._options if option.key in self._selected_keys]

    def _rebuild_rows(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for option in self._options:
            row = _MarshmallowMultiSelectOptionRow(
                option,
                selected=option.key in self._selected_keys,
            )
            row.toggled.connect(self._toggle_option)
            self._content_layout.addWidget(row)

        self._content_layout.addStretch(1)

    def _toggle_option(self, key: str) -> None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return
        if normalized_key in self._selected_keys:
            self._selected_keys.remove(normalized_key)
        else:
            self._selected_keys.add(normalized_key)
        self._rebuild_rows()
        self.selection_changed.emit(self._ordered_selected_keys())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.animate_hide()
            event.accept()
            return
        super().keyPressEvent(event)


class MarshmallowDropdown(QFrame):
    currentKeyChanged = Signal(str)
    addRequested = Signal(str)
    deleteRequested = Signal(str)

    def __init__(self, parent=None, *, placeholder: str = "Choose a loadout"):
        super().__init__(parent)
        self._placeholder = str(placeholder or "Choose a loadout")
        self._options: list[MarshmallowOption] = []
        self._current_key: str | None = None
        self._consume_release = False
        self._popup: _MarshmallowPopup | None = None

        self.setObjectName("marshmallowDropdown")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"""
            QFrame#marshmallowDropdown {{
                background-color: {BrandColors.INPUT_BG};
                border: 2px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
            }}
            QFrame#marshmallowDropdown:hover {{
                border: 2px solid {BrandColors.ACCENT};
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("background-color: transparent;")
        self._icon_label.setFixedSize(18, 18)
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

        self._text_label = QLabel(self._placeholder)
        self._text_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            font-weight: 500;
            """
        )
        layout.addWidget(self._text_label, 1, Qt.AlignVCenter)

        self._chevron_label = QLabel()
        self._chevron_label.setStyleSheet("background-color: transparent;")
        self._chevron_label.setFixedSize(16, 16)
        chevron = IconUtils.get_pixmap(
            "chevron-down.svg",
            color=BrandColors.TEXT_SECONDARY,
            size=16,
            dpr=self.devicePixelRatioF(),
        )
        if not chevron.isNull():
            self._chevron_label.setPixmap(chevron)
        layout.addWidget(self._chevron_label, 0, Qt.AlignVCenter)

        self._refresh_display()

    def set_options(self, options: list[MarshmallowOption], current_key: str | None = None) -> None:
        self._options = list(options or [])
        if current_key is not None:
            normalized_key = str(current_key or "").strip() or None
            self._current_key = normalized_key
        elif self._current_key and not any(option.key == self._current_key for option in self._options):
            self._current_key = None
        self._refresh_display()
        if self._popup is not None:
            self._popup.set_options(self._options, self._current_key)

    def set_current_key(self, key: str | None) -> None:
        normalized_key = str(key or "").strip() or None
        self._current_key = normalized_key
        self._refresh_display()
        if self._popup is not None:
            self._popup.set_options(self._options, self._current_key)

    def current_key(self) -> str | None:
        return self._current_key

    def _refresh_display(self) -> None:
        current = next((option for option in self._options if option.key == self._current_key), None)
        if current is None:
            self._text_label.setText(self._placeholder)
            self._icon_label.clear()
            self._text_label.setStyleSheet(
                f"""
                color: {BrandColors.TEXT_SECONDARY};
                background-color: transparent;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
                font-weight: 500;
                """
            )
            return

        self._text_label.setText(current.label)
        self._text_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            font-weight: 500;
            """
        )

        if current.icon_file:
            pixmap = IconUtils.get_pixmap(
                current.icon_file,
                color=BrandColors.TEXT_PRIMARY,
                size=16,
                dpr=self.devicePixelRatioF(),
            )
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
                return
        self._icon_label.clear()

    def _ensure_popup(self) -> _MarshmallowPopup:
        if self._popup is None:
            self._popup = _MarshmallowPopup(self)
            self._popup.option_selected.connect(self._on_popup_option_selected)
            self._popup.add_requested.connect(self.addRequested.emit)
            self._popup.delete_requested.connect(self.deleteRequested.emit)
        return self._popup

    def mouseReleaseEvent(self, event) -> None:
        if self._consume_release:
            self._consume_release = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self._consume_release = True
            self.toggle_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def toggle_popup(self) -> None:
        popup = self._ensure_popup()
        if popup.isVisible():
            popup.animate_hide()
            return

        popup.set_options(self._options, self._current_key)
        popup_width = max(self.width(), 300)
        visible_rows = max(3, min(max(len(self._options), 0), 6))
        popup_height = 92 + (visible_rows * 52)
        popup.resize(popup_width, min(420, max(232, popup_height)))
        popup_pos = self.mapToGlobal(QPoint(0, self.height() + 6))

        app = QApplication.instance()
        if app is not None:
            screen = app.screenAt(popup_pos) or app.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                if popup_pos.x() + popup_width > available.right():
                    popup_pos.setX(max(available.left(), available.right() - popup_width))
                if popup_pos.y() + popup.height() > available.bottom():
                    popup_pos.setY(max(available.top(), self.mapToGlobal(QPoint(0, -popup.height() - 6)).y()))

        popup.animate_show(popup_pos)

    def _on_popup_option_selected(self, key: str) -> None:
        normalized_key = str(key or "").strip() or None
        self._current_key = normalized_key
        self._refresh_display()
        if normalized_key is not None:
            self.currentKeyChanged.emit(normalized_key)


class MarshmallowMultiSelectDropdown(QFrame):
    selectionChanged = Signal(list)

    def __init__(
        self,
        parent=None,
        *,
        placeholder: str = "Select items",
        button_icon_file: str | None = None,
        popup_title: str | None = None,
        summary_formatter: Callable[[int], str] | None = None,
    ):
        super().__init__(parent)
        self._placeholder = str(placeholder or "Select items")
        self._button_icon_file = str(button_icon_file or "").strip() or None
        self._popup_title = str(popup_title or "").strip() or None
        self._summary_formatter = summary_formatter
        self._options: list[MarshmallowOption] = []
        self._selected_keys: list[str] = []
        self._consume_release = False
        self._popup: _MarshmallowMultiSelectPopup | None = None

        self.setObjectName("marshmallowMultiSelectDropdown")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"""
            QFrame#marshmallowMultiSelectDropdown {{
                background-color: {BrandColors.INPUT_BG};
                border: 2px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
            }}
            QFrame#marshmallowMultiSelectDropdown:hover {{
                border: 2px solid {BrandColors.ACCENT};
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("background-color: transparent;")
        self._icon_label.setFixedSize(18, 18)
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

        self._text_label = QLabel(self._placeholder)
        self._text_label.setMinimumWidth(0)
        self._text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._text_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            font-weight: 500;
            """
        )
        layout.addWidget(self._text_label, 1, Qt.AlignVCenter)

        self._chevron_label = QLabel()
        self._chevron_label.setStyleSheet("background-color: transparent;")
        self._chevron_label.setFixedSize(16, 16)
        chevron = IconUtils.get_pixmap(
            "chevron-down.svg",
            color=BrandColors.TEXT_SECONDARY,
            size=16,
            dpr=self.devicePixelRatioF(),
        )
        if not chevron.isNull():
            self._chevron_label.setPixmap(chevron)
        layout.addWidget(self._chevron_label, 0, Qt.AlignVCenter)

        self._refresh_display()

    def set_summary_formatter(self, formatter: Callable[[int], str] | None) -> None:
        self._summary_formatter = formatter
        self._refresh_display()

    def set_options(
        self,
        options: list[MarshmallowOption],
        selected_keys: Iterable[str] | None = None,
    ) -> None:
        self._options = list(options or [])
        valid_keys = {option.key for option in self._options}
        if selected_keys is None:
            next_keys = [key for key in self._selected_keys if key in valid_keys]
        else:
            next_keys = [
                key
                for key in self._normalize_keys(selected_keys)
                if key in valid_keys
            ]
        self._selected_keys = self._order_selected_keys(next_keys)
        self._refresh_display()
        if self._popup is not None:
            self._popup.set_options(self._options, self._selected_keys)

    def set_selected_keys(self, keys: Iterable[str] | None) -> None:
        valid_keys = {option.key for option in self._options}
        self._selected_keys = self._order_selected_keys(
            key
            for key in self._normalize_keys(keys)
            if key in valid_keys
        )
        self._refresh_display()
        if self._popup is not None:
            self._popup.set_options(self._options, self._selected_keys)

    def selected_keys(self) -> list[str]:
        return list(self._selected_keys)

    def _normalize_keys(self, keys: Iterable[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for key in keys or []:
            safe = str(key or "").strip()
            if not safe or safe in seen:
                continue
            normalized.append(safe)
            seen.add(safe)
        return normalized

    def _order_selected_keys(self, keys: Iterable[str]) -> list[str]:
        selected = set(self._normalize_keys(keys))
        return [option.key for option in self._options if option.key in selected]

    def _summary_text(self) -> str:
        count = len(self._selected_keys)
        if self._summary_formatter is not None:
            return str(self._summary_formatter(count) or self._placeholder)

        if count == 0:
            return self._placeholder
        if count == 1:
            selected_key = self._selected_keys[0]
            option = next((item for item in self._options if item.key == selected_key), None)
            if option is not None:
                return option.label
        return f"{count} selected"

    def _refresh_display(self) -> None:
        count = len(self._selected_keys)
        self._text_label.setText(self._summary_text())
        self._text_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY if count else BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            font-weight: 500;
            """
        )

        icon_file = self._button_icon_file
        if icon_file is None and count == 1:
            selected_key = self._selected_keys[0]
            option = next((item for item in self._options if item.key == selected_key), None)
            icon_file = option.icon_file if option is not None else None

        if icon_file:
            pixmap = IconUtils.get_pixmap(
                icon_file,
                color=BrandColors.TEXT_PRIMARY if count else BrandColors.TEXT_SECONDARY,
                size=16,
                dpr=self.devicePixelRatioF(),
            )
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
                return
        self._icon_label.clear()

    def _ensure_popup(self) -> _MarshmallowMultiSelectPopup:
        if self._popup is None:
            self._popup = _MarshmallowMultiSelectPopup(self, title=self._popup_title)
            self._popup.selection_changed.connect(self._on_popup_selection_changed)
        return self._popup

    def mouseReleaseEvent(self, event) -> None:
        if self._consume_release:
            self._consume_release = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self._consume_release = True
            self.toggle_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def toggle_popup(self) -> None:
        popup = self._ensure_popup()
        if popup.isVisible():
            popup.animate_hide()
            return

        popup.set_options(self._options, self._selected_keys)
        popup_width = max(self.width(), 300)
        visible_rows = max(3, min(max(len(self._options), 0), 6))
        title_extra = 36 if self._popup_title else 0
        popup_height = 24 + title_extra + (visible_rows * 52)
        popup.resize(popup_width, min(380, max(180, popup_height)))
        popup_pos = self.mapToGlobal(QPoint(0, self.height() + 6))

        app = QApplication.instance()
        if app is not None:
            screen = app.screenAt(popup_pos) or app.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                if popup_pos.x() + popup_width > available.right():
                    popup_pos.setX(max(available.left(), available.right() - popup_width))
                if popup_pos.y() + popup.height() > available.bottom():
                    popup_pos.setY(max(available.top(), self.mapToGlobal(QPoint(0, -popup.height() - 6)).y()))

        popup.animate_show(popup_pos)

    def _on_popup_selection_changed(self, keys: list[str]) -> None:
        self._selected_keys = self._order_selected_keys(keys)
        self._refresh_display()
        self.selectionChanged.emit(self.selected_keys())
