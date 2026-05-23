from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import patchright

from drivers.providers import DriverProvider
from utils.logger import Logger


PROFILE_COMPATIBILITY_META_FILE = ".irp_profile_meta.json"


@dataclass(frozen=True)
class BrowserBuildInfo:
    version: str = ""
    major: int | None = None
    title: str = ""
    revision: str = ""


@dataclass(frozen=True)
class ProfileVersionInfo:
    created_by_version: str = ""
    created_by_major: int | None = None
    last_chrome_version: str = ""
    last_chrome_major: int | None = None


@dataclass(frozen=True)
class ProfileCompatibilityAssessment:
    provider_key: str
    provider_label: str
    profile_dir: str
    profile_created_by_version: str
    profile_last_chrome_version: str
    current_browser_version: str
    current_browser_title: str
    last_auth_success_browser_version: str
    has_version_mismatch: bool
    has_current_auth_success: bool
    should_warn: bool

    def to_payload(self, auth_error: str | None = None) -> dict[str, Any]:
        payload = asdict(self)
        payload["auth_error"] = str(auth_error or "").strip()
        return payload


def _parse_major(version: object) -> int | None:
    raw = str(version or "").strip()
    if not raw:
        return None
    first = raw.split(".", 1)[0].strip()
    if not first.isdigit():
        return None
    try:
        return int(first)
    except Exception:
        return None


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def get_current_chromium_build_info() -> BrowserBuildInfo:
    browsers_json = Path(patchright.__file__).resolve().parent / "driver" / "package" / "browsers.json"
    data = _read_json_file(browsers_json)

    for browser in data.get("browsers") or []:
        if not isinstance(browser, dict):
            continue
        if str(browser.get("name") or "").strip() != "chromium":
            continue
        version = str(browser.get("browserVersion") or "").strip()
        return BrowserBuildInfo(
            version=version,
            major=_parse_major(version),
            title=str(browser.get("title") or "Chromium").strip() or "Chromium",
            revision=str(browser.get("revision") or "").strip(),
        )

    return BrowserBuildInfo()


def read_profile_version_info(profile_dir: str | Path) -> ProfileVersionInfo:
    prefs_path = Path(profile_dir) / "Default" / "Preferences"
    data = _read_json_file(prefs_path)

    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    extensions = data.get("extensions") if isinstance(data.get("extensions"), dict) else {}

    created_by = str(profile.get("created_by_version") or "").strip()
    last_chrome = str(extensions.get("last_chrome_version") or "").strip()
    return ProfileVersionInfo(
        created_by_version=created_by,
        created_by_major=_parse_major(created_by),
        last_chrome_version=last_chrome,
        last_chrome_major=_parse_major(last_chrome),
    )


def _read_profile_meta(profile_dir: str | Path) -> dict[str, Any]:
    return _read_json_file(Path(profile_dir) / PROFILE_COMPATIBILITY_META_FILE)


def assess_profile_compatibility(
    profile_dir: str | Path,
    provider: DriverProvider,
) -> ProfileCompatibilityAssessment:
    profile_path = Path(profile_dir)
    profile_info = read_profile_version_info(profile_path)
    browser_info = get_current_chromium_build_info()
    meta = _read_profile_meta(profile_path)

    last_auth_success = str(meta.get("last_auth_success_browser_version") or "").strip()
    last_auth_success_major = _parse_major(last_auth_success)

    source_major = profile_info.created_by_major
    if source_major is None:
        source_major = profile_info.last_chrome_major

    has_version_mismatch = (
        source_major is not None
        and browser_info.major is not None
        and source_major != browser_info.major
    )
    has_current_auth_success = (
        last_auth_success_major is not None
        and browser_info.major is not None
        and last_auth_success_major == browser_info.major
    )

    return ProfileCompatibilityAssessment(
        provider_key=provider.key,
        provider_label=provider.value,
        profile_dir=str(profile_path),
        profile_created_by_version=profile_info.created_by_version,
        profile_last_chrome_version=profile_info.last_chrome_version,
        current_browser_version=browser_info.version,
        current_browser_title=browser_info.title,
        last_auth_success_browser_version=last_auth_success,
        has_version_mismatch=has_version_mismatch,
        has_current_auth_success=has_current_auth_success,
        should_warn=bool(has_version_mismatch and not has_current_auth_success),
    )


def mark_profile_auth_success(profile_dir: str | Path) -> None:
    profile_path = Path(profile_dir)
    try:
        profile_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    browser_info = get_current_chromium_build_info()
    meta_path = profile_path / PROFILE_COMPATIBILITY_META_FILE
    meta = _read_profile_meta(profile_path)
    meta.update(
        {
            "last_auth_success_browser_version": browser_info.version,
            "last_auth_success_browser_title": browser_info.title,
            "last_auth_success_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    try:
        meta_path.write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        Logger.debug(f"Could not write profile compatibility metadata: {exc}")
