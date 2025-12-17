from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, 
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from ui.brand import BrandColors
from ui.icons import IconUtils, IconType
from ui.contributors_window import ContributorsWindow
from utils.v1_migrator import V1Migrator
from utils.logger import Logger

class HelpWindow(QMainWindow):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Help & Extras")
        self.resize(350, 300)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG};")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Help & Extras")
        title.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {BrandColors.TEXT_PRIMARY};
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        desc = QLabel("Access migration tools for older versions or view project resources.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 4px 4px;
        """)
        layout.addWidget(desc)
        
        layout.addStretch()

        # Migrate Button
        self.migrate_btn = self._create_button("Migrate from v1", IconType.MIGRATE)
        self.migrate_btn.clicked.connect(self.start_migration)
        layout.addWidget(self.migrate_btn)

        # Contributors Button
        self.contrib_btn = self._create_button("Contributors", IconType.CONTRIBUTORS)
        self.contrib_btn.clicked.connect(self.show_contributors)
        layout.addWidget(self.contrib_btn)
        
        layout.addStretch()



        self.contributors_window = None

    def _create_button(self, text, icon_type):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(60)
        
        # Apply icon using util
        IconUtils.apply_icon(btn, icon_type, BrandColors.TEXT_PRIMARY)
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BrandColors.SIDEBAR_BG};
                color: {BrandColors.TEXT_PRIMARY};
                border: none;
                padding: 15px 20px;
                border-radius: 8px;
                font-size: {BrandColors.FONT_SIZE_REGULAR};
                text-align: left;
                padding-left: 20px;
            }}
            QPushButton:hover {{
                background-color: {BrandColors.ITEM_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {BrandColors.ACCENT};
            }}
        """)
        return btn

    def start_migration(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Migrate from v1")
        msg.setText("This tool will migrate settings from an old IntenseRP (v1.5.3+) installation.\n\n"
                    "Please select the root directory of your old installation.\n"
                    "This directory must contain the 'save' folder with 'config.enc' and 'secret.key'.")
        msg.setIcon(QMessageBox.Information)
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        
        if msg.exec() != QMessageBox.Ok:
            return

        directory = QFileDialog.getExistingDirectory(self, "Select v1 Installation Directory")
        if not directory:
            return

        migrator = V1Migrator(self.config_manager)
        success, message = migrator.migrate(directory)

        result_msg = QMessageBox(self)
        result_msg.setWindowTitle("Migration Result")
        result_msg.setText(message)
        result_msg.setIcon(QMessageBox.Information if success else QMessageBox.Warning)
        result_msg.exec()

    def show_contributors(self):
        if not self.contributors_window:
            self.contributors_window = ContributorsWindow(None) # Top level
        self.contributors_window.show()
        self.contributors_window.activateWindow()
