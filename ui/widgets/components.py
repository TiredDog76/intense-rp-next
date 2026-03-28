from PySide6.QtWidgets import QCheckBox, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QFrame, QPushButton, QSizePolicy, QFileDialog, QStyle, QStyleOptionComboBox, QToolButton
from PySide6.QtCore import Property, QSize, Qt, QRect, Signal, QEvent, QPropertyAnimation, QEasingCurve, QAbstractAnimation
import html
import os
from pathlib import Path
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QIcon, QTextCursor
from ui.core.brand import BrandColors
from ui.core.animation_settings import animations_disabled
from ui.core.icons import IconUtils, IconType


class DocsHelpButton(QToolButton):
    """
    Tiny icon-only button used to open a setting's docs entry.
    """

    def __init__(self, docs_url: str, parent=None):
        super().__init__(parent)
        self._docs_url = str(docs_url or "").strip()
        size_policy = self.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        self.setSizePolicy(size_policy)

        self.setProperty("docsUrl", self._docs_url)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoRaise(True)
        self.setToolTip("Open docs for this setting (F1)")
        self.setAccessibleName("Open docs for this setting")
        self.setFixedSize(16, 16)
        self.setIconSize(QSize(12, 12))
        self.setStyleSheet(
            f"""
            QToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                padding: 0px;
            }}
            QToolButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            QToolButton:focus {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            """
        )
        self._update_icon()

    def _icon_color(self) -> str:
        if not self.isEnabled():
            return BrandColors.TEXT_DISABLED
        if self.hasFocus() or self.underMouse():
            return BrandColors.ACCENT
        return BrandColors.TEXT_SECONDARY

    def _update_icon(self) -> None:
        icon = IconUtils.get_icon(
            IconType.HELP,
            color=self._icon_color(),
            size=12,
            widget=self,
        )
        if not icon.isNull():
            self.setIcon(icon)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._update_icon()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._update_icon()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._update_icon()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._update_icon()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._update_icon()

class MultiColumnRow(QWidget):
    def __init__(self, widgets, ratios=None, spacing=10, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        
        self.widgets = widgets
        
        for i, widget in enumerate(widgets):
            ratio = ratios[i] if ratios and i < len(ratios) else 1
            layout.addWidget(widget, stretch=ratio)


class _SettingsTextEdit(QTextEdit):
    """
    QTextEdit variant that preserves normal form navigation inside settings.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabChangesFocus(True)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.NoModifier:
            if event.key() == Qt.Key_Up and self._try_move_focus(QTextCursor.Up, forward=False):
                event.accept()
                return
            if event.key() == Qt.Key_Down and self._try_move_focus(QTextCursor.Down, forward=True):
                event.accept()
                return
        super().keyPressEvent(event)

    def _try_move_focus(self, direction, *, forward: bool) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False

        probe = self.textCursor()
        if probe.movePosition(direction):
            return False
        return bool(self.focusNextPrevChild(forward))


class StyledTextEdit(QFrame):
    textChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        self.setCursor(Qt.IBeamCursor)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        
        # Inner Editor
        self.editor = _SettingsTextEdit(self)
        self.editor.setFrameShape(QFrame.NoFrame)
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.editor.textChanged.connect(self.textChanged.emit)
        self.editor.installEventFilter(self) # For focus tracking
        
        layout.addWidget(self.editor)
        
        self._has_focus = False
        self._update_style()
        
    def eventFilter(self, obj, event):
        if obj == self.editor:
            if event.type() == QEvent.FocusIn:
                self._has_focus = True
                self._update_style()
            elif event.type() == QEvent.FocusOut:
                self._has_focus = False
                self._update_style()
        return super().eventFilter(obj, event)
        
    def _update_style(self):
        border_color = BrandColors.ACCENT if self._has_focus else BrandColors.INPUT_BORDER
        bg_color = BrandColors.INPUT_BG
        
        self.setStyleSheet(f"""
            StyledTextEdit {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 6px;
            }}
        """)
        
        # Inner editor style
        self.editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
                selection-background-color: {BrandColors.ACCENT};
                selection-color: {BrandColors.TEXT_PRIMARY};
            }}
            QTextEdit:disabled {{
                color: {BrandColors.TEXT_DISABLED};
            }}
        """)

    def setPlainText(self, text):
        self.editor.setPlainText(text)
        
    def toPlainText(self):
        return self.editor.toPlainText()
        
    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.editor.setEnabled(enabled)
        # Update opacity or style if needed
        if not enabled:
            self.setStyleSheet(f"""
                StyledTextEdit {{
                    background-color: {BrandColors.INPUT_BG};
                    border: 2px solid {BrandColors.INPUT_BORDER};
                    border-radius: 6px;
                    opacity: 0.6;
                }}
            """)
        else:
            self._update_style()

class StyledComboBox(QComboBox):
    popupAboutToShow = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        # Disable scroll wheel changing values
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {BrandColors.INPUT_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 2px solid {BrandColors.INPUT_BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QComboBox:hover {{
                border: 2px solid {BrandColors.ITEM_HOVER};
            }}
            QComboBox:focus {{
                border: 2px solid {BrandColors.ACCENT};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 0px;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
            QComboBox::down-arrow {{
                /* Custom-painted in paintEvent to support currentColor icons */
                image: none;
                width: 16px;
                height: 16px;
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BrandColors.INPUT_BG};
                color: {BrandColors.TEXT_PRIMARY};
                selection-background-color: {BrandColors.ACCENT};
                selection-color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.INPUT_BORDER};
                outline: none;
            }}
        """)
    
    def wheelEvent(self, event):
        # Ignore wheel events to prevent accidental value changes when scrolling
        event.ignore()

    def showPopup(self):
        self.popupAboutToShow.emit()
        super().showPopup()

    def paintEvent(self, event):
        super().paintEvent(event)

        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        arrow_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, self)
        if arrow_rect.isNull():
            return

        icon_color = BrandColors.TEXT_SECONDARY if self.isEnabled() else BrandColors.TEXT_DISABLED
        pixmap = IconUtils.get_pixmap(
            "chevron-down.svg",
            color=icon_color,
            size=16,
            dpr=self.devicePixelRatioF(),
        )
        if pixmap.isNull():
            return

        dpr = float(pixmap.devicePixelRatio() or 1.0)
        logical_w = pixmap.width() / dpr
        logical_h = pixmap.height() / dpr
        x = arrow_rect.center().x() - (logical_w / 2)
        y = arrow_rect.center().y() - (logical_h / 2)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(int(round(x)), int(round(y)), pixmap)
        painter.end()


class Divider(QWidget):
    def __init__(self, text=None, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 12)
        layout.setSpacing(12)
        
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        line1.setFixedHeight(1)
        line1.setStyleSheet(f"background-color: {BrandColors.INPUT_BORDER}; border: none;")
        layout.addWidget(line1)
        
        if text:
            label = QLabel(text)
            label.setStyleSheet(f"""
                color: {BrandColors.TEXT_PRIMARY}; 
                font-weight: 600; 
                font-size: {BrandColors.FONT_SIZE_LARGE};
                letter-spacing: 0.5px;
            """)
            label.setAlignment(Qt.AlignVCenter | Qt.AlignCenter)
            label.setContentsMargins(0, 2, 0, 2)
            label.setMinimumHeight(24)
            label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            layout.addWidget(label)
            
            line2 = QFrame()
            line2.setFrameShape(QFrame.HLine)
            line2.setFrameShadow(QFrame.Sunken)
            line2.setFixedHeight(1)
            line2.setStyleSheet(f"background-color: {BrandColors.INPUT_BORDER}; border: none;")
            layout.addWidget(line2)

        self.setMinimumHeight(layout.sizeHint().height())


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


class HintCard(QFrame):
    VARIANT_STYLES = {
        "info": {"accent": BrandColors.ACCENT, "icon": "info.svg"},
        "warn": {"accent": BrandColors.WARNING, "icon": "alert-triangle.svg"},
        "danger": {"accent": BrandColors.DANGER, "icon": "alert-triangle.svg"},
        "success": {"accent": BrandColors.SUCCESS, "icon": "check.svg"},
    }

    def __init__(self, title: str, text: str, variant: str = "info", parent=None):
        super().__init__(parent)
        self.setObjectName("hintCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        palette = self._resolve_palette(variant)
        self.setStyleSheet(
            f"""
            QFrame#hintCard {{
                background-color: {palette["bg"]};
                border: 1px solid {palette["border"]};
                border-radius: 8px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setStyleSheet("background-color: transparent;")
        icon_label.setFixedSize(18, 18)
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        pixmap = IconUtils.get_pixmap(
            palette["icon"],
            color=palette["accent"],
            size=18,
            dpr=self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap)
        layout.addWidget(icon_label, 0, Qt.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        title_text = str(title or "").strip()
        if title_text:
            title_label = QLabel(title_text)
            title_label.setStyleSheet(
                f"""
                color: {palette["title"]};
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 700;
                background-color: transparent;
                """
            )
            text_layout.addWidget(title_label)

        body_label = QLabel("" if text is None else str(text))
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body_label.setStyleSheet(
            f"""
            color: {palette["text"]};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            background-color: transparent;
            """
        )
        text_layout.addWidget(body_label)
        layout.addLayout(text_layout, 1)

    def _resolve_palette(self, variant: str) -> dict[str, str]:
        resolved_variant = str(variant or "info").strip().lower()
        style = self.VARIANT_STYLES.get(resolved_variant, self.VARIANT_STYLES["info"])
        accent = style["accent"]
        return {
            "accent": accent,
            "icon": style["icon"],
            "bg": _blend_hex_colors(BrandColors.SIDEBAR_BG, accent, 0.22),
            "border": _blend_hex_colors(BrandColors.SIDEBAR_BG, accent, 0.52),
            "title": _blend_hex_colors("#f3f5f7", accent, 0.42),
            "text": _blend_hex_colors("#eef2f5", accent, 0.18),
        }


class Description(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setStyleSheet(f"""
            color: {BrandColors.TEXT_SECONDARY};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            padding: 5px 0;
        """)

class StyledButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.INPUT_BORDER};
                padding: 8px 16px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.ACCENT};
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.ACCENT};
            }}
            QPushButton:disabled {{
                color: {BrandColors.TEXT_DISABLED};
            }}
        """)


class Tumbler(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._handle_position = 1.0 if self.isChecked() else 0.0
        
        # Define dimensions
        self._width = 40
        self._height = 20
        self._handle_radius = 8
        self._margin = 2
        
        self._handle_anim = QPropertyAnimation(self, b"handle_position")
        self._handle_anim.setDuration(160)
        self._handle_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate_handle_position)

        self.setStyleSheet(self._get_stylesheet())

    def _get_handle_position(self) -> float:
        return float(self._handle_position)

    def _set_handle_position(self, value: float):
        value = max(0.0, min(float(value), 1.0))
        if value == self._handle_position:
            return
        self._handle_position = value
        self.update()

    handle_position = Property(float, _get_handle_position, _set_handle_position)

    @staticmethod
    def _blend_colors(a: QColor, b: QColor, t: float) -> QColor:
        t = max(0.0, min(float(t), 1.0))
        inv = 1.0 - t
        return QColor(
            int(round(a.red() * inv + b.red() * t)),
            int(round(a.green() * inv + b.green() * t)),
            int(round(a.blue() * inv + b.blue() * t)),
            int(round(a.alpha() * inv + b.alpha() * t)),
        )

    def _animate_handle_position(self, checked: bool):
        target = 1.0 if checked else 0.0
        if self._handle_anim.state() == QAbstractAnimation.Running:
            self._handle_anim.stop()
        if animations_disabled():
            self._set_handle_position(target)
            return
        self._handle_anim.setStartValue(self._handle_position)
        self._handle_anim.setEndValue(target)
        self._handle_anim.start()

    def set_dependency_mode(self, mode: str | None):
        """
        Set a visual dependency mode for the tumbler.
        Supported modes: None, "forced", "ignored".
        """
        mode_value = mode or ""
        if self.property("depMode") == mode_value:
            return
        self.setProperty("depMode", mode_value)
        self.setStyleSheet(self._get_stylesheet())
        self.update()

    def _get_stylesheet(self):
        # We use the indicator subcontrol
        return f"""
            QCheckBox {{
                spacing: 10px;
                color: {BrandColors.TEXT_PRIMARY};
            }}
            QCheckBox::indicator {{
                width: 40px;
                height: 20px;
                border-radius: 10px;
                background-color: {BrandColors.TUMBLER_BG};
            }}
            QCheckBox::indicator:checked {{
                background-color: {BrandColors.ACCENT};
            }}
            QCheckBox::indicator:unchecked:hover {{
                background-color: {BrandColors.ITEM_HOVER}; 
            }}
            QCheckBox[depMode="forced"]::indicator {{
                background-color: {BrandColors.WARNING};
            }}
            QCheckBox[depMode="forced"]::indicator:checked {{
                background-color: {BrandColors.WARNING};
            }}
            QCheckBox[depMode="forced"]::indicator:unchecked:hover {{
                background-color: {BrandColors.WARNING};
            }}
            QCheckBox[depMode="ignored"]::indicator {{
                background-color: {BrandColors.TUMBLER_BG};
            }}
            QCheckBox[depMode="ignored"]::indicator:checked {{
                background-color: {BrandColors.TUMBLER_BG};
            }}
            /* The tumbler look is achieved via custom painting in paintEvent
            */
        """
    
    # Painted implementation of the tumbler
    
    def hitButton(self, pos):
        return self.contentsRect().contains(pos)

    def sizeHint(self):
        width = self._width
        if self.text():
            width += 10 + self.fontMetrics().horizontalAdvance(self.text())
        return QSize(width, self._height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        target_pos = 1.0 if self.isChecked() else 0.0
        if animations_disabled():
            if self._handle_anim.state() == QAbstractAnimation.Running:
                self._handle_anim.stop()
            self._handle_position = target_pos
        elif self._handle_anim.state() != QAbstractAnimation.Running:
            self._handle_position = target_pos
        
        # Draw text
        if self.text():
            painter.setPen(QColor(BrandColors.TEXT_PRIMARY))
            text_rect = self.rect()
            text_rect.setLeft(self._width + 10)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
        
        # Draw track
        track_rect = QRect(0, 0, self._width, self._height)
        dep_mode = self.property("depMode") or ""
        if dep_mode == "forced":
            bg_color = QColor(BrandColors.WARNING)
        elif dep_mode == "ignored":
            bg_color = QColor(BrandColors.TUMBLER_BG)
        else:
            bg_off = QColor(BrandColors.TUMBLER_BG)
            bg_on = QColor(BrandColors.ACCENT)
            bg_color = self._blend_colors(bg_off, bg_on, self._handle_position)
            
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_rect, self._height / 2, self._height / 2)
        
        # Draw handle
        handle_color = QColor(BrandColors.TUMBLER_HANDLE)
        painter.setBrush(QBrush(handle_color))
        
        handle_d = self._handle_radius * 2
        handle_min_x = self._margin
        handle_max_x = self._width - handle_d - self._margin
        handle_x = handle_min_x + (handle_max_x - handle_min_x) * float(self._handle_position)
            
        handle_y = self._margin
        
        painter.drawEllipse(int(round(handle_x)), handle_y, handle_d, handle_d)
        painter.end()

class StyledLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._error_state = False
        self._update_style()
        
    def set_error(self, error: bool):
        self._error_state = error
        self._update_style()
        
    def _update_style(self):
        border_color = BrandColors.DANGER if self._error_state else BrandColors.INPUT_BORDER
        focus_border = BrandColors.DANGER if self._error_state else BrandColors.ACCENT
        
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BrandColors.INPUT_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 2px solid {border_color};
                border-radius: 6px;
                padding: 10px 12px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QLineEdit:focus {{
                border: 2px solid {focus_border};
            }}
            QLineEdit:disabled {{
                color: {BrandColors.TEXT_DISABLED};
                border: 2px solid {BrandColors.INPUT_BORDER};
                background-color: {BrandColors.INPUT_BG};
                opacity: 0.6;
            }}
        """)

class DirectoryEntry(QWidget):
    textChanged = Signal(str)

    def __init__(self, parent=None, button_text: str = "Browse", dialog_title: str = "Select Directory") -> None:
        super().__init__(parent)
        self._dialog_title = dialog_title
        self._error_state = False

        self.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.line_edit = StyledLineEdit()
        self.line_edit.textChanged.connect(self.textChanged.emit)

        self.browse_button = QPushButton(button_text)
        self.browse_button.setCursor(Qt.PointingHandCursor)
        self.browse_button.setFixedWidth(92)
        self._update_button_style()
        self.browse_button.clicked.connect(self._browse_directory)

        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.browse_button, 0)

        # Keep the button height aligned to the line edit for a cohesive input-like look.
        self.browse_button.setFixedHeight(self.line_edit.sizeHint().height())

    def _update_button_style(self) -> None:
        border_color = BrandColors.DANGER if self._error_state else BrandColors.INPUT_BORDER
        hover_border = BrandColors.DANGER if self._error_state else BrandColors.ACCENT
        self.browse_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 2px solid {border_color};
                padding: 8px 12px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 2px solid {hover_border};
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.ACCENT};
            }}
            QPushButton:disabled {{
                color: {BrandColors.TEXT_DISABLED};
                border: 2px solid {BrandColors.INPUT_BORDER};
                background-color: {BrandColors.SIDEBAR_BG};
                opacity: 0.6;
            }}
        """)

    def _browse_directory(self) -> None:
        start_dir = ""
        current = self.line_edit.text().strip()
        if current:
            try:
                path = Path(current).expanduser()
                if path.is_dir():
                    start_dir = str(path)
                elif path.parent.is_dir():
                    start_dir = str(path.parent)
            except Exception:
                start_dir = ""

        selected_dir = QFileDialog.getExistingDirectory(self, self._dialog_title, start_dir)
        if not selected_dir:
            return
        self.line_edit.setText(os.path.normpath(selected_dir))

    def set_error(self, error: bool) -> None:
        self._error_state = error
        self.line_edit.set_error(error)
        self._update_button_style()

    def text(self) -> str:
        return self.line_edit.text()

    def setText(self, text: str) -> None:
        self.line_edit.setText(text)

    def setPlaceholderText(self, text: str) -> None:
        self.line_edit.setPlaceholderText(text)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.line_edit.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)


class InputPairRow(QWidget):
    """A single 50/50 split input pair with a remove (X) button."""

    def __init__(self, left_text: str = "", right_text: str = "", left_placeholder: str = "", right_placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.left_input = StyledLineEdit()
        self.left_input.setPlaceholderText(left_placeholder)
        self.left_input.setText(left_text)

        self.right_input = StyledLineEdit()
        self.right_input.setPlaceholderText(right_placeholder)
        self.right_input.setText(right_text)

        layout.addWidget(self.left_input, 1)
        layout.addWidget(self.right_input, 1)

        self.remove_button = QPushButton()
        self.remove_button.setCursor(Qt.PointingHandCursor)
        self.remove_button.setFixedSize(28, 28)
        self.remove_button.setIconSize(QSize(12, 12))
        self.remove_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.DANGER};
            }}
            QPushButton:disabled {{
                border: 1px solid {BrandColors.INPUT_BORDER};
                opacity: 0.4;
            }}
        """)
        IconUtils.apply_icon(self.remove_button, IconType.CANCEL, BrandColors.TEXT_PRIMARY, size=12)

        layout.addWidget(self.remove_button, 0)

    def get_pair(self):
        return (self.left_input.text(), self.right_input.text())

    def set_pair(self, left_text: str, right_text: str):
        self.left_input.setText(left_text)
        self.right_input.setText(right_text)


class InputListRow(QWidget):
    """A single full-width input row with a remove (X) button."""

    def __init__(self, text: str = "", placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.input = StyledLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.input.setText(text)
        layout.addWidget(self.input, 1)

        self.remove_button = QPushButton()
        self.remove_button.setCursor(Qt.PointingHandCursor)
        self.remove_button.setFixedSize(28, 28)
        self.remove_button.setIconSize(QSize(12, 12))
        self.remove_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.DANGER};
            }}
            QPushButton:disabled {{
                border: 1px solid {BrandColors.INPUT_BORDER};
                opacity: 0.4;
            }}
        """)
        IconUtils.apply_icon(self.remove_button, IconType.CANCEL, BrandColors.TEXT_PRIMARY, size=12)
        layout.addWidget(self.remove_button, 0)

    def get_text(self) -> str:
        return self.input.text()

    def set_text(self, text: str) -> None:
        self.input.setText(text)


class InputPairsWidget(QWidget):
    """A vertical list of InputPairRow items with a Create New button."""

    pairsChanged = Signal()
    alternativeActionTriggered = Signal(str)

    def __init__(
        self,
        parent=None,
        left_placeholder: str = "Name",
        right_placeholder: str = "Key",
        alternative_actions: list[object] | None = None,
    ):
        super().__init__(parent)
        self._rows: list[InputPairRow] = []
        self._left_placeholder = left_placeholder
        self._right_placeholder = right_placeholder
        self._alternative_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        layout.addLayout(self._rows_layout)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)

        self.add_button = StyledButton("Create New")
        IconUtils.apply_icon(
            self.add_button,
            IconType.PLUS,
            BrandColors.TEXT_PRIMARY,
            size=14,
            include_disabled=True,
        )
        self.add_button.setIconSize(QSize(14, 14))
        # clicked(bool) passes a checked arg; ignore it.
        self.add_button.clicked.connect(lambda: self.add_pair())

        actions_row.addWidget(self.add_button, 0)

        for action_def in (alternative_actions or []):
            name = ""
            action = ""
            icon = None
            if isinstance(action_def, dict):
                name = str(action_def.get("name") or action_def.get("label") or "")
                action = str(action_def.get("action") or "")
                icon = action_def.get("icon")
            else:
                name = str(getattr(action_def, "name", "") or getattr(action_def, "label", "") or "")
                action = str(getattr(action_def, "action", "") or "")
                icon = getattr(action_def, "icon", None)

            name = name.strip()
            action = action.strip()
            if not name or not action:
                continue

            btn = StyledButton(name)
            if icon:
                btn_icon = IconUtils.get_icon(
                    str(icon),
                    color=BrandColors.TEXT_PRIMARY,
                    size=14,
                    widget=btn,
                    include_disabled=True,
                )
                if not btn_icon.isNull():
                    btn.setIcon(btn_icon)
                    btn.setIconSize(QSize(14, 14))

            # clicked(bool) passes a checked arg; ignore it
            btn.clicked.connect(
                lambda _checked=False, action_name=action: self.alternativeActionTriggered.emit(action_name)
            )
            actions_row.addWidget(btn, 0)
            self._alternative_buttons.append(btn)

        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        # Ensure at least one pair exists by default.
        self.add_pair(emit_change=False)

    def add_pair(self, left_text: str = "", right_text: str = "", emit_change: bool = True):
        row = InputPairRow(
            left_text=left_text,
            right_text=right_text,
            left_placeholder=self._left_placeholder,
            right_placeholder=self._right_placeholder
        )

        # textChanged(str) passes an argument; ignore it.
        row.left_input.textChanged.connect(lambda *_: self.pairsChanged.emit())
        row.right_input.textChanged.connect(lambda *_: self.pairsChanged.emit())
        row.remove_button.clicked.connect(lambda: self.remove_pair(row))

        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._update_remove_buttons()
        self.updateGeometry()

        if emit_change:
            self.pairsChanged.emit()

    def upsert_pair(self, left_text: str = "", right_text: str = "", emit_change: bool = True):
        for row in reversed(self._rows):
            existing_left, existing_right = row.get_pair()
            if str(existing_left).strip() or str(existing_right).strip():
                continue

            row.left_input.blockSignals(True)
            row.right_input.blockSignals(True)
            row.set_pair(left_text, right_text)
            row.left_input.blockSignals(False)
            row.right_input.blockSignals(False)

            self.updateGeometry()
            if emit_change:
                self.pairsChanged.emit()
            return

        self.add_pair(left_text=left_text, right_text=right_text, emit_change=emit_change)

    def remove_pair(self, row: InputPairRow):
        if len(self._rows) <= 1:
            return

        self._rows_layout.removeWidget(row)
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()

        self._update_remove_buttons()
        self.updateGeometry()
        self.pairsChanged.emit()

    def _update_remove_buttons(self):
        # Don't allow removing the last remaining pair.
        disable_remove = len(self._rows) <= 1
        for r in self._rows:
            r.remove_button.setEnabled(not disable_remove)

    def get_pairs(self):
        return [list(r.get_pair()) for r in self._rows]

    def set_pairs(self, pairs):
        # Clear existing rows.
        for r in self._rows:
            self._rows_layout.removeWidget(r)
            r.setParent(None)
            r.deleteLater()
        self._rows = []

        if pairs:
            for p in pairs:
                left_text = ""
                right_text = ""
                if isinstance(p, dict):
                    left_text = str(p.get("name", ""))
                    right_text = str(p.get("key", ""))
                elif isinstance(p, (list, tuple)) and len(p) >= 2:
                    left_text = str(p[0])
                    right_text = str(p[1])
                self.add_pair(left_text, right_text, emit_change=False)

        if not self._rows:
            self.add_pair(emit_change=False)

        self._update_remove_buttons()
        self.updateGeometry()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        for r in self._rows:
            r.left_input.setEnabled(enabled)
            r.right_input.setEnabled(enabled)
            r.remove_button.setEnabled(enabled and len(self._rows) > 1)
        self.add_button.setEnabled(enabled)
        for btn in self._alternative_buttons:
            btn.setEnabled(enabled)


class InputListWidget(QWidget):
    """A vertical list of single-value inputs with a Create New button."""

    itemsChanged = Signal()

    def __init__(self, parent=None, placeholder: str = ""):
        super().__init__(parent)
        self._rows: list[InputListRow] = []
        self._placeholder = placeholder

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        layout.addLayout(self._rows_layout)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)

        self.add_button = StyledButton("Create New")
        IconUtils.apply_icon(
            self.add_button,
            IconType.PLUS,
            BrandColors.TEXT_PRIMARY,
            size=14,
            include_disabled=True,
        )
        self.add_button.setIconSize(QSize(14, 14))
        self.add_button.clicked.connect(lambda: self.add_item())
        actions_row.addWidget(self.add_button, 0)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        self.add_item(emit_change=False)

    def add_item(self, text: str = "", emit_change: bool = True) -> None:
        row = InputListRow(text=text, placeholder=self._placeholder)
        row.input.textChanged.connect(lambda *_: self.itemsChanged.emit())
        row.remove_button.clicked.connect(lambda: self.remove_item(row))

        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._update_remove_buttons()
        self.updateGeometry()

        if emit_change:
            self.itemsChanged.emit()

    def remove_item(self, row: InputListRow) -> None:
        if len(self._rows) <= 1:
            return

        self._rows_layout.removeWidget(row)
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()

        self._update_remove_buttons()
        self.updateGeometry()
        self.itemsChanged.emit()

    def _update_remove_buttons(self) -> None:
        disable_remove = len(self._rows) <= 1
        for row in self._rows:
            row.remove_button.setEnabled(not disable_remove)

    def get_items(self) -> list[str]:
        items: list[str] = []
        for row in self._rows:
            text = str(row.get_text() or "").strip()
            if text:
                items.append(text)
        return items

    def set_items(self, items) -> None:
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []

        if items:
            for item in items:
                text = str(item or "").strip()
                self.add_item(text=text, emit_change=False)

        if not self._rows:
            self.add_item(emit_change=False)

        self._update_remove_buttons()
        self.updateGeometry()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        for row in self._rows:
            row.input.setEnabled(enabled)
            row.remove_button.setEnabled(enabled and len(self._rows) > 1)
        self.add_button.setEnabled(enabled)


class SettingRow(QWidget):
    """A stacked layout for settings with label above and full-width control below."""

    def __init__(
        self,
        label_text: str,
        control_widget: QWidget,
        tooltip: str = None,
        description: str = None,
        docs_url: str = None,
        docs_handler=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent;")

        self._docs_url = str(docs_url or "").strip()
        self._label_text = str(label_text or "")
        self._description_text = str(description or tooltip or "")
        self._is_dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(6)

        header = QWidget()
        header.setStyleSheet("background-color: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        self.label = QLabel()
        self.label.setTextFormat(Qt.RichText)
        self.label.setStyleSheet("background-color: transparent;")
        header_layout.addWidget(self.label, 0, Qt.AlignVCenter)
        header_layout.addStretch(1)
        layout.addWidget(header)

        self.desc_label = None
        if description:
            self.desc_label = QLabel(description)
            self.desc_label.setWordWrap(True)
            self.desc_label.setStyleSheet(f"""
                font-size: {BrandColors.FONT_SIZE_SMALL};
                color: {BrandColors.TEXT_SOFT};
                background-color: transparent;
                padding-bottom: 4px;
            """)
            layout.addWidget(self.desc_label)

        self.control = control_widget
        self.control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.control)
        self._tag_info_widget(self)
        self._tag_info_widget(self.label)
        self._tag_info_widget(self.control)
        self._update_label_style()

    def _tag_info_widget(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        widget.setProperty("settingInfoTitle", self._label_text)
        widget.setProperty("settingInfoBody", str(self._description_text or "").strip())
        if self._docs_url:
            widget.setProperty("docsUrl", self._docs_url)

    def _update_label_style(self, enabled: bool = True) -> None:
        label_color = BrandColors.TEXT_SECONDARY if enabled else BrandColors.TEXT_DISABLED
        dirty_html = ""
        if self._is_dirty:
            dirty_html = f" <span style='color: {BrandColors.ACCENT};'>*</span>"
        self.label.setText(
            (
                f"<span style='font-size: {BrandColors.FONT_SIZE_REGULAR}; "
                f"font-weight: 500; color: {label_color};'>"
                f"{html.escape(self._label_text)}</span>{dirty_html}"
            )
        )

    def set_dirty(self, dirty: bool) -> None:
        dirty = bool(dirty)
        if self._is_dirty == dirty:
            return
        self._is_dirty = dirty
        self._update_label_style(self.isEnabled())

    def set_help_focus_visible(self, _visible: bool) -> None:
        return

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.control.setEnabled(enabled)
        self._update_label_style(enabled)
        if self.desc_label:
            desc_color = BrandColors.TEXT_SOFT if enabled else BrandColors.TEXT_DISABLED
            self.desc_label.setStyleSheet(f"""
                font-size: {BrandColors.FONT_SIZE_SMALL};
                color: {desc_color};
                background-color: transparent;
                padding-bottom: 4px;
            """)


class ToggleRow(QWidget):
    """A compact horizontal layout for toggle settings (label left, toggle right)."""

    def __init__(
        self,
        label_text: str,
        toggle_widget: QWidget,
        tooltip: str = None,
        description: str = None,
        docs_url: str = None,
        docs_handler=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent;")

        self._docs_url = str(docs_url or "").strip()
        self._label_text = str(label_text or "")
        self._description_text = str(description or tooltip or "")
        self._is_dirty = False

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 12, 0, 12)
        main_layout.setSpacing(16)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(3)

        label_row = QWidget()
        label_row.setStyleSheet("background-color: transparent;")
        label_row_layout = QHBoxLayout(label_row)
        label_row_layout.setContentsMargins(0, 0, 0, 0)
        label_row_layout.setSpacing(0)

        self.label = QLabel()
        self.label.setTextFormat(Qt.RichText)
        self.label.setStyleSheet("background-color: transparent;")
        label_row_layout.addWidget(self.label, 0, Qt.AlignVCenter)
        label_row_layout.addStretch(1)
        left_layout.addWidget(label_row)

        if description:
            self.desc_label = QLabel(description)
            self.desc_label.setWordWrap(True)
            self.desc_label.setStyleSheet(f"""
                font-size: {BrandColors.FONT_SIZE_SMALL};
                color: {BrandColors.TEXT_SOFT};
                background-color: transparent;
            """)
            left_layout.addWidget(self.desc_label)
        else:
            self.desc_label = None

        main_layout.addLayout(left_layout, 1)

        self.control = toggle_widget
        main_layout.addWidget(self.control, 0)
        self._tag_info_widget(self)
        self._tag_info_widget(self.label)
        self._tag_info_widget(self.control)
        self._update_label_style()

    def _tag_info_widget(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        widget.setProperty("settingInfoTitle", self._label_text)
        widget.setProperty("settingInfoBody", str(self._description_text or "").strip())
        if self._docs_url:
            widget.setProperty("docsUrl", self._docs_url)

    def _update_label_style(self, enabled: bool = True) -> None:
        label_color = BrandColors.TEXT_PRIMARY if enabled else BrandColors.TEXT_DISABLED
        dirty_html = ""
        if self._is_dirty:
            dirty_html = f" <span style='color: {BrandColors.ACCENT};'>*</span>"
        self.label.setText(
            (
                f"<span style='font-size: {BrandColors.FONT_SIZE_LARGE}; "
                f"color: {label_color};'>{html.escape(self._label_text)}</span>{dirty_html}"
            )
        )

    def set_dirty(self, dirty: bool) -> None:
        dirty = bool(dirty)
        if self._is_dirty == dirty:
            return
        self._is_dirty = dirty
        self._update_label_style(self.isEnabled())

    def set_help_focus_visible(self, _visible: bool) -> None:
        return

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.control.setEnabled(enabled)
        self._update_label_style(enabled)
        if self.desc_label:
            desc_color = BrandColors.TEXT_SOFT if enabled else BrandColors.TEXT_DISABLED
            self.desc_label.setStyleSheet(f"""
                font-size: {BrandColors.FONT_SIZE_SMALL};
                color: {desc_color};
                background-color: transparent;
            """)
