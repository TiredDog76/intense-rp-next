from enum import Enum
import os
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QAbstractButton
from utils.logger import Logger

class IconType(Enum):
    START = "play.svg"
    STOP = "square.svg"
    CONFIRM = "check.svg"
    CANCEL = "x.svg"
    SETTINGS = "settings.svg"
    SEARCH = "search.svg"
    PLUS = "plus.svg"
    HELP = "help-circle.svg"
    SUPPORT = "support.svg"
    MIGRATE = "truck.svg"
    CONTRIBUTORS = "user-check.svg"
    PATCHER = "terminal.svg"
    BACKUP = "download-cloud.svg"

class IconUtils:
    @staticmethod
    def apply_icon(button: QAbstractButton, icon_type: IconType, color: str = None, size: int = 20, y_offset: int = 0):
        """
        Applies an SVG icon to a button.
        
        Note: Colors and offsets are now baked into the SVG files for optimal HiDPI support.
        The 'color', 'size', and 'y_offset' parameters are ignored but kept for compatibility.
        """
        # Path to icons
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "assets", "icons"))
        file_path = os.path.join(base_path, icon_type.value)
        
        if not os.path.exists(file_path):
            Logger.warning(f"Icon file not found: {file_path}")
            return

        # Use QIcon directly to let Qt handle HiDPI scaling and rendering
        icon = QIcon(file_path)
        button.setIcon(icon)
