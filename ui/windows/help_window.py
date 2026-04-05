from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel,
    QMessageBox, QFileDialog, QFrame
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices

from ui.core.brand import BrandColors
from ui.core.icons import IconUtils, IconType
from ui.niche.backup_import_window import BackupImportWindow
from ui.niche.browser_manager_window import BrowserManagerWindow
from ui.niche.diagnostics_bundle_window import DiagnosticsBundleWindow
from ui.windows.contributors_window import ContributorsWindow
from ui.niche.stmp_patcher_window import STMPPatcherWindow
from utils.v1_migrator import V1Migrator
from utils.logger import Logger


DISCORD_INVITE_URL = "https://discord.gg/4Gvjk2RdsK"
REPOSITORY_URL = "https://github.com/LyubomirT/intense-rp-next"
DOCS_HOME_URL = "https://intense-rp-next.readthedocs.io/en/latest/"
DONATE_URL = f"{DOCS_HOME_URL}hands/support/#financial-support-optional"


class HelpTile(QFrame):
    clicked = Signal()

    def __init__(self, label: str, icon_type: IconType | str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

        self.setStyleSheet(f"""
            HelpTile {{
                background-color: {BrandColors.SIDEBAR_BG};
                border-radius: 8px;
                border: 1px solid transparent;
            }}
            HelpTile:hover {{
                background-color: {BrandColors.ITEM_HOVER};
                border: 1px solid {BrandColors.ACCENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(10, 16, 10, 12)
        layout.setSpacing(8)

        # Icon (large, centered)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background-color: transparent;")
        pixmap = IconUtils.get_pixmap(
            icon_type,
            color=BrandColors.TEXT_PRIMARY,
            size=36,
            dpr=self.devicePixelRatioF(),
        )
        icon_label.setPixmap(pixmap)
        layout.addWidget(icon_label)

        # Text label (centered, below icon)
        text_label = QLabel(label)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_SMALL};
            font-weight: 600;
            color: {BrandColors.TEXT_PRIMARY};
            background-color: transparent;
        """)
        layout.addWidget(text_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class HelpWindow(QMainWindow):
    settings_reloaded = Signal()

    def __init__(self, config_manager, parent=None, main_window=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.main_window = main_window
        self.setWindowTitle("Help & Extras")
        self.resize(440, 520)
        self.setStyleSheet(f"background-color: {BrandColors.WINDOW_BG};")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(16)
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

        desc = QLabel("Migration tools, utilities, community, and project resources.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"""
            font-size: {BrandColors.FONT_SIZE_REGULAR};
            color: {BrandColors.TEXT_SECONDARY};
            background-color: transparent;
            padding: 4px 4px;
        """)
        layout.addWidget(desc)

        # Tile grid
        grid = QGridLayout()
        grid.setSpacing(10)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        layout.addLayout(grid)

        tiles = [
            ("Backup / Import", IconType.BACKUP, "Backup or restore your config directory (settings/key/profiles) using a .zip file.", self.show_backup_import),
            ("Browser Manager", IconType.BROWSER_MANAGER, "Install, reinstall, or remove the Playwright Chromium browser used by IntenseRP.", self.show_browser_manager),
            ("STMP Patcher", IconType.PATCHER, "Patches RossAscends's STMP to include per-message names.", self.show_stmp_patcher),
            ("Migrate from v1", IconType.MIGRATE, "", self.start_migration),
            ("Contributors", IconType.CONTRIBUTORS, "", self.show_contributors),
            ("Bug Report", IconType.BUG_REPORT, "Create a diagnostics .zip bundle from the private internal log and latest saved prompts.", self.show_bug_report_bundle),
            ("Discord Server", IconType.DISCORD, "Join the IntenseRP Next Discord server for community help and quick questions.", self.open_discord),
            ("GitHub", IconType.GITHUB, "Open the IntenseRP Next GitHub repository.", self.open_github),
            ("Donate", IconType.DONATE, "Support the project financially.", self.open_donate),
            ("Docs", IconType.DOCS, "Open the IntenseRP Next documentation.", self.open_docs),
        ]

        for i, (label, icon_type, tooltip, handler) in enumerate(tiles):
            tile = HelpTile(label, icon_type, tooltip=tooltip, parent=self)
            tile.clicked.connect(handler)
            row, col = divmod(i, 3)
            if len(tiles) % 3 == 1 and i == len(tiles) - 1:
                col = 1
            grid.addWidget(tile, row, col)

        layout.addStretch()

        self.contributors_window = None
        self.stmp_patcher_window = None
        self.backup_import_window = None
        self.browser_manager_window = None
        self.diagnostics_bundle_window = None

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

    def show_stmp_patcher(self):
        if not self.stmp_patcher_window:
            self.stmp_patcher_window = STMPPatcherWindow(None)  # Top level
        self.stmp_patcher_window.show()
        self.stmp_patcher_window.activateWindow()

    def show_contributors(self):
        if not self.contributors_window:
            self.contributors_window = ContributorsWindow(None) # Top level
        self.contributors_window.show()
        self.contributors_window.activateWindow()

    def show_backup_import(self):
        if not self.backup_import_window:
            self.backup_import_window = BackupImportWindow(self.config_manager, None)  # Top level
            self.backup_import_window.settings_reloaded.connect(self.settings_reloaded.emit)
        self.backup_import_window.show()
        self.backup_import_window.activateWindow()

    def show_bug_report_bundle(self):
        if not self.diagnostics_bundle_window:
            self.diagnostics_bundle_window = DiagnosticsBundleWindow(self.config_manager, None)  # Top level
        self.diagnostics_bundle_window.show()
        self.diagnostics_bundle_window.activateWindow()

    def show_browser_manager(self):
        if not self.browser_manager_window:
            self.browser_manager_window = BrowserManagerWindow(main_window=self.main_window, parent=None)  # Top level
        self.browser_manager_window.show()
        self.browser_manager_window.activateWindow()

    def open_discord(self):
        QDesktopServices.openUrl(QUrl(DISCORD_INVITE_URL))

    def open_github(self):
        QDesktopServices.openUrl(QUrl(REPOSITORY_URL))

    def open_docs(self):
        QDesktopServices.openUrl(QUrl(DOCS_HOME_URL))

    def open_donate(self):
        QDesktopServices.openUrl(QUrl(DONATE_URL))
