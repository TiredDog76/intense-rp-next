"""
Console window for displaying application logs.
QT-based window with black background and colored text.
"""
import html
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow,
    QPlainTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QTextCharFormat, QColor, QFont

from ui.core.brand import BrandColors
from utils.logger import Logger


class ConsoleWindow(QMainWindow):
    """
    A console window that displays colored log output.
    Cannot be closed manually - only closes when settings toggle is off.
    """
    
    MAX_LINES = 500
    
    # Color Palettes
    # copypasted from original project
    PALETTES = {
        "Modern": {
            "DEBUG": "#ADB5BD",     # Gray
            "INFO": "#66D9EF",      # Cyan
            "SUCCESS": "#51CF66",   # Green
            "WARNING": "#FFD43B",   # Yellow
            "ERROR": "#FF6B6B",     # Red
        },
        "Classic": {
            "DEBUG": "#ADB5BD",     # Gray
            "INFO": "cyan",         
            "SUCCESS": "#13FF00",   # Green
            "WARNING": "yellow",
            "ERROR": "red",
        },
        "Bright": {
            "DEBUG": "#888888",     # Gray
            "INFO": "#00FFFF",      # Cyan
            "SUCCESS": "#00FF88",   # Green
            "WARNING": "#FFDD00",   # Yellow
            "ERROR": "#FF3333",     # Red
        }
    }
    
    def __init__(self, config_manager=None, parent=None):
        # Pass None as parent to make it a top-level window with its own taskbar icon
        super().__init__(None)
        self.setWindowTitle("Console")
        self.resize(700, 400)
        self.config_manager = config_manager
        self._allow_close = False
        
        # Remove close button but keep minimize and maximize
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint
        )
        
        self.current_palette = self.PALETTES["Modern"]
        self._init_ui()
        self._line_count = 0
        
        if self.config_manager:
            self.apply_settings()
    
    def _init_ui(self):
        """Initialize the UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Mini menu bar (Clear / Dump)
        menu_bar = QWidget()
        menu_bar.setStyleSheet("""
            QWidget {
                background-color: #101010;
                border-bottom: 1px solid #1a1a1a;
            }
        """)
        menu_layout = QHBoxLayout(menu_bar)
        menu_layout.setContentsMargins(8, 8, 8, 8)
        menu_layout.setSpacing(8)

        button_style = f"""
            QPushButton {{
                background-color: #1a1a1a;
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid #333333;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QPushButton:hover {{
                background-color: #222222;
                border: 1px solid {BrandColors.ACCENT};
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.ACCENT};
                border: 1px solid {BrandColors.ACCENT};
            }}
        """

        menu_layout.addStretch(1)

        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(button_style)
        clear_btn.clicked.connect(self.clear)
        menu_layout.addWidget(clear_btn)

        dump_btn = QPushButton("Dump")
        dump_btn.setCursor(Qt.PointingHandCursor)
        dump_btn.setStyleSheet(button_style)
        dump_btn.clicked.connect(self.dump)
        menu_layout.addWidget(dump_btn)

        layout.addWidget(menu_bar)
        
        # Text display area
        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setLineWrapMode(QPlainTextEdit.NoWrap)
        
        # Styling
        font = QFont("Consolas", 10)
        self.text_area.setFont(font)
        
        # Initial style, will be updated by apply_settings
        self.text_area.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0c0c0c;
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 8px;
            }}
            QScrollBar:vertical {{
                border: none;
                background: #1a1a1a;
                width: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #444444;
                min-height: 20px;
                border-radius: 6px;
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
            QScrollBar:horizontal {{
                border: none;
                background: #1a1a1a;
                height: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background: #444444;
                min-width: 20px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: #555555;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """)
        
        layout.addWidget(self.text_area)
        
        # Main window styling
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: #0c0c0c;
            }}
        """)

    def _get_dump_directory(self) -> str:
        if not self.config_manager:
            return ""

        value = self.config_manager.get_setting("console_dumping", "condump_directory")
        return str(value).strip() if value is not None else ""

    def dump(self):
        """Dump current console contents to a file."""
        text = self.text_area.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "Console Dump", "Console is empty.")
            return

        dump_dir = self._get_dump_directory()
        if not dump_dir:
            selected_dir = QFileDialog.getExistingDirectory(self, "Select Dump Directory")
            if not selected_dir:
                return
            dump_dir = selected_dir

        try:
            out_dir = Path(dump_dir).expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            out_path = out_dir / f"condump_{timestamp}.txt"
            counter = 1
            while out_path.exists():
                out_path = out_dir / f"condump_{timestamp}_{counter}.txt"
                counter += 1

            content = text if text.endswith("\n") else (text + "\n")
            out_path.write_text(content, encoding="utf-8", errors="replace")
            Logger.success(f"Console dumped to: {out_path}")
        except Exception as exc:
            Logger.error(f"Failed to dump console: {exc}")
            QMessageBox.warning(self, "Console Dump", f"Failed to dump console:\n\n{exc}")

    def _confirm_clear_enabled(self) -> bool:
        if not self.config_manager:
            return True

        value = self.config_manager.get_setting("console_dumping", "confirm_clear")
        if value is None:
            return True
        return bool(value)

    def apply_settings(self):
        """Apply settings from config manager."""
        if not self.config_manager:
            return

        # 1. Max Line Limit
        self.MAX_LINES = self.config_manager.get_setting("console_settings", "max_lines") or 500
        if self._line_count > self.MAX_LINES:
            self._trim_lines()

        # 2. Font Size
        font_size = self.config_manager.get_setting("console_settings", "font_size") or 10
        font = QFont("Consolas", int(font_size))
        self.text_area.setFont(font)

        # 3. Color Palette setup
        palette_name = self.config_manager.get_setting("console_settings", "color_palette") or "Modern"
        self.current_palette = self.PALETTES.get(palette_name, self.PALETTES["Modern"])
        
        # Update stylesheet (Opaque background, maybe later make configurable)
        self.text_area.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0c0c0c;
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 8px;
            }}
            QScrollBar:vertical {{
                border: none;
                background: #1a1a1a;
                width: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #444444;
                min-height: 20px;
                border-radius: 6px;
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
            QScrollBar:horizontal {{
                border: none;
                background: #1a1a1a;
                height: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background: #444444;
                min-width: 20px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: #555555;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """)
        
        # 4. Always On Top
        always_on_top = self.config_manager.get_setting("console_settings", "always_on_top")
        
        # Base flags
        flags = Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowMaximizeButtonHint
        
        if always_on_top:
            # If always on top, disable minimization (remove the hint) and add OnTop hint
            flags |= Qt.WindowStaysOnTopHint
            # Explicitly NOT adding Qt.WindowMinimizeButtonHint, kinda kills the purpose
        else:
            # Allow minimization if not always on top
            flags |= Qt.WindowMinimizeButtonHint
            
        # We need to preserve the window state (visible/hidden) when changing flags
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    
    def _get_color_for_level(self, level_str: str) -> str:
        """Get the hex color for a log level."""
        return self.current_palette.get(level_str, BrandColors.TEXT_PRIMARY)
    
    @Slot(str, str)
    def append_log(self, level_name: str, message: str):
        """
        Append a log message with appropriate coloring.
        
        Args:
            level_name: The log level name (DEBUG, INFO, etc.)
            message: The formatted log message
        """
        color = self._get_color_for_level(level_name)
        
        # Escape HTML entities and convert newlines for multiline support
        safe_msg = html.escape(message).replace('\n', '<br>')
        html_message = f'<span style="color: {color};">{safe_msg}</span>'
        self.text_area.appendHtml(html_message)
        
        # (multiline messages count as multiple lines)
        line_count = message.count('\n') + 1
        self._line_count += line_count
        
        # Trim old lines if exceeded max
        if self._line_count > self.MAX_LINES:
            self._trim_lines()
        
        # Auto-scroll to bottom
        scrollbar = self.text_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _trim_lines(self):
        """Remove oldest lines to stay within MAX_LINES limit."""
        cursor = self.text_area.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        
        # Calculate how many lines to remove
        lines_to_remove = self._line_count - self.MAX_LINES
        
        # just remove chunks. (iq = 30)
        # NOOOO WE NEED TO CAREFULLY REMOVE EXACTLY LINES AND BE PRECISE (iq = 80)
        # just remove chunks. (iq = 160)
        
        if lines_to_remove > 0:
            for _ in range(lines_to_remove):
                cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor)
                cursor.movePosition(cursor.MoveOperation.StartOfLine, cursor.MoveMode.KeepAnchor)
            
            # Include the newline
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            
            self._line_count = self.MAX_LINES
    
    def clear(self):
        """Clear all log content."""
        if self._confirm_clear_enabled() and self.text_area.toPlainText().strip():
            reply = QMessageBox.question(
                self,
                "Clear Console",
                "Are you sure you want to clear the console output?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self.text_area.clear()
        self._line_count = 0
    
    def closeEvent(self, event):
        """Prevent manual closing - always ignore close events."""
        if getattr(self, "_allow_close", False):
            event.accept()
            return

        event.ignore()
    
    def force_close(self):
        """Force close the window (called when settings toggle is off)."""
        # Temporarily restore close button behavior
        self._allow_close = True
        try:
            self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint)
            self.close()
        finally:
            self._allow_close = False
