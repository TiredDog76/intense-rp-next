from __future__ import annotations

import sys
from pathlib import Path


def is_pyinstaller_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_nuitka_compiled() -> bool:
    return "__compiled__" in globals()


def is_packaged_app() -> bool:
    return is_pyinstaller_frozen() or is_nuitka_compiled()


def get_executable_path() -> Path:
    if is_nuitka_compiled():
        # Nuitka standalone/onefile keeps the real emitted binary in argv[0];
        # sys.executable can still point at python.exe.
        return Path(sys.argv[0]).expanduser().resolve()
    if is_pyinstaller_frozen():
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).expanduser().resolve()


def get_packaged_app_dir() -> Path | None:
    if is_nuitka_compiled():
        return get_executable_path().parent

    if is_pyinstaller_frozen():
        return Path(sys.executable).resolve().parent

    return None


def get_source_root() -> Path:
    return Path(__file__).resolve().parent.parent
