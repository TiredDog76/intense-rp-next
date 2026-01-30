from PySide6.QtWidgets import QCheckBox, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QFrame, QPushButton, QSizePolicy, QFileDialog, QStyle, QStyleOptionComboBox
from PySide6.QtCore import Property, QSize, Qt, QRect, Signal, QEvent
import os
from pathlib import Path
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QIcon
from ui.core.brand import BrandColors
from ui.core.icons import IconUtils, IconType

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
        self.editor = QTextEdit()
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
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            
            line2 = QFrame()
            line2.setFrameShape(QFrame.HLine)
            line2.setFrameShadow(QFrame.Sunken)
            line2.setFixedHeight(1)
            line2.setStyleSheet(f"background-color: {BrandColors.INPUT_BORDER}; border: none;")
            layout.addWidget(line2)

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
        """)


class Tumbler(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._handle_position = 0.0
        
        # Define dimensions
        self._width = 40
        self._height = 20
        self._handle_radius = 8
        self._margin = 2
        
        # We don't do animation yet, just instant toggle

        self.setStyleSheet(self._get_stylesheet())

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
        elif self.isChecked():
            bg_color = QColor(BrandColors.ACCENT)
        else:
            bg_color = QColor(BrandColors.TUMBLER_BG)
            
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_rect, self._height / 2, self._height / 2)
        
        # Draw handle
        handle_color = QColor(BrandColors.TUMBLER_HANDLE)
        painter.setBrush(QBrush(handle_color))
        
        if self.isChecked():
            handle_x = self._width - self._handle_radius * 2 - self._margin
        else:
            handle_x = self._margin
            
        handle_y = self._margin
        handle_d = self._handle_radius * 2
        
        painter.drawEllipse(handle_x, handle_y, handle_d, handle_d)
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


class InputPairsWidget(QWidget):
    """A vertical list of InputPairRow items with an Add Pair button."""

    pairsChanged = Signal()

    def __init__(self, parent=None, left_placeholder: str = "Name", right_placeholder: str = "Key"):
        super().__init__(parent)
        self._rows: list[InputPairRow] = []
        self._left_placeholder = left_placeholder
        self._right_placeholder = right_placeholder

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        layout.addLayout(self._rows_layout)

        self.add_button = StyledButton("Add Pair")
        IconUtils.apply_icon(self.add_button, IconType.PLUS, BrandColors.TEXT_PRIMARY, size=14)
        self.add_button.setIconSize(QSize(14, 14))
        # clicked(bool) passes a checked arg; ignore it.
        self.add_button.clicked.connect(lambda: self.add_pair())
        layout.addWidget(self.add_button, 0, Qt.AlignLeft)

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


class SettingRow(QWidget):
    """A stacked layout for settings with label above and full-width control below."""
    
    def __init__(self, label_text: str, control_widget: QWidget, tooltip: str = None, description: str = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(6)
        
        # Label
        self.label = QLabel(label_text)
        self.label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR}; 
            color: {BrandColors.TEXT_SECONDARY}; 
            background-color: transparent;
            font-weight: 500;
        """)
        if tooltip:
            self.label.setToolTip(tooltip)
        layout.addWidget(self.label)
        
        # Optional description
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(f"""
                font-size: {BrandColors.FONT_SIZE_SMALL}; 
                color: {BrandColors.TEXT_DISABLED}; 
                background-color: transparent;
                padding-bottom: 4px;
            """)
            layout.addWidget(desc_label)
        
        # Control widget - full width
        self.control = control_widget
        if tooltip:
            self.control.setToolTip(tooltip)
        
        # Make control expand to full width
        self.control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.control)
        
    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.control.setEnabled(enabled)
        # Dim the label when disabled
        label_color = BrandColors.TEXT_SECONDARY if enabled else BrandColors.TEXT_DISABLED
        self.label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR}; 
            color: {label_color}; 
            background-color: transparent;
            font-weight: 500;
        """)


class ToggleRow(QWidget):
    """A compact horizontal layout for toggle settings (label left, toggle right)."""
    
    def __init__(self, label_text: str, toggle_widget: QWidget, tooltip: str = None, description: str = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: transparent;")
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 12, 0, 12)
        main_layout.setSpacing(16)
        
        # Left side: Label and optional description
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(3)
        
        # Label
        self.label = QLabel(label_text)
        self.label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_LARGE}; 
            color: {BrandColors.TEXT_PRIMARY}; 
            background-color: transparent;
        """)
        if tooltip:
            self.label.setToolTip(tooltip)
        left_layout.addWidget(self.label)
        
        # Optional description (shown below label)
        if description:
            self.desc_label = QLabel(description)
            self.desc_label.setWordWrap(True)
            self.desc_label.setStyleSheet(f"""
                font-size: {BrandColors.FONT_SIZE_SMALL}; 
                color: {BrandColors.TEXT_DISABLED}; 
                background-color: transparent;
            """)
            left_layout.addWidget(self.desc_label)
        else:
            self.desc_label = None
        
        # Left side takes available space (stretch=1), toggle takes minimum (stretch=0)
        main_layout.addLayout(left_layout, 1)
        
        # Right side: Toggle (stays on right edge)
        self.control = toggle_widget
        if tooltip:
            self.control.setToolTip(tooltip)
        main_layout.addWidget(self.control, 0)
        
    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.control.setEnabled(enabled)
        # Dim the label when disabled
        label_color = BrandColors.TEXT_PRIMARY if enabled else BrandColors.TEXT_DISABLED
        self.label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_LARGE}; 
            color: {label_color}; 
            background-color: transparent;
        """)
        if self.desc_label:
            desc_color = BrandColors.TEXT_DISABLED if enabled else BrandColors.TEXT_DISABLED
            self.desc_label.setStyleSheet(f"""
                font-size: {BrandColors.FONT_SIZE_SMALL}; 
                color: {desc_color}; 
                background-color: transparent;
            """)
