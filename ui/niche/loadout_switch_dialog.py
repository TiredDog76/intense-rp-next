from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from config.loadouts import LoadoutDefinition
from ui.core.brand import BrandColors
from ui.core.icons import IconType, IconUtils
from ui.niche.hotswap_dialog import PROVIDER_ICON_MAP
from ui.widgets.components import HintCard
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
        parent=None,
    ):
        super().__init__(parent)
        self._loadout_name = str(loadout_name or "").strip()
        self._selected = bool(selected)

        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("loadoutOptionCard")
        self.setMinimumHeight(78)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("background-color: transparent;")
        self._icon_label.setFixedSize(30, 30)
        self._icon_label.setAlignment(Qt.AlignCenter)
        icon_file = PROVIDER_ICON_MAP.get(str(provider_name or "").strip())
        if icon_file:
            pixmap = IconUtils.get_pixmap(
                icon_file,
                color=BrandColors.TEXT_PRIMARY,
                size=24,
                dpr=self.devicePixelRatioF(),
            )
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
        layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)

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
            background = BrandColors.ACCENT
            border = BrandColors.ACCENT
            hover = BrandColors.ACCENT
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
    ):
        super().__init__(parent)
        self._selected_loadout_name: Optional[str] = None
        self._provider_name = str(provider_name or "").strip()
        self._loadouts = list(loadouts or [])
        self._current_loadout_name = str(current_loadout_name or "").strip() or None

        self.setWindowTitle("Switch Loadout")
        self.setModal(True)
        self.setFixedWidth(420)
        self.setMinimumHeight(420)

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

        desc = QLabel(
            f"Showing loadouts for <b>{self._provider_name}</b>. "
            "Pick the one you want to use next:"
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setTextFormat(Qt.RichText)
        desc.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 2px 4px;
            """
        )
        layout.addWidget(desc)

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
        list_layout = QVBoxLayout(list_root)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        if self._loadouts:
            for loadout in self._loadouts:
                list_layout.addWidget(self._build_loadout_button(loadout))
        else:
            list_layout.addWidget(
                HintCard(
                    "No loadouts found",
                    f"No valid loadouts are available for {self._provider_name}.",
                    variant="warn",
                )
            )

        list_layout.addStretch(1)
        scroll.setWidget(list_root)
        layout.addWidget(scroll, 1)

        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 14px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            """
        )
        IconUtils.apply_icon(cancel, IconType.CANCEL, BrandColors.TEXT_PRIMARY, size=14)
        cancel.setIconSize(QSize(14, 14))
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _build_loadout_button(self, loadout: LoadoutDefinition) -> QWidget:
        is_current = loadout.name == self._current_loadout_name
        subtitle = "Currently active" if is_current else "Click to switch on the next restart"

        button = _LoadoutOptionCard(
            provider_name=self._provider_name,
            loadout_name=loadout.name,
            subtitle=subtitle,
            selected=is_current,
        )
        button.clicked.connect(self._pick)
        return button

    def _pick(self, loadout_name: str) -> None:
        self._selected_loadout_name = str(loadout_name or "").strip() or None
        if not self._selected_loadout_name:
            return
        self.accept()

    @property
    def selected_loadout_name(self) -> Optional[str]:
        return self._selected_loadout_name
