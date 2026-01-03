from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.core.brand import BrandColors


class UpdateGitInstructionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Update via Git")
        self.setModal(True)
        self.setFixedWidth(500)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("gitUpdateCard")
        card.setStyleSheet(
            f"""
            QFrame#gitUpdateCard {{
                background-color: {BrandColors.WINDOW_BG};
                border: none;
            }}
            """
        )
        root_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Update using the terminal")
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
            "Close the app, then run the commands below from a terminal to update your source checkout."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(
            f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 2px 2px;
            """
        )
        layout.addWidget(desc)

        commands = self._default_commands()
        self._commands = commands
        layout.addWidget(self._build_command_box(commands))

        layout.addWidget(self._build_button_row())

    def _default_commands(self) -> str:
        repo_root = Path(__file__).resolve().parent.parent.parent
        repo_root_str = str(repo_root)
        # Keep it simple and cross-shell. Users can adapt for venvs as needed.
        return "\n".join(
            [
                f'cd "{repo_root_str}"',
                "git pull",
                "pip install -r requirements.txt",
                "python main.py",
            ]
        )

    def _build_command_box(self, text: str) -> QFrame:
        box = QFrame()
        box.setStyleSheet(
            f"""
            QFrame {{
                background-color: {BrandColors.SIDEBAR_BG};
                border-radius: 10px;
            }}
            """
        )

        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            f"""
            font-family: Consolas, 'Courier New', monospace;
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
            """
        )
        layout.addWidget(label)
        return box

    def _build_button_row(self) -> QFrame:
        row = QFrame()
        row.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        self._copy_btn = QPushButton("Copy Commands")
        copy_btn = self._copy_btn
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: 1px solid {BrandColors.INPUT_BORDER};
                padding: 10px 14px;
                border-radius: 8px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.ACCENT};
            }}
            """
        )
        copy_btn.setIcon(QIcon(self._icon_path("copy.svg")))
        copy_btn.setIconSize(QSize(16, 16))
        copy_btn.clicked.connect(self._on_copy_clicked)
        layout.addWidget(copy_btn, 1)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f"""
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
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 1)
        return row

    def _copy_to_clipboard(self, text: str) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)

    def _on_copy_clicked(self) -> None:
        from PySide6.QtCore import QTimer

        self._copy_to_clipboard(self._commands)
        btn = getattr(self, "_copy_btn", None)
        if btn is None:
            return

        original = btn.text()
        btn.setText("Copied")
        btn.setEnabled(False)

        def restore():
            btn.setText(original)
            btn.setEnabled(True)

        QTimer.singleShot(650, restore)

    def _icon_path(self, filename: str) -> str:
        import os

        return os.path.join(os.path.dirname(__file__), "..", "assets", "icons", filename)
