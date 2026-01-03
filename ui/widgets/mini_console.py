"""
Mini-console widget for displaying grouped logs in the main window.
"""
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QStackedLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtSvgWidgets import QSvgWidget

from ui.core.brand import BrandColors
from utils.logger import LogLevel


class LogGroup(QWidget):
    """A collapsible group of logs of the same type."""
    
    MAX_LOGS_PER_GROUP = 50
    
    # Colors for each log type
    LEVEL_COLORS = {
        "INFO": {"bg": "#1a3a4a", "header": "#2a5a7a", "text": "#66D9EF"},
        "SUCCESS": {"bg": "#1a3a2a", "header": "#2a5a3a", "text": "#51CF66"},
        "WARNING": {"bg": "#3a3a1a", "header": "#5a5a2a", "text": "#FFD43B"},
        "ERROR": {"bg": "#3a1a1a", "header": "#5a2a2a", "text": "#FF6B6B"},
    }
    # Based on the Modern palette + some darker tweaks for better contrast
    
    LEVEL_ICONS = {
        "INFO": "info-cyan.svg",
        "SUCCESS": "check-green.svg",
        "WARNING": "alert-triangle-yellow.svg",
        "ERROR": "x-red.svg",
    }
    
    def __init__(self, level: str, parent=None):
        super().__init__(parent)
        self.level = level
        self.logs = []
        self.is_expanded = True
        
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
        self.header_widget.setStyleSheet(f"""
            background-color: {self.header_color};
            border-radius: 4px 4px 0 0;
        """)
        self.header_widget.setCursor(Qt.PointingHandCursor)
        
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)

        # Level icon (using QSvgWidget for HiDPI rendering)
        self.level_icon = QSvgWidget()
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
        
        # Chevron icon (using QSvgWidget for HiDPI rendering)
        self.chevron_label = QSvgWidget()
        self.chevron_label.setFixedSize(16, 16)
        header_layout.addWidget(self.chevron_label)
        
        # Make entire header clickable
        self.header_widget.mousePressEvent = lambda e: self._toggle_expand()
        
        self.main_layout.addWidget(self.header_widget)
        
        # Content area
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(f"""
            background-color: {self.bg_color};
            border-radius: 0 0 4px 4px;
        """)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 6, 10, 6)
        self.content_layout.setSpacing(2)
        
        self.main_layout.addWidget(self.content_widget)
        
        # Initial update
        self._update_header()
        self._update_chevron()
    
    def _lighten_color(self, hex_color: str, amount: int) -> str:
        """Lighten a hex color by an amount."""
        hex_color = hex_color.lstrip('#')
        r = min(255, int(hex_color[0:2], 16) + amount)
        g = min(255, int(hex_color[2:4], 16) + amount)
        b = min(255, int(hex_color[4:6], 16) + amount)
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _update_header(self):
        """Update header text with log count."""
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "assets", "icons", self.LEVEL_ICONS.get(self.level, "info-cyan.svg")))
        count = len(self.logs)
        self.header_text.setText(f"{self.level} ({count})")
        
        # Set level icon using QSvgWidget for crisp HiDPI rendering
        if os.path.exists(icon_path):
            self.level_icon.load(icon_path)
    
    def _update_chevron(self):
        """Update the chevron icon based on expanded state."""
        if self.is_expanded:
            chevron_file = "chevron-down.svg"
        else:
            chevron_file = "chevron-right.svg"
        
        chevron_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "assets", "icons", chevron_file))
        if os.path.exists(chevron_path):
            self.chevron_label.load(chevron_path)
    
    def _toggle_expand(self):
        """Toggle the expanded/collapsed state."""
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)
        self._update_chevron()
    
    def add_log(self, message: str) -> bool:
        """
        Add a log message to this group.
        Returns False if the group is full.
        """
        if len(self.logs) >= self.MAX_LOGS_PER_GROUP:
            return False
        
        self.logs.append(message)
        
        # Create label for the log
        log_label = QLabel(message)
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

        # Skip DEBUG logs
        if level == LogLevel.DEBUG:
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
