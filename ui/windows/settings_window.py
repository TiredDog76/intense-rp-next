from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
    QScrollArea, QLabel, QPushButton, QFrame, QMessageBox, QDialog, QListWidgetItem,
    QLineEdit, QTextEdit, QComboBox, QGraphicsColorizeEffect
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QColor, QIcon
from difflib import SequenceMatcher
import threading
import os
import shutil
from pathlib import Path
from config.manager import ConfigManager
from config.location import infer_preset_from_config_dir, migrate_config_dir, resolve_config_dir, write_pointer_file
from config.schema import SCHEMA, SettingType
from drivers.providers import DriverProvider
from ui.core.brand import BrandColors
from ui.widgets.components import Tumbler, StyledLineEdit, StyledTextEdit, StyledComboBox, Divider, Description, StyledButton, MultiColumnRow, SettingRow, ToggleRow, InputPairsWidget, DirectoryEntry
from ui.widgets.redirect_card import RedirectCard
from ui.widgets.smooth_scroll_area import SmoothScrollArea
from ui.ece.credential_manager_dialog import CredentialManagerDialog
from ui.core.icons import IconUtils, IconType
from ui.niche.update_available_dialog import UpdateAvailableDialog, UpdateAvailableInfo
from utils.logger import Logger
from utils.api_key_generator import generate_api_key
from utils.update_checker import check_for_updates, read_local_version

class SettingsWindow(QMainWindow):
    settings_saved = Signal(set)
    restart_requested = Signal()
    update_check_finished = Signal(object, str)

    SIDEBAR_ICON_MAP = {
        "providers_credentials": "key.svg",
        "formatting": "type.svg",
        "deepseek_behavior": "providers/deepseek.svg",
        "glm_behavior": "providers/zai.svg",
        "moonshot_behavior": "providers/moonshot.svg",
        "logfiles": "file.svg",
        "application_settings": "settings.svg",
        "system_settings": "monitor.svg",
        "console_settings": "terminal.svg",
        "console_dumping": "download.svg",
        "network_settings": "share-2.svg",
        "experimental": "flask-conical.svg",
    }

    BEHAVIOR_CATEGORY_BY_PROVIDER = {
        DriverProvider.DEEPSEEK: "deepseek_behavior",
        DriverProvider.GLM_CHAT: "glm_behavior",
        DriverProvider.MOONSHOT: "moonshot_behavior",
    }

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Settings")
        self.resize(900, 700)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG}; color: {BrandColors.TEXT_PRIMARY};")
        
        self.unsaved_changes = False
        self.field_widgets = {} # Map "category.key" -> widget
        self.setting_rows = {} # Map "category.key" -> SettingRow (for dependency toggling)
        self.category_widgets_by_key = {}  # Map category key -> card widget
        self.category_items_by_key = {}  # Map category key -> QListWidgetItem
        self._persistent_profile_entries = {}
        self._paged_settings_view_enabled = None

        self._init_ui()
        self._load_values()
        self.update_check_finished.connect(self._handle_update_check_result)
        self._update_check_in_progress = False
        self._sync_application_settings_info()

    def _get_sidebar_icon(self, icon_file: str, color: str, size: int = 18) -> QIcon:
        use_sidebar_subdir = ("/" not in icon_file) and ("\\" not in icon_file)
        return IconUtils.get_icon(
            icon_file,
            color=color,
            size=size,
            widget=self,
            subdir="sidebar" if use_sidebar_subdir else None,
        )

    def _create_card_header(self, category_key: str, title: str) -> QWidget:
        header = QWidget()
        header.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        icon_file = self.SIDEBAR_ICON_MAP.get(category_key)
        if icon_file:
            icon_size = 20
            icon_label = QLabel()
            icon_label.setStyleSheet("background-color: transparent;")
            icon_label.setFixedSize(icon_size, icon_size)
            icon = self._get_sidebar_icon(icon_file, BrandColors.TEXT_PRIMARY, size=icon_size)
            icon_label.setPixmap(icon.pixmap(icon_size, icon_size))
            layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_TITLE};
            font-weight: 700;
            letter-spacing: 0.5px;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
        """)
        layout.addWidget(title_label, 1, Qt.AlignVCenter)

        return header

    def _has_immediate_subdivider(self, fields) -> bool:
        """
        Returns True when the first meaningful field in a category is a subsection divider.
        In that case, rendering a header underline tends to look like a duplicated divider.
        """
        for field in fields or []:
            if field.type == SettingType.DESCRIPTION:
                continue
            return field.type == SettingType.DIVIDER
        return False

    def _apply_category_item_icon(self, item: QListWidgetItem, active: bool):
        if not item:
            return

        icon_file = item.data(Qt.UserRole + 1)
        if not icon_file:
            return

        color = BrandColors.TEXT_PRIMARY if active else BrandColors.TEXT_SECONDARY
        item.setIcon(self._get_sidebar_icon(icon_file, color))

    def _on_category_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        self._apply_category_item_icon(previous, active=False)
        self._apply_category_item_icon(current, active=True)
        self._sync_paged_settings_view(scroll_to_top=self._should_use_paged_settings_view())

    def _create_field_widget(self, field, category_key):
        widget = None
        if field.type == SettingType.BOOLEAN:
            widget = Tumbler()
            widget.stateChanged.connect(self._on_setting_changed)
            if category_key == "application_settings" and field.key == "show_only_active_provider_behavior":
                widget.stateChanged.connect(self._sync_behavior_category_visibility)
            if category_key == "application_settings" and field.key == "paged_settings_view":
                widget.stateChanged.connect(self._sync_paged_settings_view)
        elif field.type == SettingType.DIRECTORY:
            dialog_title = f"Select {field.label}" if field.label else "Select Directory"
            widget = DirectoryEntry(dialog_title=dialog_title)
            if field.key == "config_storage_custom_path":
                widget.setPlaceholderText("Custom config directory...")
            elif field.key == "condump_directory":
                widget.setPlaceholderText("Ask (leave blank)...")
            elif field.key == "log_dir":
                widget.setPlaceholderText("Default (logs)...")
            widget.textChanged.connect(self._on_setting_changed)
        elif field.type in [SettingType.STRING, SettingType.PASSWORD, SettingType.INTEGER]:
            widget = StyledLineEdit()
            if field.type == SettingType.PASSWORD:
                widget.setEchoMode(QLineEdit.Password)
            elif field.type == SettingType.INTEGER:
                from PySide6.QtGui import QIntValidator
                widget.setValidator(QIntValidator())

            if field.key == "config_storage_custom_path":
                widget.setPlaceholderText("Custom config directory...")
            elif field.key == "condump_directory":
                widget.setPlaceholderText("Ask (leave blank)...")
            widget.textChanged.connect(self._on_setting_changed)
        elif field.type == SettingType.DROPDOWN:
            widget = StyledComboBox()
            if field.options:
                widget.addItems(field.options)
            if not getattr(field, "transient", False):
                widget.currentTextChanged.connect(self._on_setting_changed)

            if category_key == "providers_credentials" and field.key == "provider":
                widget.currentTextChanged.connect(self._sync_behavior_category_visibility)
            
            # Specific logic for formatting preset
            if field.key == "formatting_preset":
                widget.currentTextChanged.connect(self._on_preset_changed)
            elif field.key == "config_storage_location":
                widget.currentTextChanged.connect(self._on_config_storage_location_changed)
        elif field.type == SettingType.INPUT_PAIR:
            widget = InputPairsWidget(alternative_actions=field.alternative_actions)
            widget.pairsChanged.connect(self._on_setting_changed)
            widget.alternativeActionTriggered.connect(
                lambda action_name, field_key=field.key, widget=widget: self._on_input_pair_alternative_action(
                    category_key, field_key, widget, action_name
                )
            )

        elif field.type == SettingType.REDIRECT:
            btn_text = str(field.default) if field.default else "Open"
            widget = RedirectCard(field.label, field.tooltip or "", btn_text)
            if field.action == "open_credential_manager":
                widget.clicked.connect(self._open_credential_manager)
                
        elif field.type == SettingType.BUTTON:
            widget = StyledButton(field.label)
            # use the default value as button text if provided, else label
            btn_text = str(field.default) if field.default else field.label
            widget.setText(btn_text)
            
            if field.action == "reset_injection":
                widget.clicked.connect(self._reset_injection)
            elif field.action == "reset_formatting":
                widget.clicked.connect(self._reset_formatting)
            elif field.action == "delete_selected_persistent_profile":
                widget.clicked.connect(self._delete_selected_persistent_profile)
            elif field.action == "clear_all_persistent_profiles":
                widget.clicked.connect(self._clear_all_persistent_profiles)
            elif field.action == "check_for_updates":
                widget.clicked.connect(self._check_for_updates)
        
        if widget:
            self.field_widgets[f"{category_key}.{field.key}"] = widget
            
        return widget

    def _iter_fields(self, fields):
        for field in fields:
            yield field
            if field.type == SettingType.ROW:
                yield from self._iter_fields(field.sub_fields)

    def _init_ui(self):

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left Sidebar (Categories + Search)
        left_widget = QWidget()
        left_widget.setFixedWidth(250)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.category_list = QListWidget()
        self.category_list.setFixedWidth(250)
        self.category_list.setSpacing(4)
        self.category_list.setIconSize(QSize(18, 18))
        self.category_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {BrandColors.SIDEBAR_BG};
                border: none;
                outline: none;
                padding: 8px;
                font-size: {BrandColors.FONT_SIZE_REGULAR}; /* Applied to widget directly */
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QListWidget::item {{
                padding: 10px 12px;
                color: {BrandColors.TEXT_SECONDARY};
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
            }}
            QListWidget::item:selected {{
                background-color: {BrandColors.CATEGORY_ACTIVE_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.CATEGORY_ACTIVE_BORDER};
                font-weight: 600;
            }}
            QListWidget::item:selected:hover {{
                background-color: {BrandColors.CATEGORY_ACTIVE_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.CATEGORY_ACTIVE_BORDER};
            }}
            QListWidget::item:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                color: {BrandColors.TEXT_PRIMARY};
            }}
            QScrollBar:vertical {{
                border: none;
                background: {BrandColors.SIDEBAR_BG};
                width: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #555555;
                min-height: 20px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #666666;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        self.category_list.itemClicked.connect(self._on_category_clicked)
        self.category_list.currentItemChanged.connect(self._on_category_selection_changed)
        left_layout.addWidget(self.category_list, 1)

        # Search bar at bottom of sidebar
        self.search_bar = QWidget()
        self.search_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {BrandColors.SIDEBAR_BG};
                border-top: 1px solid {BrandColors.INPUT_BORDER};
            }}
        """)
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(8, 6, 8, 6)
        search_layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search settings…")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BrandColors.INPUT_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 2px solid {BrandColors.INPUT_BORDER};
                border-radius: 6px;
                padding: 6px 10px 6px 28px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-family: {BrandColors.FONT_FAMILY};
            }}
            QLineEdit:focus {{
                border: 2px solid {BrandColors.ACCENT};
            }}
        """)
        search_icon = IconUtils.get_icon(
            IconType.SEARCH,
            color=BrandColors.TEXT_SECONDARY,
            size=16,
            widget=self.search_input,
        )
        self.search_input.addAction(search_icon, QLineEdit.LeadingPosition)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_input, 1)

        left_layout.addWidget(self.search_bar, 0)
        main_layout.addWidget(left_widget)

        # Right Content Area
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(30, 30, 30, 30)
        
        # Scroll Area for Settings
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        
        # Connect scroll signal
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.is_auto_scrolling = False
        
        # Custom Scrollbar Styling
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: {BrandColors.WINDOW_BG};
                width: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #555555;
                min-height: 20px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #666666;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setMaximumWidth(BrandColors.CONTENT_MAX_WIDTH)
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 10, 0) # Add right margin for scrollbar space
        self.scroll_layout.setSpacing(BrandColors.CARD_SPACING)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        
        self.category_widgets = {} # Map category name -> widget (for scrolling)
        self.category_widgets_by_key = {}  # Map category key -> widget (for visibility/selection)
        self.category_items_by_key = {}  # Map category key -> QListWidgetItem
        self.search_targets = []  # List of searchable setting widgets

        # Generate Fields
        for category in SCHEMA:
            # Add to list
            item = QListWidgetItem(category.name)
            item.setData(Qt.UserRole, category.key)
            icon_file = self.SIDEBAR_ICON_MAP.get(category.key)
            if icon_file:
                item.setData(Qt.UserRole + 1, icon_file)
                item.setIcon(self._get_sidebar_icon(icon_file, BrandColors.TEXT_SECONDARY))
            self.category_list.addItem(item)
            self.category_items_by_key[category.key] = item
            
            # Category Card
            card = QWidget()
            card.setStyleSheet(f"""
                QWidget {{
                    background-color: {BrandColors.SIDEBAR_BG};
                    border-radius: 8px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(BrandColors.CARD_PADDING, 18, BrandColors.CARD_PADDING, BrandColors.CARD_PADDING)
            card_layout.setSpacing(4)  # now SettingRow/ToggleRow have their own internal padding
            
            self.category_widgets[category.name] = card
            self.category_widgets_by_key[category.key] = card
            
            # Header
            header = self._create_card_header(category.key, category.name)
            card_layout.addWidget(header)
            
            # Divider (skip when a subsection divider follows immediately)
            if not self._has_immediate_subdivider(category.fields):
                divider = QFrame()
                divider.setFrameShape(QFrame.HLine)
                divider.setFrameShadow(QFrame.Sunken)
                divider.setFixedHeight(1)
                divider.setStyleSheet(f"background-color: {BrandColors.INPUT_BORDER}; border: none;")
                card_layout.addWidget(divider)
                card_layout.addSpacing(6)
            
            # Fields
            for field in category.fields:
                # Handle Divider Type separately as it takes full width
                if field.type == SettingType.DIVIDER:
                    widget = Divider(field.label)
                    card_layout.addWidget(widget)
                    continue
                
                # Handle Description Type separately
                if field.type == SettingType.DESCRIPTION:
                    widget = Description(field.default)
                    self.field_widgets[f"{category.key}.{field.key}"] = widget
                    card_layout.addWidget(widget)
                    continue

                # No handholding for Redirect Type (it renders its own title/description/button)
                if field.type == SettingType.REDIRECT:
                    widget = self._create_field_widget(field, category.key)
                    if widget:
                        self.setting_rows[f"{category.key}.{field.key}"] = widget
                        card_layout.addWidget(widget)
                        self._add_search_target(category, field, widget)
                    continue

                # Use VBox for Textarea to give it more space
                if field.type == SettingType.TEXTAREA:
                    field_container = QWidget()
                    field_container.setStyleSheet("background-color: transparent;")
                    field_layout = QVBoxLayout(field_container)
                    field_layout.setContentsMargins(0, 10, 0, 10)
                    field_layout.setSpacing(6)
                    
                    label = QLabel(field.label)
                    label.setToolTip(field.tooltip or "")
                    # Consistent label styling with SettingRow
                    label.setStyleSheet(f"font-size: {BrandColors.FONT_SIZE_REGULAR}; font-weight: 500; color: {BrandColors.TEXT_SECONDARY}; background-color: transparent;")
                    field_layout.addWidget(label)
                    
                    widget = StyledTextEdit()
                    widget.textChanged.connect(self._on_setting_changed)
                    widget.setToolTip(field.tooltip or "")
                    field_layout.addWidget(widget)
                    self.field_widgets[f"{category.key}.{field.key}"] = widget
                    card_layout.addWidget(field_container)
                    self._add_search_target(category, field, field_container)
                    continue
                
                # Handle ROW type (multiple controls in one row)
                if field.type == SettingType.ROW:
                    sub_widgets = []
                    if field.sub_fields:
                        for sub in field.sub_fields:
                            sub_w = self._create_field_widget(sub, category.key)
                            sub_widgets.append(sub_w)
                    widget = MultiColumnRow(sub_widgets, field.ratios)
                    widget.setToolTip(field.tooltip or "")
                    self.field_widgets[f"{category.key}.{field.key}"] = widget
                    
                    # Use SettingRow for consistent layout
                    row = SettingRow(field.label, widget, field.tooltip)
                    self.setting_rows[f"{category.key}.{field.key}"] = row
                    card_layout.addWidget(row)
                    self._add_search_target(category, field, row)
                    continue
                
                # Standard field types - use appropriate row layout
                widget = self._create_field_widget(field, category.key)
                if widget:
                    # Use ToggleRow for boolean fields (compact horizontal layout)
                    # Pass tooltip as description to show it inline below the label
                    # Use SettingRow for everything else (stacked vertical layout)
                    if field.type == SettingType.BOOLEAN:
                        row = ToggleRow(field.label, widget, field.tooltip, description=field.tooltip)
                    else:
                        row = SettingRow(field.label, widget, field.tooltip)
                    self.setting_rows[f"{category.key}.{field.key}"] = row
                    card_layout.addWidget(row)
                    if field.type != SettingType.BUTTON:
                        self._add_search_target(category, field, row)
            
            self.scroll_layout.addWidget(card)

        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.setAlignment(Qt.AlignHCenter)
        right_layout.addWidget(self.scroll_area)

        # Bottom Buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 20, 0, 0) # Add top margin to separate from content
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
        """)
        IconUtils.apply_icon(self.cancel_btn, IconType.CANCEL, BrandColors.TEXT_PRIMARY, size=16, y_offset=2)
        self.cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.ACCENT};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QPushButton:hover {{
                background-color: #4a80e0;
            }}
        """)
        IconUtils.apply_icon(self.save_btn, IconType.CONFIRM, BrandColors.TEXT_PRIMARY, size=16, y_offset=2)
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)
        
        right_layout.addLayout(button_layout)
        main_layout.addWidget(right_widget)

        # Select first category by default
        self.category_list.setCurrentRow(0)
        self._apply_category_item_icon(self.category_list.currentItem(), active=True)
        
        # Setup dependency tracking
        self.field_defs = {} # Map "category.key" -> SettingField
        self._dep_override_cache = {} # Map "category.key" -> underlying value (when overriding display value)
        for category in SCHEMA:
            for field in self._iter_fields(category.fields):
                full_key = f"{category.key}.{field.key}"
                self.field_defs[full_key] = field
        
        # Debounce timer for updates
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(100)
        self.update_timer.timeout.connect(self._update_dependencies)

        # Debounce timer for settings search
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self._perform_search)

        # Flash state for search highlight
        self._flashed_widget = None
        self._flashed_original_style = ""
        self._flashed_original_effect = None
        self._flash_reset_timer = QTimer()
        self._flash_reset_timer.setSingleShot(True)
        self._flash_reset_timer.setInterval(1000)
        self._flash_reset_timer.timeout.connect(self._clear_flash)

    def _load_values(self):
        override_cache = getattr(self, "_dep_override_cache", None)
        if override_cache is not None:
            override_cache.clear()
        if hasattr(self, "_last_custom_template"):
            delattr(self, "_last_custom_template")

        for category in SCHEMA:
            for field in self._iter_fields(category.fields):
                if getattr(field, "transient", False):
                    continue
                key = f"{category.key}.{field.key}"
                value = self.config_manager.get_setting(category.key, field.key)
                widget = self.field_widgets.get(key)
                
                if widget:
                    widget.blockSignals(True)
                    if field.type == SettingType.BOOLEAN:
                        widget.setChecked(bool(value))
                    elif field.type in [SettingType.STRING, SettingType.DIRECTORY, SettingType.PASSWORD, SettingType.INTEGER]:
                        widget.setText(str(value) if value is not None else "")
                    elif field.type == SettingType.TEXTAREA:
                        widget.setPlainText(str(value) if value is not None else "")
                    elif field.type == SettingType.DROPDOWN:
                        if value and value in field.options:
                            widget.setCurrentText(value)
                    elif field.type == SettingType.INPUT_PAIR:
                        widget.set_pairs(value or [])
                    widget.blockSignals(False)
        
        self._update_dependencies()
        # Trigger preset logic manually after load
        preset_widget = self.field_widgets.get("formatting.formatting_preset")
        if preset_widget:
            self._on_preset_changed(preset_widget.currentText())

        self._sync_config_storage_from_active_dir()
        self._sync_behavior_category_visibility()
        self._refresh_persistent_profile_options()
        self._sync_paged_settings_view()
            
        self.unsaved_changes = False

    def refresh_from_config(self, force: bool = False) -> bool:
        if self.unsaved_changes and not force:
            return False

        try:
            self.config_manager.load_settings()
        except Exception as exc:
            Logger.warning(f"Failed to reload settings: {exc}")

        self._load_values()
        self._sync_application_settings_info()
        return True

    def select_category_by_key(self, category_key: str) -> bool:
        item = self.category_items_by_key.get(category_key)
        card = self.category_widgets_by_key.get(category_key)
        if not item or not card:
            return False

        paged_view = self._should_use_paged_settings_view()

        if item.isHidden():
            item.setHidden(False)
        if not card.isVisible():
            card.setVisible(True)

        self.category_list.setCurrentItem(item)
        if paged_view:
            self._sync_paged_settings_view(scroll_to_top=True)
            return True

        self.is_auto_scrolling = True
        self.scroll_area.ensureWidgetVisible(card)
        QTimer.singleShot(100, lambda: setattr(self, "is_auto_scrolling", False))
        return True

    def focus_setting(self, category_key: str, field_key: str) -> bool:
        category_key = str(category_key or "").strip()
        field_key = str(field_key or "").strip()
        if not category_key or not field_key:
            return False

        full_key = f"{category_key}.{field_key}"
        target = self.setting_rows.get(full_key) or self.field_widgets.get(full_key)
        if not target:
            return False

        self.select_category_by_key(category_key)
        self.scroll_area.ensureWidgetVisible(target)
        self._flash_widget(target)
        return True

    def _on_setting_changed(self):
        self.unsaved_changes = True
        self.update_timer.start()

    def _on_input_pair_alternative_action(
        self,
        category_key: str,
        field_key: str,
        widget: InputPairsWidget,
        action_name: str,
    ) -> None:
        action_name = str(action_name or "").strip()
        if not action_name:
            return

        if (category_key == "network_settings") and (field_key == "api_keys") and (action_name == "generate_api_key"):
            self._generate_api_key(widget)
            return

        Logger.warning(f"Unhandled input pair alternative action: {category_key}.{field_key} -> {action_name}")

    def _generate_api_key(self, widget: InputPairsWidget) -> None:
        existing: set[str] = set()
        for pair in (widget.get_pairs() or []):
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                key_val = str(pair[1] or "").strip()
                if key_val:
                    existing.add(key_val)

        for _ in range(25):
            name, key_val = generate_api_key(prefix="intenserp")
            if key_val in existing:
                continue

            widget.upsert_pair(name, key_val, emit_change=True)
            return

        QMessageBox.warning(
            self,
            "Generate Key",
            "Failed to generate a unique key. Please try again.",
        )

    def _get_widget_value(self, widget):
        if isinstance(widget, Tumbler):
            return widget.isChecked()
        if isinstance(widget, (StyledLineEdit, QLineEdit, DirectoryEntry)):
            return widget.text()
        if isinstance(widget, StyledComboBox):
            return widget.currentText()
        if isinstance(widget, StyledTextEdit):
            return widget.toPlainText()
        return None

    def _set_widget_value(self, widget, value):
        widget.blockSignals(True)
        try:
            if isinstance(widget, Tumbler):
                widget.setChecked(bool(value))
            elif isinstance(widget, (StyledLineEdit, QLineEdit, DirectoryEntry)):
                widget.setText("" if value is None else str(value))
            elif isinstance(widget, StyledComboBox):
                widget.setCurrentText("" if value is None else str(value))
            elif isinstance(widget, StyledTextEdit):
                widget.setPlainText("" if value is None else str(value))
        finally:
            widget.blockSignals(False)

    def _is_dependency_met(self, expr: str | None) -> bool:
        if not expr:
            return True

        parts = [part.strip() for part in str(expr).split("&&")]
        for part in parts:
            if not part:
                continue

            if "==" in part:
                left, right = part.split("==", 1)
                dep_key = left.strip()
                expected = right.strip()
                widget = self.field_widgets.get(dep_key)
                if not widget:
                    return False

                value = self._get_widget_value(widget)
                if isinstance(value, bool):
                    expected_bool = expected.lower() in {"1", "true", "yes", "on"}
                    if value != expected_bool:
                        return False
                else:
                    if str(value or "").strip() != expected:
                        return False
                continue

            if "!=" in part:
                left, right = part.split("!=", 1)
                dep_key = left.strip()
                expected = right.strip()
                widget = self.field_widgets.get(dep_key)
                if not widget:
                    return False

                value = self._get_widget_value(widget)
                if isinstance(value, bool):
                    expected_bool = expected.lower() in {"1", "true", "yes", "on"}
                    if value == expected_bool:
                        return False
                else:
                    if str(value or "").strip() == expected:
                        return False
                continue

            # Backwards-compatible: treat the token as a widget key and check truthiness.
            widget = self.field_widgets.get(part)
            if not widget:
                return False

            value = self._get_widget_value(widget)
            if isinstance(value, bool):
                if not value:
                    return False
            else:
                if not str(value or "").strip():
                    return False

        return True

    def _update_dependencies(self):
        for dependent_key, field_def in (self.field_defs or {}).items():
            depends_expr = getattr(field_def, "depends", None) if field_def else None
            if not depends_expr:
                depends_expr = None

            widget = self.field_widgets.get(dependent_key)
            if not widget:
                continue

            is_met = self._is_dependency_met(depends_expr) if depends_expr else True
            forced_value = getattr(field_def, "force_when_dep_unmet", None) if field_def else None

            desired_mode = None
            should_override = False
            override_value = None

            if not is_met:
                if forced_value is not None:
                    should_override = True
                    override_value = forced_value
                    if isinstance(widget, Tumbler):
                        desired_mode = "forced"
                elif isinstance(widget, Tumbler):
                    # Disabled + not counted: show as OFF and treat as unmet.
                    should_override = True
                    override_value = False
                    desired_mode = "ignored"

            if is_met:
                if dependent_key in self._dep_override_cache:
                    cached_value = self._dep_override_cache.pop(dependent_key)
                    self._set_widget_value(widget, cached_value)
                if isinstance(widget, Tumbler):
                    widget.set_dependency_mode(None)
            else:
                if should_override:
                    if dependent_key not in self._dep_override_cache:
                        self._dep_override_cache[dependent_key] = self._get_widget_value(widget)
                    self._set_widget_value(widget, override_value)
                if isinstance(widget, Tumbler):
                    widget.set_dependency_mode(desired_mode)

            # If there's a SettingRow for this field, enable/disable the whole row
            row = self.setting_rows.get(dependent_key)
            if row:
                row.setEnabled(is_met)
            else:
                widget.setEnabled(is_met)
            if not is_met and isinstance(widget, (StyledLineEdit, DirectoryEntry)):
                widget.set_error(False) # Clear error if disabled

            visible_expr = getattr(field_def, "visible_depends", None) if field_def else None
            if visible_expr is not None:
                should_show = self._is_dependency_met(visible_expr)
                if row:
                    row.setVisible(should_show)
                else:
                    widget.setVisible(should_show)

        self._apply_forced_overrides()

    def _apply_forced_overrides(self) -> None:
        # Reserved for future UI-level forced overrides (none currently).
        return

    def _add_search_target(self, category, field, widget):
        extra_labels = ""
        if field.type == SettingType.ROW and field.sub_fields:
            extra_labels = " ".join(sub.label for sub in field.sub_fields if sub.label)

        self.search_targets.append({
            "label_lower": (field.label or "").lower(),
            "key_lower": (field.key or "").lower(),
            "category_lower": (category.name or "").lower(),
            "category_key_lower": (category.key or "").lower(),
            "category_key": category.key,
            "extra_lower": extra_labels.lower(),
            "widget": widget,
        })

    def _on_search_text_changed(self, text):
        self.search_timer.stop()
        if text.strip():
            self.search_timer.start()
        else:
            self._clear_flash()

    def _score_match(self, query: str, target: dict) -> float:
        candidates = [
            target.get("label_lower", ""),
            target.get("key_lower", ""),
            target.get("category_lower", ""),
            target.get("category_key_lower", ""),
            target.get("extra_lower", ""),
        ]

        best = 0.0
        for cand in candidates:
            if not cand:
                continue
            if query == cand:
                best = max(best, 1.0)
                continue
            if cand.startswith(query):
                best = max(best, 0.95)
                continue
            if query in cand:
                idx = cand.find(query)
                best = max(best, 0.85 + (1 - idx / max(len(cand), 1)) * 0.1)
                continue

            ratio = SequenceMatcher(None, query, cand).ratio()
            best = max(best, ratio * 0.8)

        return best

    def _perform_search(self):
        query = self.search_input.text().strip().lower()
        if not query:
            return

        paged_view = self._should_use_paged_settings_view()
        best_target = None
        best_score = 0.0

        for target in self.search_targets:
            widget = target.get("widget")
            if not widget:
                continue

            if paged_view:
                category_key = target.get("category_key")
                item = self.category_items_by_key.get(category_key) if category_key else None
                if item and item.isHidden():
                    continue
                if widget.isHidden():
                    continue
            elif not widget.isVisible():
                continue

            score = self._score_match(query, target)
            if score > best_score:
                best_score = score
                best_target = target

        if best_target and best_score >= 0.25:
            widget = best_target["widget"]
            if paged_view:
                category_key = best_target.get("category_key")
                if category_key:
                    self.select_category_by_key(category_key)
            self.scroll_area.ensureWidgetVisible(widget)
            self._flash_widget(widget)

    def _flash_widget(self, widget):
        if self._flashed_widget is widget:
            # Already flashed; just restart the timer.
            self._flash_reset_timer.start()
            return

        if self._flashed_widget:
            self._flashed_widget.setStyleSheet(self._flashed_original_style)
            self._flashed_widget.setGraphicsEffect(self._flashed_original_effect)

        self._flashed_widget = widget
        self._flashed_original_style = widget.styleSheet()
        self._flashed_original_effect = widget.graphicsEffect()

        tint_bg = "rgba(88, 149, 252, 0.10)"
        widget.setStyleSheet(
            self._flashed_original_style +
            f"\nbackground-color: {tint_bg};"
            f"\nborder: 2px solid {BrandColors.ACCENT};"
            "\nborder-radius: 6px;"
        )

        effect = QGraphicsColorizeEffect()
        effect.setColor(QColor(BrandColors.ACCENT))
        effect.setStrength(0.15)
        widget.setGraphicsEffect(effect)
        self._flash_reset_timer.start()

    def _clear_flash(self):
        if self._flashed_widget:
            self._flashed_widget.setStyleSheet(self._flashed_original_style)
            self._flashed_widget.setGraphicsEffect(self._flashed_original_effect)
        self._flashed_widget = None
        self._flashed_original_style = ""
        self._flashed_original_effect = None

    def _on_category_clicked(self, item):
        if self._should_use_paged_settings_view():
            if item and item != self.category_list.currentItem():
                self.category_list.setCurrentItem(item)
            self._sync_paged_settings_view(scroll_to_top=True)
            return

        self.is_auto_scrolling = True
        category_name = item.text()
        widget = self.category_widgets.get(category_name)
        if widget:
            self.scroll_area.ensureWidgetVisible(widget)

            # Let's just use a timer to reset the flag to be safe against race conditions
            # I spent WAY too long trying to do this with signals alone
            QTimer.singleShot(100, lambda: setattr(self, "is_auto_scrolling", False))
            # Random bullshit go!
            # This line literally had just 1 change (double quotes instead of single) because
            # I was trying to find some edge cases where we might need different timing
            # but then figured out that this is pointless and just returned the same thing
            # HOWEVER, the undo buffer was full and henceforth I just rewrote the line
            # while I could copy it from the git diff
            # stupid, right?
            # but oh well, that's the story of this line of code
            # why double quotes though? reflex, I guess? who knows
            # anyway, let's call it "Harald's Great Scroll Flag Reset Adventure of 2026"
            # with Harald being the name of the trigger flag
            # also, if you read this, have a one (1) 🍪 cookie
    def _on_scroll(self, value):
        if self.is_auto_scrolling:
            return
        if self._should_use_paged_settings_view():
            return

        # Check if we are at the very bottom
        v_bar = self.scroll_area.verticalScrollBar()
        if value >= v_bar.maximum() - 5: # Small buffer for float inaccuracies
            # Select the last category
            count = self.category_list.count()
            if count > 0:
                for idx in range(count - 1, -1, -1):
                    last_item = self.category_list.item(idx)
                    if not last_item or last_item.isHidden():
                        continue
                    if last_item != self.category_list.currentItem():
                        self.category_list.setCurrentItem(last_item)
                    break
            return

        # Find which category is currently visible
        # To do it, we'll check the vertical position of each category widget relative to the scroll area
        
        scroll_pos = value
        closest_category = None
        
        # We want the category that is at the top of the view
        # The scroll_content coordinates
        
        for name, widget in self.category_widgets.items():
            if not widget.isVisible():
                continue
            # Get widget position relative to scroll content
            widget_pos = widget.y()
            
            # If the widget is above the scroll position (or slightly below), it's a candidate.
            # The last category whose Y position is <= scroll_pos + buffer is the active one.
            
            if widget_pos <= scroll_pos + 50: # 50px buffer
                closest_category = name
            else:
                # Since they are ordered, once we find one that is further down, we can stop
                pass
        
        # If we found a category, select it
        if closest_category:
            # Find the item in the list
            items = self.category_list.findItems(closest_category, Qt.MatchExactly)
            if items:
                item = items[0]
                if item != self.category_list.currentItem():
                    self.category_list.setCurrentItem(item)

    def _sync_config_storage_from_active_dir(self):
        preset_widget = self.field_widgets.get("system_settings.config_storage_location")
        custom_widget = self.field_widgets.get("system_settings.config_storage_custom_path")
        if not preset_widget or not custom_widget:
            return

        active_dir = Path(getattr(self.config_manager, "config_dir", "config_data")).resolve()
        preset, custom_path = infer_preset_from_config_dir(active_dir)

        preset_widget.blockSignals(True)
        options = [preset_widget.itemText(i) for i in range(preset_widget.count())]
        preset_to_apply = preset if preset in options else "Custom"
        preset_widget.setCurrentText(preset_to_apply)
        preset_widget.blockSignals(False)

        if preset_to_apply == "Custom":
            custom_widget.blockSignals(True)
            custom_widget.setText(custom_path)
            custom_widget.blockSignals(False)

        self._on_config_storage_location_changed(preset_to_apply)

    def _is_behavior_category(self, category_key: str) -> bool:
        return bool(category_key) and str(category_key).endswith("_behavior")

    def _get_selected_category_key(self) -> str | None:
        item = self.category_list.currentItem() if hasattr(self, "category_list") else None
        if not item:
            return None
        key = item.data(Qt.UserRole)
        if key is None:
            return None
        return str(key)

    def _should_use_paged_settings_view(self) -> bool:
        widget = self.field_widgets.get("application_settings.paged_settings_view")
        if isinstance(widget, Tumbler):
            return widget.isChecked()
        return bool(self.config_manager.get_setting("application_settings", "paged_settings_view"))

    def _sync_paged_settings_view(self, *_args, scroll_to_top: bool = False) -> None:
        enabled = self._should_use_paged_settings_view()
        selected_key = self._get_selected_category_key()
        if not selected_key:
            return

        prev_enabled = getattr(self, "_paged_settings_view_enabled", None)
        initial_apply = prev_enabled is None
        mode_changed = (not initial_apply) and (prev_enabled != enabled)
        self._paged_settings_view_enabled = enabled

        for key, card in (self.category_widgets_by_key or {}).items():
            if not card:
                continue

            item = self.category_items_by_key.get(key)
            base_visible = (item is None) or (not item.isHidden())

            if enabled:
                desired_visible = base_visible and (key == selected_key)
            else:
                desired_visible = base_visible

            # was done for paged_settings_view
            # because the show_only_active_provider_behavior setting
            # showed the active provider behavior cat anyway
            # even if it's not selected (overridden)
            desired_hidden = not desired_visible
            if card.isHidden() != desired_hidden:
                card.setHidden(desired_hidden)

        if enabled:
            if scroll_to_top or mode_changed or (initial_apply and enabled):
                self.is_auto_scrolling = True
                try:
                    self.scroll_area.verticalScrollBar().setValue(0)
                finally:
                    QTimer.singleShot(100, lambda: setattr(self, "is_auto_scrolling", False))
        else:
            if mode_changed:
                card = self.category_widgets_by_key.get(selected_key)
                if card:
                    self.is_auto_scrolling = True
                    try:
                        self.scroll_area.ensureWidgetVisible(card)
                    finally:
                        QTimer.singleShot(100, lambda: setattr(self, "is_auto_scrolling", False))

    def _should_show_only_active_provider_behavior(self) -> bool:
        widget = self.field_widgets.get("application_settings.show_only_active_provider_behavior")
        if isinstance(widget, Tumbler):
            return widget.isChecked()
        return bool(self.config_manager.get_setting("application_settings", "show_only_active_provider_behavior"))

    def _get_selected_provider(self) -> DriverProvider:
        widget = self.field_widgets.get("providers_credentials.provider")
        if isinstance(widget, StyledComboBox):
            provider_setting = widget.currentText()
        else:
            provider_setting = self.config_manager.get_setting("providers_credentials", "provider")
        return DriverProvider.from_setting(provider_setting)

    def _set_category_visible(self, category_key: str, visible: bool) -> None:
        item = self.category_items_by_key.get(category_key)
        if item:
            item.setHidden(not visible)

        card = self.category_widgets_by_key.get(category_key)
        if card:
            card.setVisible(visible)

    def _sync_behavior_category_visibility(self, *_args) -> None:
        behavior_keys = [key for key in (self.category_widgets_by_key or {}) if self._is_behavior_category(key)]
        if not behavior_keys:
            return

        if not self._should_show_only_active_provider_behavior():
            for key in behavior_keys:
                self._set_category_visible(key, True)
            self._sync_paged_settings_view()
            return

        active_key = self.BEHAVIOR_CATEGORY_BY_PROVIDER.get(self._get_selected_provider())
        if not active_key:
            for key in behavior_keys:
                self._set_category_visible(key, True)
            self._sync_paged_settings_view()
            return

        for key in behavior_keys:
            self._set_category_visible(key, key == active_key)

        current_item = self.category_list.currentItem()
        if current_item and current_item.isHidden():
            preferred_item = self.category_items_by_key.get(active_key)
            if preferred_item and not preferred_item.isHidden():
                self.category_list.setCurrentItem(preferred_item)
                preferred_card = self.category_widgets_by_key.get(active_key)
                if preferred_card:
                    self.scroll_area.ensureWidgetVisible(preferred_card)
                self._sync_paged_settings_view()
                return

            for i in range(self.category_list.count()):
                item = self.category_list.item(i)
                if item and not item.isHidden():
                    self.category_list.setCurrentItem(item)
                    card = self.category_widgets.get(item.text())
                    if card:
                        self.scroll_area.ensureWidgetVisible(card)
                    self._sync_paged_settings_view()
                    return

        self._sync_paged_settings_view()

    def _on_config_storage_location_changed(self, text: str):
        is_custom = text == "Custom"
        custom_key = "system_settings.config_storage_custom_path"
        row = self.setting_rows.get(custom_key)
        widget = self.field_widgets.get(custom_key)

        if row:
            row.setEnabled(is_custom)
        elif widget:
            widget.setEnabled(is_custom)

        if not is_custom and isinstance(widget, (StyledLineEdit, DirectoryEntry)):
            widget.set_error(False)

    def _on_preset_changed(self, text):
        template_widget = self.field_widgets.get("formatting.formatting_template")
        if not template_widget:
            return

        if text == "Custom":
            template_widget.setEnabled(True)
            # We need to store the custom value temporarily if we switch away from Custom.
            
            if hasattr(self, "_last_custom_template"):
                # Ignoring lint because we know it exists here
                template_widget.setPlainText(self._last_custom_template)
                
        else:
            # If the widget is enabled, it means we are on Custom (or just started).
            if template_widget.isEnabled():
                self._last_custom_template = template_widget.toPlainText()
            
            template_widget.setEnabled(False)
            if text == "Classic - Name":
                template_widget.setPlainText("{{name}}: {{content}}")
            elif text == "Classic - Role":
                template_widget.setPlainText("{{role}}: {{content}}")
            elif text == "XML-Like - Name":
                template_widget.setPlainText("<{{name}}>{{content}}</{{name}}>")
            elif text == "XML-Like - Role":
                template_widget.setPlainText("<{{role}}>{{content}}</{{role}}>")
            elif text == "Divided - Name":
                template_widget.setPlainText("### {{name}}\n{{content}}")
            elif text == "Divided - Role":
                template_widget.setPlainText("### {{role}}\n{{content}}")

    def _sync_application_settings_info(self):
        version_widget = self.field_widgets.get("application_settings.current_version_info")
        if isinstance(version_widget, QLabel):
            version_widget.setText(f"Current version: {read_local_version()}")

    def _set_update_status(self, text: str):
        status_widget = self.field_widgets.get("application_settings.update_status_info")
        if isinstance(status_widget, QLabel):
            status_widget.setText(text)

    def _check_for_updates(self):
        if getattr(self, "_update_check_in_progress", False):
            return

        self._update_check_in_progress = True
        self._set_update_status("Status: Checking...")

        btn_key = "application_settings.check_for_updates_btn"
        btn = self.field_widgets.get(btn_key)
        original_text = btn.text() if isinstance(btn, QPushButton) else "Check"

        if isinstance(btn, QPushButton):
            btn.setEnabled(False)
            btn.setText("Checking...")

        def worker():
            result = check_for_updates()
            self.update_check_finished.emit(result, original_text)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_update_check_result(self, result, original_button_text: str):
        self._update_check_in_progress = False

        btn = self.field_widgets.get("application_settings.check_for_updates_btn")
        if isinstance(btn, QPushButton):
            btn.setEnabled(True)
            btn.setText(original_button_text or "Check")

        self._sync_application_settings_info()

        if result.error:
            self._set_update_status("Status: Failed to check for updates.")
            QMessageBox.warning(
                self,
                "Check For Updates",
                "Failed to check for updates.\n\n"
                f"{result.error}",
            )
            return

        if result.update_available:
            sev = getattr(result, "remote_severity", None)
            sev_suffix = f", severity: {sev}" if sev is not None else ""
            self._set_update_status(f"Status: Update available ({result.remote_version}{sev_suffix}).")
            dialog = UpdateAvailableDialog(
                UpdateAvailableInfo(
                    local_version=str(result.local_version or "unknown"),
                    remote_version=str(result.remote_version or "unknown"),
                    remote_auto_updateable=getattr(result, "remote_auto_updateable", None),
                    remote_severity=getattr(result, "remote_severity", None),
                ),
                parent=self,
            )
            dialog.exec()
            return

        self._set_update_status(f"Status: Up to date ({result.local_version}).")
        QMessageBox.information(
            self,
            "No Updates Found",
            "You're up to date.\n\n"
            f"Current: {result.local_version}\n"
            f"Latest: {result.remote_version}",
        )

    def _reset_formatting(self):
        preset_widget = self.field_widgets.get("formatting.formatting_preset")
        if preset_widget:
            preset_widget.setCurrentText("Classic - Name")

    def _reset_injection(self):
        position_widget = self.field_widgets.get("formatting.injection_position")
        content_widget = self.field_widgets.get("formatting.injection_content")
        
        if position_widget:
            position_widget.setCurrentText("Before")
        
        if content_widget:
            content_widget.setPlainText("[Important Instructions]")

    def _get_profiles_root_dir(self) -> Path:
        base_dir = Path(getattr(self.config_manager, "config_dir", "config_data")).resolve()
        return (base_dir / "playwright_profiles").resolve()

    def _format_provider_label(self, provider_key: str) -> str:
        for provider in DriverProvider:
            if provider.key == provider_key:
                if provider is DriverProvider.GLM_CHAT:
                    return "GLM"
                return provider.value

        raw = str(provider_key or "").strip()
        if not raw:
            return "Unknown"
        return raw.replace("_", " ").title()

    def _build_persistent_profile_entries(self) -> list[tuple[str, str, Path]]:
        legacy: list[tuple[tuple[str], tuple[str, str, Path]]] = []
        accounts: list[tuple[tuple[str, str, int], tuple[str, str, Path]]] = []

        profiles_root = self._get_profiles_root_dir()

        # Legacy profiles: [config_dir]/playwright_profiles/<provider_key>/
        try:
            if profiles_root.exists() and profiles_root.is_dir():
                for child in profiles_root.iterdir():
                    if not child.is_dir():
                        continue
                    if child.name in {"ece", "accounts"}:
                        continue
                    provider_name = self._format_provider_label(child.name)
                    label = f"[Legacy] {provider_name}"
                    token = str(child.resolve())
                    legacy.append(((provider_name.lower(),), (token, label, child)))
        except Exception:
            pass

        # Account profiles: [config_dir]/playwright_profiles/accounts/<provider_key>/<hash>[_slot]/
        config_dir = Path(getattr(self.config_manager, "config_dir", "config_data")).resolve()
        account_roots = [profiles_root / "accounts", profiles_root / "ece"]
        account_manager = None

        pre_roots = [root for root in account_roots if root.exists() and root.is_dir()]
        if pre_roots:
            try:
                from ece.manager import EceManager

                account_manager = EceManager(config_dir)
            except Exception as exc:
                Logger.debug(f"Accounts: unable to read credentials for profile labels: {exc}")
                account_manager = None

            # EceManager may migrate/rename directories; re-evaluate roots after init
            roots = [root for root in account_roots if root.exists() and root.is_dir()]
            for root in roots:
                try:
                    provider_dirs = [p for p in root.iterdir() if p.is_dir()]
                except Exception:
                    provider_dirs = []

                for provider_dir in provider_dirs:
                    provider_key = provider_dir.name
                    provider_name = self._format_provider_label(provider_key)

                    hash_to_email: dict[str, str] = {}
                    if account_manager is not None:
                        try:
                            pairs = account_manager.get_provider_pairs(provider_key)
                            for pair in pairs:
                                email = (pair.email or "").strip()
                                if not email:
                                    continue
                                ident = account_manager.get_profile_dir(provider_key, email=email, slot=0).name
                                hash_to_email[ident] = email
                        except Exception:
                            hash_to_email = {}

                    try:
                        ident_dirs = [p for p in provider_dir.iterdir() if p.is_dir()]
                    except Exception:
                        ident_dirs = []

                    for ident_dir in ident_dirs:
                        ident_name = ident_dir.name
                        base_ident = ident_name
                        slot = 0
                        if "_" in ident_name:
                            maybe_base, maybe_slot = ident_name.rsplit("_", 1)
                            if maybe_slot.isdigit():
                                base_ident = maybe_base
                                try:
                                    slot = int(maybe_slot)
                                except Exception:
                                    slot = 0

                        email = None
                        if base_ident != "manual":
                            email = hash_to_email.get(base_ident)

                        if base_ident == "manual":
                            label = f"[Account] {provider_name} - manual"
                        elif email:
                            label = f"[Account] {provider_name} - {email}"
                        else:
                            label = f"[Account] {provider_name} - {base_ident}"

                        if slot > 0:
                            label = f"{label} (slot {slot})"

                        token = str(ident_dir.resolve())
                        sort_ident = (email or base_ident or "").lower()
                        accounts.append(((provider_name.lower(), sort_ident, slot), (token, label, ident_dir)))

        legacy_sorted = [item for _k, item in sorted(legacy, key=lambda t: t[0])]
        accounts_sorted = [item for _k, item in sorted(accounts, key=lambda t: t[0])]
        return legacy_sorted + accounts_sorted

    def _refresh_persistent_profile_options(self):
        select_widget = self.field_widgets.get("system_settings.persistent_profile_to_delete")
        delete_btn = self.field_widgets.get("system_settings.delete_persistent_profile_btn")

        if not isinstance(select_widget, StyledComboBox):
            return

        old_token = select_widget.currentData(Qt.UserRole)
        entries = self._build_persistent_profile_entries()
        self._persistent_profile_entries = {token: (label, path) for token, label, path in entries}

        select_widget.blockSignals(True)
        try:
            select_widget.clear()

            if not entries:
                select_widget.addItem("(No saved profiles found)", "")
                select_widget.setEnabled(False)
                if isinstance(delete_btn, QPushButton):
                    delete_btn.setEnabled(False)
                return

            select_widget.setEnabled(True)
            if isinstance(delete_btn, QPushButton):
                delete_btn.setEnabled(True)

            for token, label, _path in entries:
                select_widget.addItem(label, token)

            if old_token and str(old_token) in self._persistent_profile_entries:
                idx = select_widget.findData(old_token, Qt.UserRole)
                if idx >= 0:
                    select_widget.setCurrentIndex(idx)
        finally:
            select_widget.blockSignals(False)

    def _get_selected_persistent_profile(self) -> tuple[str, str, Path] | None:
        select_widget = self.field_widgets.get("system_settings.persistent_profile_to_delete")
        if not isinstance(select_widget, StyledComboBox):
            return None

        token = select_widget.currentData(Qt.UserRole)
        if token is None:
            token = ""

        entry = self._persistent_profile_entries.get(str(token))
        if not entry:
            return None

        label, path = entry
        return (str(token), label, path)

    def _delete_selected_persistent_profile(self):
        selected = self._get_selected_persistent_profile()
        if not selected:
            QMessageBox.information(self, "Delete Profile", "No saved browser profile is selected.")
            return

        _token, label, profile_dir = selected
        base_dir = Path(getattr(self.config_manager, "config_dir", "config_data")).resolve()

        try:
            profile_dir.resolve().relative_to(base_dir)
        except Exception:
            QMessageBox.warning(
                self,
                "Delete Profile",
                "Refusing to delete profile: resolved path is outside the config directory.",
            )
            return

        if not profile_dir.exists():
            QMessageBox.information(self, "Delete Profile", "That profile folder no longer exists.")
            self._refresh_persistent_profile_options()
            return

        reply = QMessageBox.question(
            self,
            "Delete Profile",
            "This will permanently delete the selected saved browser profile:\n\n"
            f"{label}\n\n"
            "This removes cookies/local storage and will log you out.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            shutil.rmtree(profile_dir)
            Logger.success(f"Deleted persistent profile: {label}")
            QMessageBox.information(self, "Delete Profile", "Profile deleted successfully.")
        except Exception as e:
            Logger.error(f"Error deleting persistent profile: {e}")
            QMessageBox.warning(self, "Delete Profile", f"Failed to delete profile:\n\n{e}")
        finally:
            self._refresh_persistent_profile_options()

    def _clear_all_persistent_profiles(self):
        profiles_root = self._get_profiles_root_dir()
        base_dir = Path(getattr(self.config_manager, "config_dir", "config_data")).resolve()

        try:
            profiles_root.resolve().relative_to(base_dir)
        except Exception:
            QMessageBox.warning(
                self,
                "Clear All Profiles",
                "Refusing to clear profiles: resolved path is outside the config directory.",
            )
            return

        if not profiles_root.exists():
            QMessageBox.information(self, "Clear All Profiles", "No saved browser profiles were found.")
            self._refresh_persistent_profile_options()
            return

        reply = QMessageBox.question(
            self,
            "Clear All Profiles",
            "This will delete ALL saved browser profiles used for Persistent Sessions.\n\n"
            "This removes cookies/local storage and will log you out of all providers and saved accounts.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            shutil.rmtree(profiles_root)
            Logger.success("Cleared all persistent profiles.")
            QMessageBox.information(self, "Clear All Profiles", "All profiles cleared successfully.")
        except Exception as e:
            Logger.error(f"Error clearing all persistent profiles: {e}")
            QMessageBox.warning(self, "Clear All Profiles", f"Failed to clear profiles:\n\n{e}")
        finally:
            self._refresh_persistent_profile_options()

    def save_settings(self):
        validation_errors = []

        # Snapshot old values for fields with "affects" so we can detect changes later
        _affects_snapshot = {}
        for _cat in SCHEMA:
            for _field in self._iter_fields(_cat.fields):
                _affects_list = getattr(_field, "affects", None)
                if _affects_list:
                    _key = f"{_cat.key}.{_field.key}"
                    _affects_snapshot[_key] = (
                        self.config_manager.get_setting(_cat.key, _field.key),
                        _affects_list,
                    )

        active_config_dir = Path(getattr(self.config_manager, "config_dir", "config_data")).resolve()
        storage_preset_widget = self.field_widgets.get("system_settings.config_storage_location")
        storage_custom_widget = self.field_widgets.get("system_settings.config_storage_custom_path")

        requested_preset = storage_preset_widget.currentText() if storage_preset_widget else "Relative"
        requested_custom_path = storage_custom_widget.text() if storage_custom_widget else ""

        prev_preset = self.config_manager.get_setting("system_settings", "config_storage_location")
        prev_custom_path = self.config_manager.get_setting("system_settings", "config_storage_custom_path")

        target_config_dir = None
        try:
            target_config_dir = resolve_config_dir(requested_preset, requested_custom_path).resolve()
        except Exception as e:
            if isinstance(storage_custom_widget, (StyledLineEdit, DirectoryEntry)):
                storage_custom_widget.set_error(True)
            validation_errors.append(f"Config Storage Location: {e}")
        else:
            if isinstance(storage_custom_widget, (StyledLineEdit, DirectoryEntry)):
                storage_custom_widget.set_error(False)
        
        for category in SCHEMA:
            for field in self._iter_fields(category.fields):
                if getattr(field, "transient", False):
                    continue
                key = f"{category.key}.{field.key}"
                widget = self.field_widgets.get(key)
                
                if widget:
                    value = None
                    if field.type == SettingType.BOOLEAN:
                        value = widget.isChecked()
                    elif field.type in [SettingType.STRING, SettingType.PASSWORD]:
                        value = widget.text()
                    elif field.type == SettingType.DIRECTORY:
                        value = widget.text().strip()
                        if getattr(field, "nullable", False) and not value:
                            value = None
                    elif field.type == SettingType.INTEGER:
                        text_val = widget.text()
                        value = int(text_val) if text_val else 0
                    elif field.type == SettingType.TEXTAREA:
                        value = widget.toPlainText()
                    elif field.type == SettingType.DROPDOWN:
                        value = widget.currentText()
                    elif field.type == SettingType.INPUT_PAIR:
                        value = widget.get_pairs()
                    elif field.type in [SettingType.BUTTON, SettingType.DIVIDER, SettingType.DESCRIPTION, SettingType.ROW, SettingType.REDIRECT]:
                        continue # These don't have values to save
                        
                    # Check dependencies
                    is_enabled = self._is_dependency_met(field.depends) if field.depends else True

                    if (not is_enabled) and (key in self._dep_override_cache):
                        value = self._dep_override_cache[key]
                        
                    if is_enabled:
                        # Check required
                        if field.required and not value:
                            if isinstance(widget, (StyledLineEdit, DirectoryEntry)):
                                widget.set_error(True)
                            validation_errors.append(f"{field.label}: This field is required.")
                        
                        # Run validator if exists
                        elif field.validator:
                            try:
                                field.validator(value)
                                if isinstance(widget, (StyledLineEdit, DirectoryEntry)):
                                    widget.set_error(False)
                            except ValueError as e:
                                if isinstance(widget, (StyledLineEdit, DirectoryEntry)):
                                    widget.set_error(True)
                                validation_errors.append(f"{field.label}: {str(e)}")
                    else:
                        # If disabled, ensure no error state
                        if isinstance(widget, (StyledLineEdit, DirectoryEntry)):
                            widget.set_error(False)
                    
                    if not validation_errors:
                        self.config_manager.set_setting(category.key, field.key, value)
        
        if validation_errors:
            error_msg = "\n".join(validation_errors)
            QMessageBox.warning(self, "Validation Error", f"Please fix the following errors:\n\n{error_msg}")
            return

        perform_migration = False
        if target_config_dir and target_config_dir != active_config_dir:
            reply = QMessageBox.question(
                self,
                "Move Config Storage",
                "You're about to change where configuration data is stored.\n\n"
                f"From:\n{active_config_dir}\n\n"
                f"To:\n{target_config_dir}\n\n"
                "This will save all settings, replace the destination directory contents, "
                "and restart the application.\n\n"
                "Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply != QMessageBox.Yes:
                rollback_preset = prev_preset or infer_preset_from_config_dir(active_config_dir)[0]
                rollback_custom = prev_custom_path or infer_preset_from_config_dir(active_config_dir)[1]
                if storage_preset_widget:
                    storage_preset_widget.blockSignals(True)
                    storage_preset_widget.setCurrentText(rollback_preset)
                    storage_preset_widget.blockSignals(False)
                if storage_custom_widget:
                    storage_custom_widget.blockSignals(True)
                    storage_custom_widget.setText(rollback_custom)
                    storage_custom_widget.blockSignals(False)

                self._on_config_storage_location_changed(rollback_preset)
                self.config_manager.set_setting("system_settings", "config_storage_location", rollback_preset)
                self.config_manager.set_setting("system_settings", "config_storage_custom_path", rollback_custom)
                target_config_dir = active_config_dir
            else:
                perform_migration = True

        self.config_manager.save_settings()
        self.unsaved_changes = False

        # Determine which UI components are affected by the changes
        _affected = set()
        for _key, (_old_val, _affects_list) in _affects_snapshot.items():
            _cat, _fld = _key.split(".", 1)
            _new_val = self.config_manager.get_setting(_cat, _fld)
            if _new_val != _old_val:
                _affected.update(_affects_list)

        self.settings_saved.emit(_affected)

        if not perform_migration:
            self.close()
            return

        try:
            migrate_config_dir(active_config_dir, target_config_dir)
            write_pointer_file(target_config_dir)
            QMessageBox.information(
                self,
                "Config Storage",
                "Configuration migrated successfully.\n\nRestarting now...",
            )
            self.restart_requested.emit()
            self.close()
        except Exception as e:
            Logger.error(f"Config migration failed: {e}")

            rollback_preset = prev_preset or infer_preset_from_config_dir(active_config_dir)[0]
            rollback_custom = prev_custom_path or infer_preset_from_config_dir(active_config_dir)[1]
            self.config_manager.set_setting("system_settings", "config_storage_location", rollback_preset)
            self.config_manager.set_setting("system_settings", "config_storage_custom_path", rollback_custom)
            self.config_manager.save_settings()

            self._sync_config_storage_from_active_dir()
            QMessageBox.warning(
                self,
                "Config Migration Failed",
                "Failed to migrate configuration to the new location.\n\n"
                f"Error:\n{e}",
            )
            return

    def closeEvent(self, event):
        dialog = getattr(self, "_credential_manager_dialog", None)
        if dialog and dialog.isVisible():
            QMessageBox.information(
                self,
                "Credential Manager",
                "Close the Credential Manager window before closing Settings.",
            )
            event.ignore()
            return

        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Are you sure you want to discard them?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.unsaved_changes = False
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def _open_credential_manager(self) -> None:
        existing = getattr(self, "_credential_manager_dialog", None)
        if existing and existing.isVisible():
            existing.activateWindow()
            existing.raise_()
            return

        dialog = CredentialManagerDialog(self.config_manager, parent=self)
        self._credential_manager_dialog = dialog

        def _clear_ref(*_args) -> None:
            if getattr(self, "_credential_manager_dialog", None) is dialog:
                self._credential_manager_dialog = None

        dialog.finished.connect(_clear_ref)
        dialog.open()
