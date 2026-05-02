from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from utils.runtime import get_packaged_app_dir, get_source_root, is_packaged_app


@lru_cache(maxsize=None)
def resolve_resource_path(*parts: str) -> Path:
    """
    Resolve a resource path in source and packaged runs.

    Search order:
    - PyInstaller extraction/bundle dir (sys._MEIPASS)
    - Packaged executable directory
    - Source checkout directory (repo/app root)
    """
    candidates: list[Path] = []

    if is_packaged_app():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / Path(*parts))
        packaged_dir = get_packaged_app_dir()
        if packaged_dir is not None:
            candidates.append(packaged_dir / Path(*parts))

    # Source checkout (repo/app root is the parent directory of the utils/ package)
    candidates.append(get_source_root() / Path(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[-1]
