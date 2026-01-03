from __future__ import annotations

import os
import sys
from functools import lru_cache

from PySide6.QtGui import QIcon


@lru_cache(maxsize=1)
def get_app_icon() -> QIcon:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "assets", "brand"))

    ico_path = os.path.join(base_dir, "newlogo.ico")
    png_path = os.path.join(base_dir, "newlogo.png")

    candidates = [ico_path, png_path] if sys.platform.startswith("win") else [png_path, ico_path]

    icon = QIcon()
    for path in candidates:
        if os.path.exists(path):
            icon.addFile(path)
    return icon
