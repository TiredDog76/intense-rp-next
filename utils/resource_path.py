from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def resolve_resource_path(*parts: str) -> Path:
    """
    Resolve a resource path in both dev and PyInstaller-frozen runs.

    Search order:
    - PyInstaller extraction/bundle dir (sys._MEIPASS)
    - Executable directory (where users may place loose data)
    - Source checkout directory (repo/app root)
    """
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / Path(*parts))
        candidates.append(Path(sys.executable).resolve().parent / Path(*parts))

    # Source checkout (repo/app root is the parent directory of the utils/ package)
    candidates.append(Path(__file__).resolve().parent.parent / Path(*parts))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[-1]
