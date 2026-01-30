from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

from utils.logger import Logger


def ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        Logger.warning(f"ECE: failed to create directory {path}: {exc}")


def load_or_create_settings_key(config_dir: Path) -> bytes:
    key_path = (Path(config_dir) / "settings.key").resolve()
    ensure_dir(key_path.parent)

    if key_path.exists():
        try:
            return key_path.read_bytes()
        except Exception as exc:
            Logger.warning(f"ECE: failed to read settings.key ({key_path}): {exc}")

    key = Fernet.generate_key()
    try:
        key_path.write_bytes(key)
    except Exception as exc:
        Logger.warning(f"ECE: failed to write settings.key ({key_path}): {exc}")
    return key


class EncryptedJsonFile:
    def __init__(self, path: Path, key: bytes) -> None:
        self.path = Path(path).resolve()
        self._cipher = Fernet(key)

    def read(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None

        try:
            encrypted = self.path.read_bytes()
            raw = self._cipher.decrypt(encrypted)
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            Logger.warning(f"ECE: failed to read {self.path.name}: {exc}")
        return None

    def write(self, payload: Dict[str, Any]) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
            encrypted = self._cipher.encrypt(raw)
            self.path.write_bytes(encrypted)
            return True
        except Exception as exc:
            Logger.warning(f"ECE: failed to write {self.path.name}: {exc}")
            return False

