"""
Request queue preview widget for displaying pending/processing requests.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ui.core.brand import BrandColors
from ui.core.icons import IconUtils


class RequestQueueItemCard(QFrame):
    STATUS_STYLES = {
        "pending": {
            "header_bg": BrandColors.ITEM_HOVER,
            "body_bg": "#1f1f1f",
            "border": BrandColors.INPUT_BORDER,
            "icon": "play.svg",
            "icon_color": BrandColors.TUMBLER_HANDLE,
        },
        "processing": {
            "header_bg": BrandColors.CATEGORY_ACTIVE_BG,
            "body_bg": "#132b55",
            "border": BrandColors.ACCENT,
            "icon": "clock.svg",
            "icon_color": BrandColors.ACCENT,
        },
        "cancelled": {
            "header_bg": "#5a2a2a",
            "body_bg": "#3a1a1a",
            "border": BrandColors.DANGER,
            "icon": "x.svg",
            "icon_color": BrandColors.DANGER,
        },
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("requestQueueCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._current_status: Optional[str] = None
        self._current_icon_key: Optional[tuple[str, Optional[str], int, float]] = None

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(18, 18)
        self._icon_label.setStyleSheet("background-color: transparent;")

        self._pos_label = QLabel()
        self._pos_label.setStyleSheet(
            f"color: {BrandColors.TEXT_PRIMARY}; font-weight: 700; font-size: {BrandColors.FONT_SIZE_REGULAR};"
        )

        self._id_label = QLabel()
        self._id_label.setStyleSheet(
            f"color: {BrandColors.TEXT_PRIMARY}; font-weight: 600; font-size: {BrandColors.FONT_SIZE_REGULAR};"
        )
        self._id_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._time_label = QLabel()
        self._time_label.setStyleSheet(
            f"color: {BrandColors.TEXT_SECONDARY}; font-size: {BrandColors.FONT_SIZE_SMALL};"
        )

        header = QFrame()
        header.setObjectName("requestQueueCardHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(8)
        header_layout.addWidget(self._icon_label, 0, Qt.AlignVCenter)
        header_layout.addWidget(self._pos_label, 0, Qt.AlignVCenter)
        header_layout.addWidget(self._id_label, 0, Qt.AlignVCenter)
        header_layout.addStretch(1)
        header_layout.addWidget(self._time_label, 0, Qt.AlignVCenter)

        self._meta_label = QLabel()
        self._meta_label.setWordWrap(True)
        self._meta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._meta_label.setStyleSheet(
            f"color: {BrandColors.TEXT_SECONDARY}; font-size: {BrandColors.FONT_SIZE_SMALL};"
        )

        meta = QFrame()
        meta.setObjectName("requestQueueCardMeta")
        meta_layout = QVBoxLayout(meta)
        meta_layout.setContentsMargins(10, 8, 10, 8)
        meta_layout.setSpacing(0)
        meta_layout.addWidget(self._meta_label)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(header)
        main_layout.addWidget(meta)

    def update_from_data(self, data: dict[str, Any]) -> None:
        status = (data.get("status") or "pending").lower()
        style = self.STATUS_STYLES.get(status, self.STATUS_STYLES["pending"])

        position = int(data.get("position") or 0)
        request_id = str(data.get("id") or "")
        queued_at = float(data.get("queued_at") or 0.0)

        try:
            time_str = datetime.fromtimestamp(queued_at).strftime("%H:%M:%S")
        except Exception:
            time_str = "Unknown"

        self._pos_label.setText(f"#{position}")
        self._id_label.setText(request_id)
        self._time_label.setText(f"Added: {time_str}")

        msg_count = int(data.get("message_count") or 0)
        request_type = str(data.get("request_type") or "chat").strip().lower()
        prompt_length = int(data.get("prompt_length") or 0)
        api_key_name = data.get("api_key_name")
        model = str(data.get("model") or "")
        provider = str(data.get("provider") or "")
        stream = bool(data.get("stream"))

        api_key_text = str(api_key_name) if api_key_name else "None"
        if request_type == "text":
            request_label = "Text Completion"
            size_line = f"Prompt Length: {prompt_length} chars"
        else:
            request_label = "Chat Completion"
            size_line = f"Messages: {msg_count}"

        self._meta_label.setText(
            "Provider: {provider}\nType: {request_type}\n{size_line}\nAPI Key: {api_key}\nModel: {model}\nStreaming: {streaming}".format(
                provider=provider or "Unknown",
                request_type=request_label,
                size_line=size_line,
                api_key=api_key_text,
                model=model or "Unknown",
                streaming="Yes" if stream else "No",
            )
        )

        icon_file = style["icon"]
        icon_color = style.get("icon_color") or BrandColors.TEXT_PRIMARY
        dpr = self.devicePixelRatioF()
        icon_key = (icon_file, icon_color, 18, round(dpr, 2))

        if status != self._current_status:
            self._current_status = status
            self._current_icon_key = None

            border_color = style["border"]
            header_bg = style["header_bg"]
            body_bg = style["body_bg"]

            self.setStyleSheet(
                f"""
                QFrame#requestQueueCard {{
                    background-color: transparent;
                    border: 1px solid {border_color};
                    border-radius: 8px;
                }}
                QFrame#requestQueueCardHeader {{
                    background-color: {header_bg};
                    border-top-left-radius: 7px;
                    border-top-right-radius: 7px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                }}
                QFrame#requestQueueCardMeta {{
                    background-color: {body_bg};
                    border-top-left-radius: 0px;
                    border-top-right-radius: 0px;
                    border-bottom-left-radius: 7px;
                    border-bottom-right-radius: 7px;
                }}
                """
            )

        if icon_key != self._current_icon_key:
            pixmap = IconUtils.get_pixmap(icon_file, color=icon_color, size=18, dpr=dpr)
            if not pixmap.isNull():
                self._icon_label.setPixmap(pixmap)
            self._current_icon_key = icon_key


class RequestQueuePreview(QWidget):
    stop_requested = Signal()
    clear_after_current_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item_widgets: dict[str, RequestQueueItemCard] = {}
        self._last_order: list[str] = []
        self._last_payload_by_id: dict[str, dict[str, Any]] = {}
        self._stop_button: QPushButton | None = None
        self._trash_button: QPushButton | None = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("requestQueueContainer")
        container.setStyleSheet(
            f"""
            QFrame#requestQueueContainer {{
                background-color: #1a1a1a;
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 8px;
            }}
            """
        )

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        header_label = QLabel("Request Queue")
        header_label.setStyleSheet(
            f"""
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
            """
        )
        container_layout.addWidget(header_label)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: #1a1a1a;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #444444;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #555555;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            """
        )

        self._stack_root = QWidget()
        self._stack_root.setStyleSheet("background-color: transparent;")
        self._stack = QStackedLayout(self._stack_root)

        self._list_root = QWidget()
        self._list_root.setStyleSheet("background-color: transparent;")
        self._list_layout = QVBoxLayout(self._list_root)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(8)
        self._list_layout.setAlignment(Qt.AlignTop)

        empty_root = QWidget()
        empty_root.setStyleSheet("background-color: transparent;")
        empty_layout = QVBoxLayout(empty_root)
        empty_layout.setContentsMargins(12, 18, 12, 18)
        empty_layout.addStretch(1)

        empty_label = QLabel("No queued requests")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setStyleSheet(
            f"color: {BrandColors.TEXT_SECONDARY}; font-size: {BrandColors.FONT_SIZE_REGULAR};"
        )
        empty_layout.addWidget(empty_label)
        empty_layout.addStretch(1)

        self._stack.addWidget(self._list_root)
        self._stack.addWidget(empty_root)
        self._stack.setCurrentWidget(empty_root)

        self._scroll_area.setWidget(self._stack_root)
        container_layout.addWidget(self._scroll_area)

        container_layout.addWidget(self._build_queue_ui_controls())

        main_layout.addWidget(container)

    def _build_queue_ui_controls(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("requestQueueControlsBar")
        bar.setStyleSheet(
            f"""
            QFrame#requestQueueControlsBar {{
                background-color: #222222;
                border-top: 1px solid {BrandColors.INPUT_BORDER};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 7px;
                border-bottom-right-radius: 7px;
            }}
            """
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        layout.addStretch(1)

        self._stop_button = QPushButton()
        self._stop_button.setCursor(Qt.PointingHandCursor)
        self._stop_button.setFixedSize(32, 32)
        self._stop_button.setIconSize(QSize(16, 16))
        self._stop_button.setToolTip("Abort the current processing request(s) and disconnect the client")
        self._stop_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {BrandColors.INPUT_BORDER};
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.ACCENT};
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.ITEM_SELECTED};
            }}
            QPushButton:disabled {{
                background-color: transparent;
                border: 1px solid {BrandColors.INPUT_BORDER};
                opacity: 0.4;
            }}
            """
        )
        stop_icon = IconUtils.get_icon(
            "square.svg",
            color=BrandColors.TEXT_SECONDARY,
            size=16,
            widget=self._stop_button,
        )
        if not stop_icon.isNull():
            self._stop_button.setIcon(stop_icon)
        self._stop_button.clicked.connect(self.stop_requested.emit)
        layout.addWidget(self._stop_button, 0, Qt.AlignVCenter)

        self._trash_button = QPushButton()
        self._trash_button.setCursor(Qt.PointingHandCursor)
        self._trash_button.setFixedSize(32, 32)
        self._trash_button.setIconSize(QSize(16, 16))
        self._trash_button.setToolTip("Cancel all queued requests after the current one")
        self._trash_button.setStyleSheet(
            f"""
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
            QPushButton:pressed {{
                background-color: {BrandColors.ITEM_SELECTED};
            }}
            QPushButton:disabled {{
                background-color: transparent;
                border: 1px solid {BrandColors.INPUT_BORDER};
                opacity: 0.4;
            }}
            """
        )
        trash_icon = IconUtils.get_icon(
            "trash-2.svg",
            color=BrandColors.DANGER,
            size=16,
            widget=self._trash_button,
        )
        if not trash_icon.isNull():
            self._trash_button.setIcon(trash_icon)
        self._trash_button.clicked.connect(self.clear_after_current_requested.emit)
        layout.addWidget(self._trash_button, 0, Qt.AlignVCenter)

        self._stop_button.setEnabled(False)
        self._trash_button.setEnabled(False)

        return bar

    def _set_controls_state(self, requests: list[dict[str, Any]]) -> None:
        stop_button = getattr(self, "_stop_button", None)
        trash_button = getattr(self, "_trash_button", None)
        if stop_button is None and trash_button is None:
            return

        statuses = {str(r.get("status") or "").lower() for r in (requests or [])}
        has_processing = "processing" in statuses
        has_pending = "pending" in statuses

        if stop_button is not None:
            stop_button.setEnabled(bool(has_processing))
        if trash_button is not None:
            trash_button.setEnabled(bool(has_pending))

    def set_requests(self, requests: list[dict[str, Any]]) -> None:
        requests = list(requests or [])
        self._set_controls_state(requests)
        if not requests:
            if not self._last_order:
                self._stack.setCurrentIndex(1)
                return

            self._stack.setCurrentIndex(1)
            for request_id in list(self._item_widgets.keys()):
                widget = self._item_widgets.pop(request_id)
                widget.setParent(None)
                widget.deleteLater()
            self._last_order = []
            self._last_payload_by_id = {}
            return

        self._stack.setCurrentIndex(0)
        active_ids = {str(r.get("id")) for r in requests if r.get("id") is not None}
        new_order = [str(r.get("id")) for r in requests if r.get("id") is not None]

        for request_id in list(self._item_widgets.keys()):
            if request_id in active_ids:
                continue
            widget = self._item_widgets.pop(request_id)
            self._last_payload_by_id.pop(request_id, None)
            self._list_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()

        for req in requests:
            val = req.get("id")
            if val is None:
                continue
            request_id = str(val)
            widget = self._item_widgets.get(request_id)
            if widget is None:
                widget = RequestQueueItemCard()
                self._item_widgets[request_id] = widget

            prev_payload = self._last_payload_by_id.get(request_id)
            if prev_payload != req:
                widget.update_from_data(req)
                self._last_payload_by_id[request_id] = dict(req)

        if new_order != self._last_order:
            for request_id in self._last_order:
                widget = self._item_widgets.get(request_id)
                if widget is not None:
                    self._list_layout.removeWidget(widget)

            for request_id in new_order:
                widget = self._item_widgets.get(request_id)
                if widget is not None:
                    self._list_layout.addWidget(widget)

            self._last_order = new_order
