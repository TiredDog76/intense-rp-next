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
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QLabel,
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QTextOption, QTextCursor, QTextFormat, QKeySequence, QShortcut

from ui.core.brand import BrandColors
from ui.core.icons import IconUtils, IconType
from utils.logger import Logger


class ConsoleWindow(QMainWindow):
    """
    A console window that displays colored log output.
    Cannot be closed manually - only closes when settings toggle is off.
    """
    
    MAX_LINES = 500
    AUTO_SCROLL_MODES = {"Always", "Bottom only", "Never"}
    SEARCH_DEBOUNCE_MS = 300
    SEARCH_FLASH_INTERVAL_MS = 400
    SEARCH_FLASH_STEPS = 6
    
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
        self._auto_scroll_mode = "Always"
        self._line_count = 0
        self._search_matches = []
        self._search_current_index = -1
        self._search_flash_visible = False
        self._search_flash_steps_remaining = 0
        self._search_refresh_origin = None
        self._last_search_query = ""
        self._initial_focus_pending = True
        
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
        
        if self.config_manager:
            self.apply_settings()
    
    def _init_ui(self):
        """Initialize the UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Mini menu bar (Search / Clear / Dump)
        menu_bar = QWidget()
        menu_bar.setObjectName("consoleMenuBar")
        menu_bar.setStyleSheet("""
            QWidget#consoleMenuBar {
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

        compact_button_style = f"""
            QPushButton {{
                background-color: #1a1a1a;
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid #333333;
                padding: 6px;
                min-width: 30px;
                max-width: 30px;
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
            QPushButton:disabled {{
                color: {BrandColors.TEXT_DISABLED};
                border: 1px solid #2a2a2a;
                background-color: #151515;
            }}
        """

        search_input_style = f"""
            QLineEdit {{
                background-color: #1a1a1a;
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid #333333;
                padding: 6px 32px 6px 28px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QLineEdit:hover {{
                background-color: #222222;
                border: 1px solid #444444;
            }}
            QLineEdit:focus {{
                background-color: #222222;
                border: 1px solid {BrandColors.ACCENT};
            }}
        """

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search console...")
        self.search_input.setFixedWidth(240)
        self.search_input.setStyleSheet(search_input_style)
        search_icon = IconUtils.get_icon(
            IconType.SEARCH,
            color=BrandColors.TEXT_SECONDARY,
            size=16,
            widget=self.search_input,
        )
        self.search_input.addAction(search_icon, QLineEdit.LeadingPosition)
        clear_icon = IconUtils.get_icon(
            "x.svg",
            color=BrandColors.TEXT_SECONDARY,
            size=16,
            widget=self.search_input,
        )
        self.search_clear_action = self.search_input.addAction(clear_icon, QLineEdit.TrailingPosition)
        self.search_clear_action.setVisible(False)
        self.search_clear_action.triggered.connect(self._clear_search)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        menu_layout.addWidget(self.search_input, 0)

        menu_layout.addStretch(1)

        self.search_nav = QWidget()
        self.search_nav.setStyleSheet("background-color: transparent; border: none;")
        search_nav_layout = QHBoxLayout(self.search_nav)
        search_nav_layout.setContentsMargins(0, 0, 0, 0)
        search_nav_layout.setSpacing(6)

        self.search_prev_btn = QPushButton()
        self.search_prev_btn.setCursor(Qt.PointingHandCursor)
        self.search_prev_btn.setToolTip("Previous match")
        self.search_prev_btn.setFixedSize(30, 30)
        self.search_prev_btn.setStyleSheet(compact_button_style)
        self.search_prev_btn.setIcon(
            IconUtils.get_icon(
                "chevron-left.svg",
                color=BrandColors.TEXT_PRIMARY,
                size=16,
                widget=self.search_prev_btn,
            )
        )
        self.search_prev_btn.clicked.connect(self._goto_previous_search_match)
        search_nav_layout.addWidget(self.search_prev_btn)

        self.search_status_label = QLabel("0 / 0")
        self.search_status_label.setAlignment(Qt.AlignCenter)
        self.search_status_label.setStyleSheet(f"""
            color: {BrandColors.TEXT_SECONDARY};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-family: {BrandColors.FONT_FAMILY};
            padding: 0 2px;
            min-width: 48px;
        """)
        search_nav_layout.addWidget(self.search_status_label)

        self.search_next_btn = QPushButton()
        self.search_next_btn.setCursor(Qt.PointingHandCursor)
        self.search_next_btn.setToolTip("Next match")
        self.search_next_btn.setFixedSize(30, 30)
        self.search_next_btn.setStyleSheet(compact_button_style)
        self.search_next_btn.setIcon(
            IconUtils.get_icon(
                "chevron-right.svg",
                color=BrandColors.TEXT_PRIMARY,
                size=16,
                widget=self.search_next_btn,
            )
        )
        self.search_next_btn.clicked.connect(self._goto_next_search_match)
        search_nav_layout.addWidget(self.search_next_btn)

        self.search_nav.hide()
        menu_layout.addWidget(self.search_nav, 0)

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
        self.text_area.textChanged.connect(self._on_console_text_changed)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(self.SEARCH_DEBOUNCE_MS)
        self.search_timer.timeout.connect(self._perform_search)

        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self._focus_search_input)

        self.search_flash_timer = QTimer(self)
        self.search_flash_timer.setInterval(self.SEARCH_FLASH_INTERVAL_MS)
        self.search_flash_timer.timeout.connect(self._advance_search_flash)

        self._update_search_nav(search_active=False)
        
        # Main window styling
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: #0c0c0c;
            }}
        """)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_focus_pending:
            return

        self._initial_focus_pending = False
        QTimer.singleShot(0, self._focus_console_output)

    def _schedule_search(self, origin: str) -> None:
        if not self.search_input.text().strip():
            self.search_timer.stop()
            return

        if self._search_refresh_origin != "input" or origin == "input":
            self._search_refresh_origin = origin
        self.search_timer.start()

    def _focus_search_input(self) -> None:
        self.search_input.setFocus(Qt.ShortcutFocusReason)
        self.search_input.selectAll()

    def _focus_console_output(self) -> None:
        self.text_area.setFocus(Qt.OtherFocusReason)

    def _on_search_text_changed(self, text: str) -> None:
        has_query = bool(text.strip())
        self.search_clear_action.setVisible(has_query)
        if has_query:
            self._schedule_search("input")
            return

        self.search_timer.stop()
        self._clear_search_results()

    def _on_console_text_changed(self) -> None:
        if self.search_input.text().strip():
            self._schedule_search("document")

    def _clear_search(self) -> None:
        if self.search_input.text():
            self.search_input.clear()
            return

        self._clear_search_results()

    def _clear_search_results(self) -> None:
        self._search_matches = []
        self._search_current_index = -1
        self._search_refresh_origin = None
        self._last_search_query = ""
        self._stop_search_flash()
        self._update_search_nav(search_active=False)
        self._refresh_search_highlights()

    def _find_search_matches(self, query: str) -> list[int]:
        query_key = query.casefold()
        matches = []
        block = self.text_area.document().firstBlock()
        line_number = 0

        while block.isValid():
            if query_key in block.text().casefold():
                matches.append(line_number)
            block = block.next()
            line_number += 1

        return matches

    def _perform_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self._clear_search_results()
            return

        query_key = query.casefold()
        origin = self._search_refresh_origin or "input"
        previous_line = self._current_search_line()
        matches = self._find_search_matches(query)

        self._search_refresh_origin = None
        self._search_matches = matches

        if not matches:
            self._search_current_index = -1
            self._last_search_query = query_key
            self._stop_search_flash()
            self._update_search_nav(search_active=True)
            self._refresh_search_highlights()
            return

        query_changed = query_key != self._last_search_query
        self._last_search_query = query_key

        if origin == "input":
            if query_changed or self._search_current_index == -1:
                next_index = 0
            else:
                next_index = min(self._search_current_index, len(matches) - 1)
            should_jump = True
        elif previous_line in matches:
            next_index = matches.index(previous_line)
            should_jump = False
        else:
            next_index = min(max(self._search_current_index, 0), len(matches) - 1)
            should_jump = True

        self._search_current_index = next_index
        self._update_search_nav(search_active=True)

        if should_jump:
            self._jump_to_search_match(self._search_current_index, flash=True)
        else:
            self._refresh_search_highlights()

    def _update_search_nav(self, *, search_active: bool) -> None:
        self.search_nav.setVisible(search_active)
        if not search_active:
            self.search_status_label.setText("0 / 0")
            self.search_prev_btn.setEnabled(False)
            self.search_next_btn.setEnabled(False)
            return

        total = len(self._search_matches)
        current = self._search_current_index + 1 if self._search_current_index >= 0 else 0
        self.search_status_label.setText(f"{current} / {total}")
        can_navigate = total > 1
        self.search_prev_btn.setEnabled(can_navigate)
        self.search_next_btn.setEnabled(can_navigate)

    def _current_search_line(self) -> int | None:
        if 0 <= self._search_current_index < len(self._search_matches):
            return self._search_matches[self._search_current_index]
        return None

    def _goto_previous_search_match(self) -> None:
        if not self._search_matches:
            return
        self._jump_to_search_match(self._search_current_index - 1, flash=True)

    def _goto_next_search_match(self) -> None:
        if not self._search_matches:
            return
        self._jump_to_search_match(self._search_current_index + 1, flash=True)

    def _jump_to_search_match(self, index: int, *, flash: bool) -> None:
        if not self._search_matches:
            return

        total = len(self._search_matches)
        self._search_current_index = index % total
        line_number = self._search_matches[self._search_current_index]
        block = self.text_area.document().findBlockByNumber(line_number)
        if not block.isValid():
            self._refresh_search_highlights()
            self._update_search_nav(search_active=True)
            return

        cursor = self.text_area.textCursor()
        cursor.setPosition(block.position())
        self.text_area.setTextCursor(cursor)
        self.text_area.centerCursor()
        self._update_search_nav(search_active=True)

        if flash:
            self._start_search_flash()
        else:
            self._refresh_search_highlights()

    def _start_search_flash(self) -> None:
        self.search_flash_timer.stop()
        self._search_flash_visible = True
        self._search_flash_steps_remaining = self.SEARCH_FLASH_STEPS
        self._refresh_search_highlights()
        self.search_flash_timer.start()

    def _stop_search_flash(self) -> None:
        self.search_flash_timer.stop()
        self._search_flash_visible = False
        self._search_flash_steps_remaining = 0

    def _advance_search_flash(self) -> None:
        if self._search_current_index < 0:
            self._stop_search_flash()
            self._refresh_search_highlights()
            return

        if self._search_flash_steps_remaining <= 1:
            self._stop_search_flash()
        else:
            self._search_flash_steps_remaining -= 1
            self._search_flash_visible = not self._search_flash_visible

        self._refresh_search_highlights()

    def _make_line_selection(self, line_number: int, background: QColor) -> QTextEdit.ExtraSelection | None:
        block = self.text_area.document().findBlockByNumber(line_number)
        if not block.isValid():
            return None

        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(block)
        selection.cursor.clearSelection()
        line_format = QTextCharFormat()
        line_format.setBackground(background)
        line_format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.format = line_format
        return selection

    def _refresh_search_highlights(self) -> None:
        if not self._search_matches:
            self.text_area.setExtraSelections([])
            return

        base_color = QColor(BrandColors.ACCENT)
        base_color.setAlpha(55)
        active_color = QColor(BrandColors.ACCENT)
        active_color.setAlpha(95)
        flash_color = QColor(BrandColors.ACCENT)
        flash_color.setAlpha(150)

        current_line = self._current_search_line()
        selections = []

        for line_number in self._search_matches:
            if line_number == current_line:
                continue
            selection = self._make_line_selection(line_number, base_color)
            if selection is not None:
                selections.append(selection)

        if current_line is not None:
            active_background = flash_color if self._search_flash_visible else active_color
            active_selection = self._make_line_selection(current_line, active_background)
            if active_selection is not None:
                selections.append(active_selection)

        self.text_area.setExtraSelections(selections)

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

        # 3. Wrapping
        wrap_lines = bool(self.config_manager.get_setting("console_settings", "wrap_lines"))
        if wrap_lines:
            self.text_area.setLineWrapMode(QPlainTextEdit.WidgetWidth)
            self.text_area.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        else:
            self.text_area.setLineWrapMode(QPlainTextEdit.NoWrap)
        
        # 4. Auto-scroll mode
        auto_scroll_mode = self.config_manager.get_setting("console_settings", "auto_scroll_mode") or "Always"
        auto_scroll_mode = str(auto_scroll_mode).strip()
        self._auto_scroll_mode = auto_scroll_mode if auto_scroll_mode in self.AUTO_SCROLL_MODES else "Always"

        # 5. Color Palette setup
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
        
        # 6. Always On Top
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
        scrollbar = self.text_area.verticalScrollBar()
        old_scroll_value = scrollbar.value()
        was_at_bottom = old_scroll_value >= (scrollbar.maximum() - 2)

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

        mode = getattr(self, "_auto_scroll_mode", "Always")
        if mode == "Always":
            scrollbar.setValue(scrollbar.maximum())
        elif mode == "Bottom only":
            if was_at_bottom:
                scrollbar.setValue(scrollbar.maximum())
            else:
                scrollbar.setValue(old_scroll_value)
        elif mode == "Never":
            scrollbar.setValue(old_scroll_value)
    
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
