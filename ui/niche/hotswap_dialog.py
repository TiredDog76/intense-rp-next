from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QVBoxLayout

from ui.core.brand import BrandColors
from ui.core.icons import IconType, IconUtils


PROVIDER_ICON_MAP: dict[str, str] = {
    "DeepSeek": "providers/deepseek.svg",
    "GLM Chat": "providers/zai.svg",
    "Moonshot": "providers/moonshot.svg",
    "QwenLM": "providers/qwen.svg",
}

ALL_PROVIDERS: list[str] = ["DeepSeek", "GLM Chat", "Moonshot", "QwenLM"]


class HotswapDialog(QDialog):
    """Small modal that lets the user pick one of the other providers."""

    def __init__(self, current_provider: str, parent=None):
        super().__init__(parent)
        self._selected: Optional[str] = None

        self.setWindowTitle("Hotswap Provider")
        self.setModal(True)
        self.setFixedWidth(340)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("hotswapCard")
        card.setStyleSheet(
            f"""
            QFrame#hotswapCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Switch Provider")
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

        desc = QLabel(f"Currently using <b>{current_provider}</b>. Pick a provider to switch to:")
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

        # Provider buttons (the ones you haven't picked)
        others = [p for p in ALL_PROVIDERS if p != current_provider]
        for provider_name in others:
            btn = QPushButton(f"  {provider_name}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {BrandColors.ACCENT};
                    color: {BrandColors.TEXT_PRIMARY};
                    border: none;
                    padding: 10px 14px;
                    border-radius: 8px;
                    font-size: {BrandColors.FONT_SIZE_REGULAR};
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background-color: #4a80e0;
                }}
                QPushButton:pressed {{
                    background-color: #3c6ac3;
                }}
                """
            )
            icon_file = PROVIDER_ICON_MAP.get(provider_name)
            if icon_file:
                icon = IconUtils.get_icon(
                    icon_file, color=BrandColors.TEXT_PRIMARY, size=16, widget=btn,
                )
                if not icon.isNull():
                    btn.setIcon(icon)
                    btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(lambda checked=False, name=provider_name: self._pick(name))
            layout.addWidget(btn)

        # Cancel button
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 14px;
                border-radius: 8px;
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

    def _pick(self, provider_name: str) -> None:
        self._selected = provider_name
        self.accept()

    @property
    def selected_provider(self) -> Optional[str]:
        return self._selected
