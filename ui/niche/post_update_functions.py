from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.core.brand import BrandColors
from ui.core.icons import IconType, IconUtils
from utils.logger import Logger


POST_UPDATE_FUNCTION_NONE = "none"
PLAYWRIGHT_PATCHRIGHT_BROWSER_UPDATE_283 = "playwright_patchright_browser_update_283"


@dataclass(frozen=True)
class PostUpdateFunctionContext:
    """Shared runtime context passed to version.json post-update functions."""

    parent: QWidget | None = None
    version: str = "unknown"
    open_browser_manager: Callable[[], None] | None = None


PostUpdateFunction = Callable[[PostUpdateFunctionContext], None]


def normalize_post_update_function_ref(value: object) -> str:
    """Normalize a pufref value into the registry key format."""

    normalized = str(value or "").strip().lower()
    return normalized or POST_UPDATE_FUNCTION_NONE


def run_post_update_function(ref: object, context: PostUpdateFunctionContext) -> bool:
    """
    Run a registered post-update function.

    Returns True when a matching function ran successfully, and False for none,
    unknown keys, or handled failures.
    """

    key = normalize_post_update_function_ref(ref)
    if key == POST_UPDATE_FUNCTION_NONE:
        return False

    action = POST_UPDATE_FUNCTIONS.get(key)
    if action is None:
        Logger.warning(f"Unknown post-update function reference: {key}")
        return False

    try:
        action(context)
    except Exception as exc:
        Logger.error(f"Post-update function '{key}' failed: {exc}")
        return False
    return True


def registered_post_update_function_refs() -> tuple[str, ...]:
    """Return all pufref keys supported by this build."""

    return tuple(sorted(POST_UPDATE_FUNCTIONS.keys()))


class BrowserUpdateRecommendationDialog(QDialog):
    """Warn users when a release needs a fresh Playwright/Patchright browser."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setWindowTitle("Browser Update Recommended")
        self.setModal(True)
        self.setFixedWidth(500)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("browserUpdateRecommendationCard")
        card.setStyleSheet(
            f"""
            QFrame#browserUpdateRecommendationCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(14)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_message())
        layout.addWidget(self._build_button_row())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setStyleSheet("background-color: transparent;")
        pixmap = IconUtils.get_pixmap(
            "alert-triangle.svg",
            color=BrandColors.WARNING,
            size=28,
            dpr=self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap)
        layout.addWidget(icon_label, 0, Qt.AlignTop)

        title = QLabel("Browser Update Recommended")
        title.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_TITLE};
            font-weight: 800;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        layout.addWidget(title, 1)

        return header

    def _build_message(self) -> QLabel:
        message = QLabel(
            "IntenseRP Next 2.8.3 updated the Playwright/Patchright version. "
            "Reinstalling the browser is recommended so you get the best experience "
            "and anti-bot measures.\n\n"
            "You can also do this manually from Tools -> Browser Manager -> Reinstall."
        )
        message.setWordWrap(True)
        message.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 0px 2px;
            """
        )
        return message

    def _build_button_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        later_btn = self._build_button(
            "Later",
            IconType.CANCEL,
            accent=False,
        )
        later_btn.clicked.connect(self.reject)
        layout.addWidget(later_btn, 1)

        take_me_there_btn = self._build_button(
            "Take Me There",
            "external-link.svg",
            accent=True,
        )
        take_me_there_btn.setDefault(True)
        take_me_there_btn.clicked.connect(self.accept)
        layout.addWidget(take_me_there_btn, 1)

        return row

    def _build_button(self, text: str, icon: IconType | str, *, accent: bool) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(_button_style(accent=accent))
        IconUtils.apply_icon(button, icon, BrandColors.TEXT_PRIMARY, size=16)
        button.setIconSize(QSize(16, 16))
        return button


def _button_style(*, accent: bool) -> str:
    if accent:
        return f"""
            QPushButton {{
                background-color: {BrandColors.ACCENT};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 10px 14px;
                border-radius: 8px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 800;
            }}
            QPushButton:hover {{
                background-color: #4a80e0;
            }}
            QPushButton:pressed {{
                background-color: #3c6ac3;
            }}
        """

    return f"""
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


def show_playwright_patchright_browser_update_warning(context: PostUpdateFunctionContext) -> None:
    """Show the 2.8.3 browser reinstall recommendation and open Browser Manager on request."""

    dialog = BrowserUpdateRecommendationDialog(parent=context.parent)
    if dialog.exec() != QDialog.Accepted:
        return

    opener = context.open_browser_manager
    if callable(opener):
        opener()
        return

    Logger.warning("Post-update browser warning could not open Browser Manager.")


POST_UPDATE_FUNCTIONS: dict[str, PostUpdateFunction] = {
    PLAYWRIGHT_PATCHRIGHT_BROWSER_UPDATE_283: show_playwright_patchright_browser_update_warning,
}
