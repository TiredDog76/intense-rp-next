from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class VersionFileInfo:
    version: str
    auto_updateable: bool
    severity: int  # 1-4


def parse_version_file(
    text: str,
    *,
    default_version: str = "unknown",
    default_auto_updateable: bool = True,
    default_severity: int = 2,
    strict: bool = False,
) -> VersionFileInfo:
    """
    Parse version.json content.

    version.json is a JSON object with these keys:

    - version: SemVer-like string
    - aua: boolean (auto-updateable?)
    - severity: integer 1-4
    """

    value = (text or "").strip()
    if not value:
        if strict:
            raise ValueError("version.json is empty.")
        return VersionFileInfo(
            version=default_version,
            auto_updateable=default_auto_updateable,
            severity=_clamp_severity(default_severity, default=default_severity),
        )

    try:
        payload = json.loads(value)
    except Exception as exc:
        if strict:
            raise ValueError("version.json is not valid JSON.") from exc
        payload = {}

    if not isinstance(payload, dict):
        if strict:
            raise ValueError("version.json must be a JSON object.")
        payload = {}

    version_raw = payload.get("version", default_version)
    version_str = str(version_raw or "").strip() or default_version

    aua_raw = payload.get("aua", payload.get("auto_updateable", default_auto_updateable))
    aua = _coerce_bool(aua_raw, default_auto_updateable)

    severity_raw = payload.get("severity", default_severity)
    severity = _clamp_severity(_coerce_int(severity_raw, default_severity), default=default_severity)

    return VersionFileInfo(version=version_str, auto_updateable=aua, severity=severity)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        try:
            return bool(int(value))
        except Exception:
            return default
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on", "t"}:
            return True
        if v in {"0", "false", "no", "n", "off", "f"}:
            return False
        return default
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _clamp_severity(value: int, *, default: int) -> int:
    try:
        severity = int(value)
    except Exception:
        return default
    return severity if 1 <= severity <= 4 else default
