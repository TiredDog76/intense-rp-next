"""
Mini-console widget for displaying grouped logs in the main window.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QStackedLayout, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QAbstractAnimation

from ui.core.animation_settings import animations_disabled
from ui.core.brand import BrandColors
from ui.core.icons import IconUtils
from utils.logger import LogLevel


class LogGroup(QWidget):
    """A collapsible group of logs of the same type."""
    
    MAX_LOGS_PER_GROUP = 50
    
    # Colors for each log type
    LEVEL_COLORS = {
        "DEBUG": {"bg": "#2a2a2a", "header": "#3d3d3d", "text": "#ADB5BD"},
        "INFO": {"bg": "#1a3a4a", "header": "#2a5a7a", "text": "#66D9EF"},
        "SUCCESS": {"bg": "#1a3a2a", "header": "#2a5a3a", "text": "#51CF66"},
        "WARNING": {"bg": "#3a3a1a", "header": "#5a5a2a", "text": "#FFD43B"},
        "ERROR": {"bg": "#3a1a1a", "header": "#5a2a2a", "text": "#FF6B6B"},
    }
    # Based on the Modern palette + some darker tweaks for better contrast

    LEVEL_ICONS = {
        "DEBUG": "bug.svg",
        "INFO": "info.svg",
        "SUCCESS": "check.svg",
        "WARNING": "alert-triangle.svg",
        "ERROR": "x.svg",
    }
    
    def __init__(self, level: str, parent=None):
        super().__init__(parent)
        self.level = level
        self.logs = []
        self.is_expanded = True
        self._loaded_level_icon = False
        self._loaded_chevron_path = None
        self._toggle_anim_group = None
        self._content_height_anim = None
        self._content_opacity_anim = None
        self._content_opacity_effect = None
        self._animating = False
        
        colors = self.LEVEL_COLORS.get(level, self.LEVEL_COLORS["INFO"])
        self.bg_color = colors["bg"]
        self.header_color = colors["header"]
        self.text_color = colors["text"]
        
        self._init_ui()
    
    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Header container widget
        self.header_widget = QWidget()
        self.header_widget.setCursor(Qt.PointingHandCursor)
        
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)

        self.level_icon = QLabel()
        self.level_icon.setStyleSheet("background-color: transparent;")
        self.level_icon.setFixedSize(18, 18)
        header_layout.addWidget(self.level_icon)
        
        # Level text + count
        self.header_text = QLabel()
        self.header_text.setStyleSheet(f"""
            color: {self.text_color};
            font-weight: bold;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            background-color: transparent;
        """)
        header_layout.addWidget(self.header_text)
        
        header_layout.addStretch()
        
        self.chevron_label = QLabel()
        self.chevron_label.setStyleSheet("background-color: transparent;")
        self.chevron_label.setFixedSize(16, 16)
        header_layout.addWidget(self.chevron_label)
        
        # Make entire header clickable
        self.header_widget.mousePressEvent = lambda e: self._toggle_expand()
        
        self.main_layout.addWidget(self.header_widget)
        
        # Content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 6, 10, 6)
        self.content_layout.setSpacing(2)
        
        self.main_layout.addWidget(self.content_widget)

        self._init_animations()
        self._apply_expanded_state(initial=True)

        # Initial update
        self._load_level_icon()
        self._update_header()
        self._update_chevron()

    def _init_animations(self) -> None:
        self._content_opacity_effect = QGraphicsOpacityEffect(self.content_widget)
        self._content_opacity_effect.setOpacity(1.0)
        self.content_widget.setGraphicsEffect(self._content_opacity_effect)

        self._content_height_anim = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self._content_height_anim.setDuration(170)
        self._content_height_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._content_opacity_anim = QPropertyAnimation(self._content_opacity_effect, b"opacity")
        self._content_opacity_anim.setDuration(170)
        self._content_opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._toggle_anim_group = QParallelAnimationGroup(self)
        self._toggle_anim_group.addAnimation(self._content_height_anim)
        self._toggle_anim_group.addAnimation(self._content_opacity_anim)
        self._toggle_anim_group.finished.connect(self._on_toggle_anim_finished)

    def _apply_expanded_state(self, initial: bool = False) -> None:
        if self.is_expanded:
            self.content_widget.setVisible(True)
            self.content_widget.setMaximumHeight(16777215)
            if self._content_opacity_effect:
                self._content_opacity_effect.setOpacity(1.0)
        else:
            self.content_widget.setMaximumHeight(0)
            self.content_widget.setVisible(False)
            if self._content_opacity_effect:
                self._content_opacity_effect.setOpacity(0.0)

        if initial or not self._animating:
            self._update_expand_styles()

    def _get_content_target_height(self) -> int:
        layout = self.content_widget.layout()
        if layout is not None and hasattr(layout, "totalSizeHint"):
            try:
                return max(0, int(layout.totalSizeHint().height()))
            except Exception:
                pass
        try:
            return max(0, int(self.content_widget.sizeHint().height()))
        except Exception:
            return 0

    def _on_toggle_anim_finished(self) -> None:
        self._animating = False
        if self.is_expanded:
            self.content_widget.setMaximumHeight(16777215)
            if self._content_opacity_effect:
                self._content_opacity_effect.setOpacity(1.0)
            self._update_expand_styles()
            return

        self.content_widget.setMaximumHeight(0)
        self.content_widget.setVisible(False)
        if self._content_opacity_effect:
            self._content_opacity_effect.setOpacity(0.0)
        self._update_expand_styles()

    def _load_level_icon(self) -> None:
        if self._loaded_level_icon:
            return

        icon_filename = self.LEVEL_ICONS.get(self.level, "info.svg")
        pixmap = IconUtils.get_pixmap(
            icon_filename,
            color=self.text_color,
            size=18,
            dpr=self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            self.level_icon.setPixmap(pixmap)
            self._loaded_level_icon = True

    def _update_expand_styles(self):
        """Update corner rounding based on expanded/collapsed state.
        
        Am I a perfectionist? Yes. Do I obsess over tiny UI details? Also yes. 
        But have I lost touch with reality?
        One could argue that as well.
        """
        if self.is_expanded:
            header_bottom_left = "0px"
            header_bottom_right = "0px"
        else:
            header_bottom_left = "4px"
            header_bottom_right = "4px"

        self.header_widget.setStyleSheet(f"""
            background-color: {self.header_color};
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            border-bottom-left-radius: {header_bottom_left};
            border-bottom-right-radius: {header_bottom_right};
        """)

        self.content_widget.setStyleSheet(f"""
            background-color: {self.bg_color};
            border-top-left-radius: 0px;
            border-top-right-radius: 0px;
            border-bottom-left-radius: 4px;
            border-bottom-right-radius: 4px;
        """)
    
    def _lighten_color(self, hex_color: str, amount: int) -> str:
        """Lighten a hex color by an amount."""
        hex_color = hex_color.lstrip('#')
        r = min(255, int(hex_color[0:2], 16) + amount)
        g = min(255, int(hex_color[2:4], 16) + amount)
        b = min(255, int(hex_color[4:6], 16) + amount)
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _update_header(self):
        """Update header text with log count."""
        count = len(self.logs)
        self.header_text.setText(f"{self.level} ({count})")
    
    def _update_chevron(self):
        """Update the chevron icon based on expanded state."""
        if self.is_expanded:
            chevron_file = "chevron-down.svg"
        else:
            chevron_file = "chevron-right.svg"

        if chevron_file == self._loaded_chevron_path:
            return

        pixmap = IconUtils.get_pixmap(
            chevron_file,
            color=BrandColors.TEXT_SECONDARY,
            size=16,
            dpr=self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            self.chevron_label.setPixmap(pixmap)
            self._loaded_chevron_path = chevron_file
    
    def _toggle_expand(self):
        """Toggle the expanded/collapsed state."""
        self.is_expanded = not self.is_expanded

        if self._toggle_anim_group and self._toggle_anim_group.state() == QAbstractAnimation.Running:
            self._toggle_anim_group.stop()

        if animations_disabled():
            self._animating = False
            self._apply_expanded_state()
            self._update_chevron()
            return

        self._animating = True
        self.content_widget.setVisible(True)

        if self.is_expanded:
            self._update_expand_styles()
            start_h = int(self.content_widget.maximumHeight())
            end_h = int(self._get_content_target_height())

            self._content_height_anim.setStartValue(start_h)
            self._content_height_anim.setEndValue(end_h)
            self._content_opacity_anim.setStartValue(float(self._content_opacity_effect.opacity()))
            self._content_opacity_anim.setEndValue(1.0)
        else:
            start_h = int(self.content_widget.height())
            self._content_height_anim.setStartValue(start_h)
            self._content_height_anim.setEndValue(0)
            self._content_opacity_anim.setStartValue(float(self._content_opacity_effect.opacity()))
            self._content_opacity_anim.setEndValue(0.0)

        self._toggle_anim_group.start()
        self._update_chevron()
    
    @staticmethod
    def _break_long_words(text: str, max_word_len: int = 40) -> str:
        """Insert zero-width spaces into long unbroken sequences so Qt can wrap them."""
        parts = []
        for word in text.split(' '):
            if len(word) > max_word_len:
                chunks = [word[i:i + max_word_len] for i in range(0, len(word), max_word_len)]
                word = '\u200b'.join(chunks)
            parts.append(word)
        return ' '.join(parts)

    def add_log(self, message: str) -> bool:
        """
        Add a log message to this group.
        Returns False if the group is full.
        """
        if len(self.logs) >= self.MAX_LOGS_PER_GROUP:
            return False

        if len(message) > 256:
            message = message[:253] + "..."

        self.logs.append(message)

        # Create label for the log
        log_label = QLabel(self._break_long_words(message))
        log_label.setWordWrap(True)
        log_label.setStyleSheet(f"""
            color: {self.text_color};
            font-size: {BrandColors.FONT_SIZE_SMALL};
            background-color: transparent;
            padding: 2px 0;
        """)
        log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.content_layout.addWidget(log_label)
        
        self._update_header()
        return True
    
    def is_full(self) -> bool:
        """Check if this group has reached its log limit."""
        return len(self.logs) >= self.MAX_LOGS_PER_GROUP


class MiniConsole(QWidget):
    """A mini-console widget that displays grouped logs."""
    
    MAX_GROUPS = 35
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.groups = []  # List of LogGroup widgets
        self.last_level = None
        self._main_logging_enabled = True
        
        self._init_ui()
    
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Container widget for rounded corners
        container = QFrame()
        container.setObjectName("miniConsoleContainer")
        container.setStyleSheet(f"""
            QFrame#miniConsoleContainer {{
                background-color: #1a1a1a;
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
            }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Integrated header label
        header_label = QLabel("Activity Log")
        header_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-weight: bold;
            color: {BrandColors.TEXT_SECONDARY};
            padding: 10px 12px 8px 12px;
            background-color: #222222;
            border-bottom: 1px solid {BrandColors.INPUT_BORDER};
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
        """)
        container_layout.addWidget(header_label)
        
        # Scroll area for log groups
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: #1a1a1a;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: #444444;
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #555555;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        # Stacked content: logs vs "disabled" message
        self.stacked_widget = QWidget()
        self.stacked_widget.setStyleSheet("background-color: transparent;")
        self.stacked_layout = QStackedLayout(self.stacked_widget)

        # Logs page (inside scroll area)
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(6)
        self.content_layout.setAlignment(Qt.AlignTop)

        # Disabled page (inside scroll area)
        disabled_widget = QWidget()
        disabled_widget.setStyleSheet("background-color: transparent;")
        disabled_layout = QVBoxLayout(disabled_widget)
        disabled_layout.setContentsMargins(12, 18, 12, 18)
        disabled_layout.addStretch(1)

        self.disabled_label = QLabel("Main Logging Disabled")
        self.disabled_label.setAlignment(Qt.AlignCenter)
        self.disabled_label.setStyleSheet(f"""
            color: {BrandColors.TEXT_SECONDARY};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            background-color: transparent;
        """)
        disabled_layout.addWidget(self.disabled_label)
        disabled_layout.addStretch(1)

        self.stacked_layout.addWidget(self.content_widget)
        self.stacked_layout.addWidget(disabled_widget)
        self.stacked_layout.setCurrentWidget(self.content_widget)

        self.scroll_area.setWidget(self.stacked_widget)
        container_layout.addWidget(self.scroll_area)
        main_layout.addWidget(container)
    
    def add_log(self, level: LogLevel, message: str):
        """Add a log message to the mini-console."""
        if not self._main_logging_enabled:
            return

        level_name = level.value
        
        # Determine if we need a new group
        need_new_group = (
            not self.groups or  # No groups yet
            self.last_level != level_name or  # Different level
            self.groups[-1].is_full()  # Current group is full
        )
        
        if need_new_group:
            # Check if we need to remove old groups
            while len(self.groups) >= self.MAX_GROUPS:
                old_group = self.groups.pop(0)
                self.content_layout.removeWidget(old_group)
                old_group.deleteLater()
            
            # Create new group
            new_group = LogGroup(level_name)
            self.groups.append(new_group)
            self.content_layout.addWidget(new_group)
            self.last_level = level_name
        
        # Add log to current group
        self.groups[-1].add_log(message)
        
        # Auto-scroll to bottom using QTimer to avoid async conflicts
        QTimer.singleShot(0, self._scroll_to_bottom)
    
    def _scroll_to_bottom(self):
        """Scroll the mini-console to the bottom."""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear(self):
        """Clear all log groups."""
        for group in self.groups:
            self.content_layout.removeWidget(group)
            group.deleteLater()
        self.groups.clear()
        self.last_level = None

    def set_main_logging_enabled(self, enabled: bool):
        """Enable/disable Activity Log updates and show a placeholder when disabled."""
        enabled = bool(enabled)
        if enabled == self._main_logging_enabled:
            return

        self._main_logging_enabled = enabled
        if enabled:
            self.stacked_layout.setCurrentWidget(self.content_widget)
        else:
            self.clear()
            self.stacked_layout.setCurrentIndex(1)
