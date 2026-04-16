from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config.loadouts import LoadoutDefinition
from drivers.providers import DriverProvider
from ui.core.brand import BrandColors
from ui.core.icons import IconType, IconUtils
from ui.niche.hotswap_dialog import PROVIDER_ICON_MAP
from ui.widgets.components import HintCard, StyledComboBox
from ui.widgets.smooth_scroll_area import SmoothScrollArea

class _ElidedTitleLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full_text = str(text or "")
        self._apply_elided_text()
        self.setToolTip(self._full_text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elided_text()

    def _apply_elided_text(self) -> None:
        metrics = QFontMetrics(self.font())
        available_width = max(0, self.contentsRect().width())
        if available_width <= 0:
            super().setText(self._full_text)
            return
        super().setText(metrics.elidedText(self._full_text, Qt.ElideRight, available_width))


class _LoadoutOptionCard(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        *,
        provider_name: str,
        loadout_name: str,
        subtitle: str,
        selected: bool,
        show_checkmark: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._loadout_name = str(loadout_name or "").strip()
        self._selected = bool(selected)
        self._show_checkmark = bool(show_checkmark)

        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("loadoutOptionCard")
        self.setMinimumHeight(78)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self._state_icon_label = QLabel()
        self._state_icon_label.setStyleSheet("background-color: transparent;")
        self._state_icon_label.setFixedSize(30, 30)
        self._state_icon_label.setAlignment(Qt.AlignCenter)
        self._refresh_state_icon(provider_name)
        layout.addWidget(self._state_icon_label, 0, Qt.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self._title_label = _ElidedTitleLabel(self._loadout_name)
        self._title_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY};
            font-size: {BrandColors.FONT_SIZE_XLARGE};
            font-weight: 800;
            background-color: transparent;
            """
        )
        self._title_label.setMinimumHeight(30)
        text_layout.addWidget(self._title_label)

        self._subtitle_label = QLabel(str(subtitle or ""))
        self._subtitle_label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_PRIMARY if self._selected else BrandColors.TEXT_SECONDARY};
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-weight: 400;
            background-color: transparent;
            """
        )
        self._subtitle_label.setWordWrap(False)
        text_layout.addWidget(self._subtitle_label)

        layout.addLayout(text_layout, 1)
        self._apply_style()

    def _apply_style(self) -> None:
        if self._selected:
            background = BrandColors.CATEGORY_ACTIVE_BG
            border = BrandColors.CATEGORY_ACTIVE_BORDER
            hover = BrandColors.CATEGORY_ACTIVE_BG
        else:
            background = BrandColors.SIDEBAR_BG
            border = BrandColors.INPUT_BORDER
            hover = BrandColors.ITEM_HOVER

        self.setStyleSheet(
            f"""
            QFrame#loadoutOptionCard {{
                background-color: {background};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QFrame#loadoutOptionCard:hover {{
                background-color: {hover};
                border: 1px solid {BrandColors.CATEGORY_ACTIVE_BORDER if not self._selected else BrandColors.ACCENT};
            }}
            """
        )

    def _refresh_state_icon(self, provider_name: str) -> None:
        if self._show_checkmark:
            pixmap = IconUtils.get_pixmap(
                IconType.CONFIRM,
                color=BrandColors.ACCENT,
                size=22,
                dpr=self.devicePixelRatioF(),
            )
            if not pixmap.isNull():
                self._state_icon_label.setPixmap(pixmap)
            return

        icon_file = PROVIDER_ICON_MAP.get(str(provider_name or "").strip())
        if not icon_file:
            return

        pixmap = IconUtils.get_pixmap(
            icon_file,
            color=BrandColors.TEXT_PRIMARY,
            size=24,
            dpr=self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            self._state_icon_label.setPixmap(pixmap)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self._loadout_name)
        super().mouseReleaseEvent(event)


class LoadoutSwitchDialog(QDialog):
    """Modal picker for selecting the active loadout for the current provider."""

    def __init__(
        self,
        provider_name: str,
        loadouts: list[LoadoutDefinition],
        current_loadout_name: str | None = None,
        parent=None,
        *,
        provider_loadouts: dict[DriverProvider, list[LoadoutDefinition]] | None = None,
        current_loadout_names: dict[DriverProvider, str | None] | None = None,
        initial_provider: DriverProvider | None = None,
    ):
        super().__init__(parent)
        self._selected_loadout_name: Optional[str] = None
        self._provider_name = str(provider_name or "").strip()
        self._current_loadout_name = str(current_loadout_name or "").strip() or None
        self._provider_loadouts = self._normalize_provider_loadouts(
            provider_name,
            loadouts,
            provider_loadouts,
        )
        self._provider_order = list(self._provider_loadouts.keys())
        self._active_provider = self._resolve_initial_provider(
            initial_provider,
            provider_name,
            loadouts,
        )
        self._deferred_apply = provider_loadouts is not None
        self._show_provider_dropdown = len(self._provider_order) > 1
        self._current_names_by_provider = self._build_current_names(current_loadout_names)
        self._draft_names_by_provider = dict(self._current_names_by_provider)
        self._provider_dropdown: StyledComboBox | None = None
        self._desc_label: QLabel | None = None
        self._list_layout: QVBoxLayout | None = None

        self.setWindowTitle("Switch Loadout")
        self.setModal(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(460 if self._deferred_apply else 420)
        self.setMinimumHeight(500 if self._deferred_apply else 420)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("loadoutSwitchCard")
        card.setStyleSheet(
            f"""
            QFrame#loadoutSwitchCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Switch Loadout")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_TITLE};
            font-weight: 800;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        layout.addWidget(title)

        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setAlignment(Qt.AlignCenter)
        self._desc_label.setTextFormat(Qt.RichText)
        self._desc_label.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 2px 4px;
            """
        )
        layout.addWidget(self._desc_label)

        if self._show_provider_dropdown:
            layout.addWidget(self._build_provider_dropdown())

        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #555555;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            """
        )
        list_root = QWidget()
        list_root.setStyleSheet("background-color: transparent;")
        self._list_layout = QVBoxLayout(list_root)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(10)
        self._rebuild_loadout_buttons()
        scroll.setWidget(list_root)
        layout.addWidget(scroll, 1)

        if self._deferred_apply:
            layout.addWidget(self._build_confirm_buttons())
        else:
            cancel = self._build_footer_button(
                "Cancel",
                IconType.CANCEL,
                BrandColors.SIDEBAR_BG,
                BrandColors.ITEM_HOVER,
            )
            cancel.clicked.connect(self.reject)
            layout.addWidget(cancel)

        self._refresh_description()
        QTimer.singleShot(0, self._clear_initial_focus)

    @staticmethod
    def _provider_icon_file(provider: DriverProvider | None) -> str | None:
        if provider is None:
            return None
        return PROVIDER_ICON_MAP.get(provider.value)

    def _normalize_provider_loadouts(
        self,
        provider_name: str,
        loadouts: list[LoadoutDefinition],
        provider_loadouts: dict[DriverProvider, list[LoadoutDefinition]] | None,
    ) -> dict[DriverProvider, list[LoadoutDefinition]]:
        if provider_loadouts:
            return {
                provider: list(provider_items or [])
                for provider, provider_items in provider_loadouts.items()
                if isinstance(provider, DriverProvider) and provider_items
            }

        provider = DriverProvider.from_setting(provider_name)
        if provider is None and loadouts:
            provider = loadouts[0].provider
        if provider is None:
            return {}
        return {provider: list(loadouts or [])}

    def _resolve_initial_provider(
        self,
        initial_provider: DriverProvider | None,
        provider_name: str,
        loadouts: list[LoadoutDefinition],
    ) -> DriverProvider | None:
        if initial_provider in self._provider_loadouts:
            return initial_provider

        provider = DriverProvider.from_setting(provider_name)
        if provider in self._provider_loadouts:
            return provider

        if loadouts:
            loadout_provider = loadouts[0].provider
            if loadout_provider in self._provider_loadouts:
                return loadout_provider

        return self._provider_order[0] if self._provider_order else None

    def _build_current_names(
        self,
        current_loadout_names: dict[DriverProvider, str | None] | None,
    ) -> dict[DriverProvider, str | None]:
        names: dict[DriverProvider, str | None] = {}
        raw_names = current_loadout_names or {}

        for provider, provider_loadouts in self._provider_loadouts.items():
            candidate = str(raw_names.get(provider) or "").strip() or None
            if provider == self._active_provider and self._current_loadout_name:
                candidate = candidate or self._current_loadout_name
            if candidate and any(loadout.name == candidate for loadout in provider_loadouts):
                names[provider] = candidate
            else:
                names[provider] = provider_loadouts[0].name if provider_loadouts else None

        return names

    def _provider_display_name(self, provider: DriverProvider | None = None) -> str:
        target = provider if provider is not None else self._active_provider
        return target.value if target is not None else self._provider_name

    def _build_provider_dropdown(self) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel("Provider")
        label.setStyleSheet(
            f"""
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            font-weight: 600;
            """
        )
        layout.addWidget(label)

        dropdown = StyledComboBox()
        dropdown.setIconSize(QSize(16, 16))
        for provider in self._provider_order:
            icon_file = self._provider_icon_file(provider)
            icon = IconUtils.get_icon(
                icon_file,
                color=BrandColors.TEXT_PRIMARY,
                size=16,
                widget=dropdown,
            ) if icon_file else None
            if icon is not None and not icon.isNull():
                dropdown.addItem(icon, provider.value, provider.key)
            else:
                dropdown.addItem(provider.value, provider.key)

        active_index = (
            self._provider_order.index(self._active_provider)
            if self._active_provider in self._provider_order
            else 0
        )
        dropdown.setCurrentIndex(active_index)
        dropdown.currentIndexChanged.connect(self._on_provider_index_changed)
        layout.addWidget(dropdown)
        self._provider_dropdown = dropdown
        return wrap

    def _build_confirm_buttons(self) -> QWidget:
        footer = QWidget()
        footer.setStyleSheet("background-color: transparent;")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        cancel = self._build_footer_button(
            "Cancel",
            IconType.CANCEL,
            BrandColors.SIDEBAR_BG,
            BrandColors.ITEM_HOVER,
        )
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel, 1)

        confirm = self._build_footer_button(
            "Confirm",
            IconType.CONFIRM,
            BrandColors.ACCENT,
            "#4a80e0",
        )
        confirm.clicked.connect(self._confirm)
        layout.addWidget(confirm, 1)
        return footer

    def _build_footer_button(
        self,
        text: str,
        icon_type: IconType,
        background: str,
        hover: str,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {background};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 14px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            """
        )
        IconUtils.apply_icon(button, icon_type, BrandColors.TEXT_PRIMARY, size=14)
        button.setIconSize(QSize(14, 14))
        return button

    def _refresh_description(self) -> None:
        if self._desc_label is None:
            return

        if self._deferred_apply:
            self._desc_label.setText(f"Showing loadouts for <b>{self._provider_display_name()}</b>.")
            return

        self._desc_label.setText(
            f"Showing loadouts for <b>{self._provider_display_name()}</b>. "
            "Pick the one you want to use next:"
        )

    def _clear_initial_focus(self) -> None:
        self.setFocus(Qt.OtherFocusReason)

    def _clear_loadout_buttons(self) -> None:
        if self._list_layout is None:
            return

        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_loadout_buttons(self) -> None:
        if self._list_layout is None:
            return

        self._clear_loadout_buttons()
        loadouts = self._provider_loadouts.get(self._active_provider) if self._active_provider else []
        if loadouts:
            for loadout in loadouts:
                self._list_layout.addWidget(self._build_loadout_button(loadout))
        else:
            self._list_layout.addWidget(
                HintCard(
                    "No loadouts found",
                    f"No valid loadouts are available for {self._provider_display_name()}.",
                    variant="warn",
                )
            )

        self._list_layout.addStretch(1)

    def _build_loadout_button(self, loadout: LoadoutDefinition) -> QWidget:
        selected_name = (
            self._draft_names_by_provider.get(loadout.provider)
            if self._deferred_apply
            else self._current_loadout_name
        )
        original_name = self._current_names_by_provider.get(loadout.provider)
        is_current = loadout.name == selected_name
        if is_current and loadout.name == original_name:
            subtitle = "Currently active"
        elif is_current:
            subtitle = "Selected"
        else:
            subtitle = "Click to select" if self._deferred_apply else "Click to switch on the next restart"

        button = _LoadoutOptionCard(
            provider_name=self._provider_name,
            loadout_name=loadout.name,
            subtitle=subtitle,
            selected=is_current,
            show_checkmark=self._deferred_apply and is_current,
        )
        button.clicked.connect(self._pick)
        return button

    def _pick(self, loadout_name: str) -> None:
        self._selected_loadout_name = str(loadout_name or "").strip() or None
        if not self._selected_loadout_name:
            return
        if self._deferred_apply and self._active_provider is not None:
            self._draft_names_by_provider[self._active_provider] = self._selected_loadout_name
            self._rebuild_loadout_buttons()
            return
        self.accept()

    def _on_provider_index_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._provider_order):
            return
        self._active_provider = self._provider_order[index]
        self._provider_name = self._provider_display_name(self._active_provider)
        self._refresh_description()
        self._rebuild_loadout_buttons()

    def _confirm(self) -> None:
        self._selected_loadout_name = (
            self._draft_names_by_provider.get(self._active_provider)
            if self._active_provider is not None
            else None
        )
        self.accept()

    @property
    def selected_loadout_name(self) -> Optional[str]:
        return self._selected_loadout_name

    @property
    def selected_loadout_names_by_provider(self) -> dict[DriverProvider, str]:
        return {
            provider: name
            for provider, name in self._draft_names_by_provider.items()
            if isinstance(provider, DriverProvider) and str(name or "").strip()
        }
