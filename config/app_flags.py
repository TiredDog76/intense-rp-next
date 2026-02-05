from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet
from utils.logger import Logger


class AppFlagsStore:
    """
    Encrypted key/value store for hidden app flags that should persist across runs.
    """

    VERSION = 1
    FILENAME = "appflags.json.enc"

    def __init__(self, config_dir: str | Path):
        self.config_dir = Path(config_dir).resolve()
        self._flags_path = (self.config_dir / self.FILENAME).resolve()
        self._key_path = (self.config_dir / "settings.key").resolve()
        self._cipher = Fernet(self._load_or_create_settings_key())

    def _load_or_create_settings_key(self) -> bytes:
        try:
            self._key_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            Logger.warning(f"AppFlags: failed to create key directory ({self._key_path.parent}): {exc}")

        if self._key_path.exists():
            try:
                return self._key_path.read_bytes()
            except Exception as exc:
                Logger.warning(f"AppFlags: failed to read settings.key ({self._key_path}): {exc}")

        key = Fernet.generate_key()
        try:
            self._key_path.write_bytes(key)
        except Exception as exc:
            Logger.warning(f"AppFlags: failed to write settings.key ({self._key_path}): {exc}")
        return key

    def _read_payload(self) -> Dict[str, Any]:
        if not self._flags_path.exists():
            return {"version": self.VERSION, "flags": {}}

        try:
            encrypted = self._flags_path.read_bytes()
            decrypted = self._cipher.decrypt(encrypted)
            payload = json.loads(decrypted.decode("utf-8"))
            if not isinstance(payload, dict):
                return {"version": self.VERSION, "flags": {}}

            version = payload.get("version")
            flags = payload.get("flags")
            if not isinstance(version, int) or not isinstance(flags, dict):
                return {"version": self.VERSION, "flags": {}}
            return payload
        except Exception as exc:
            Logger.warning(f"AppFlags: failed to read {self._flags_path.name}: {exc}")
            return {"version": self.VERSION, "flags": {}}

    def _write_payload(self, flags: Dict[str, Any]) -> bool:
        payload = {"version": self.VERSION, "flags": dict(flags)}
        try:
            self._flags_path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
            encrypted = self._cipher.encrypt(raw)
            self._flags_path.write_bytes(encrypted)
            return True
        except Exception as exc:
            Logger.warning(f"AppFlags: failed to write {self._flags_path.name}: {exc}")
            return False

    @staticmethod
    def _normalize_key(key: str) -> str:
        return str(key or "").strip()

    def get(self, key: str, default: Any = None) -> Any:
        flag_key = self._normalize_key(key)
        if not flag_key:
            return default

        payload = self._read_payload()
        flags = payload.get("flags")
        if not isinstance(flags, dict):
            return default
        return flags.get(flag_key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def set(self, key: str, value: Any) -> bool:
        flag_key = self._normalize_key(key)
        if not flag_key:
            Logger.warning("AppFlags: refusing to set empty key.")
            return False

        payload = self._read_payload()
        flags = payload.get("flags") if isinstance(payload.get("flags"), dict) else {}
        updated = dict(flags)
        updated[flag_key] = value
        ok = self._write_payload(updated)
        if not ok:
            Logger.warning(f"AppFlags: failed to persist key '{flag_key}'.")
        return ok

    def delete(self, key: str) -> bool:
        flag_key = self._normalize_key(key)
        if not flag_key:
            return False

        payload = self._read_payload()
        flags = payload.get("flags") if isinstance(payload.get("flags"), dict) else {}
        if flag_key not in flags:
            return True

        updated = dict(flags)
        del updated[flag_key]
        ok = self._write_payload(updated)
        if not ok:
            Logger.warning(f"AppFlags: failed to delete key '{flag_key}'.")
        return ok

    def clear(self) -> bool:
        ok = self._write_payload({})
        if not ok:
            Logger.warning("AppFlags: failed to clear all flags.")
        return ok

    def as_dict(self) -> Dict[str, Any]:
        payload = self._read_payload()
        flags = payload.get("flags")
        if not isinstance(flags, dict):
            return {}
        return dict(flags)
