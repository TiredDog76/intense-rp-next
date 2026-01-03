import json
import webbrowser
import threading
import requests
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QScrollArea, QLabel, 
    QFrame, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QBrush, QColor, QFont, QCursor

from ui.core.brand import BrandColors
from ui.core.icons import IconUtils, IconType
from utils.logger import Logger


def _resolve_resource_path(*parts: str) -> Path:
    """Resolve a resource path in both dev and PyInstaller-frozen runs."""
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / Path(*parts))
        candidates.append(Path(sys.executable).resolve().parent / Path(*parts))

    # Source checkout (repo root is the parent directory of the ui/ package)
    candidates.append(Path(__file__).resolve().parents[2] / Path(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[-1]

class ContributorCard(QFrame):
    def __init__(self, name, status, avatar_url, github_url, parent=None):
        super().__init__(parent)
        self.github_url = github_url
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(80)
        self.setStyleSheet(f"""
            ContributorCard {{
                background-color: {BrandColors.SIDEBAR_BG};
                border-radius: 10px;
                border: 1px solid transparent;
            }}
            ContributorCard:hover {{
                border: 1px solid {BrandColors.ACCENT};
                background-color: #252525;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)

        # Avatar Label
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(50, 50)
        self.avatar_label.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.avatar_label)

        # Text Layout
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignVCenter)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_LARGE};
            font-weight: bold;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
        """)
        text_layout.addWidget(name_label)

        status_label = QLabel(status)
        status_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_SMALL};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
        """)
        text_layout.addWidget(status_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        # Load Avatar
        if avatar_url:
            self._load_avatar(avatar_url)
        else:
            self._set_placeholder_avatar(name)

    def mousePressEvent(self, event):
        if self.github_url:
            webbrowser.open(self.github_url)

    def _set_placeholder_avatar(self, name):
        pixmap = QPixmap(50, 50)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Circle background
        path = QPainterPath()
        path.addEllipse(0, 0, 50, 50)
        painter.setClipPath(path)
        painter.fillPath(path, QBrush(QColor(BrandColors.ACCENT)))
        
        # Initials
        painter.setPen(QColor(BrandColors.TEXT_PRIMARY))
        font = QFont(BrandColors.FONT_FAMILY, 16, QFont.Bold)
        painter.setFont(font)
        initial = name[0].upper() if name else "?"
        painter.drawText(0, 0, 50, 50, Qt.AlignCenter, initial)
        painter.end()
        
        self.avatar_label.setPixmap(pixmap)

    def _load_avatar(self, url):
        def worker():
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.content
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    # we'll store bytes and process in `update_avatar`
                    return pixmap
            except Exception:
                pass
            return None

        thread = threading.Thread(target=self._thread_wrapper, args=(worker,), daemon=True)
        thread.start()

    def _thread_wrapper(self, worker_func):
        pixmap = worker_func()
        if pixmap:
            # Schedule update on main thread
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self, "update_avatar", Qt.QueuedConnection, Q_ARG(QPixmap, pixmap))

    @Slot(QPixmap)
    def update_avatar(self, pixmap):
        # Crop to circle
        size = 50
        rounded = QPixmap(size, size)
        rounded.fill(Qt.transparent)
        
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        
        scaled = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        # Center crop
        x = (scaled.width() - size) // 2
        y = (scaled.height() - size) // 2
        
        painter.drawPixmap(0, 0, scaled, x, y, size, size)
        painter.end()
        
        self.avatar_label.setPixmap(rounded)

class ContributorsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Contributors")
        self.resize(500, 600)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG};")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Title
        title = QLabel("Contributors")
        title.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {BrandColors.TEXT_PRIMARY};
        """)
        main_layout.addWidget(title)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: transparent; }}
            QWidget {{ background-color: transparent; }}
            QScrollBar:vertical {{
                border: none;
                background: {BrandColors.WINDOW_BG};
                width: 10px;
                margin: 0px; 
            }}
            QScrollBar::handle:vertical {{
                background: {BrandColors.SIDEBAR_BG};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        scroll_layout.setContentsMargins(0, 0, 10, 0) # Right margin for scrollbar
        
        self._load_contributors(scroll_layout)
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Close Button
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid #333;
                padding: 10px;
                border-radius: 6px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.TEXT_SECONDARY};
            }}
        """)
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(close_btn)

    def _load_contributors(self, layout):
        json_path = _resolve_resource_path("ui", "assets", "contributors", "contributors.json")
        try:
            if not json_path.exists():
                Logger.warning(f"Contributors file not found at {json_path}")
                return

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            for contributor in data.get("contributors", []):
                card = ContributorCard(
                    name=contributor.get("name", "Unknown"),
                    status=contributor.get("status", ""),
                    avatar_url=contributor.get("avatar_url", ""),
                    github_url=contributor.get("github_url", "")
                )
                layout.addWidget(card)
                
        except Exception as e:
            Logger.error(f"Error loading contributors: {e}")
            lbl = QLabel(f"Error loading contributors: {e}")
            lbl.setStyleSheet("color: red;")
            layout.addWidget(lbl)
