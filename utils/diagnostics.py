from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from drivers.providers import DriverProvider
from utils.logger import Logger


_DIAGNOSTICS_DIRNAME = "bug_reports"
_INTERNAL_LOGS_DIRNAME = "logs"
_PROMPTS_DIRNAME = "prompts"
_INTERNAL_LOG_PREFIX = "internal_log_"
_INTERNAL_LOG_MAX_FILES = 5
_PROMPT_SNAPSHOT_VERSION = 1

_URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b")
_API_KEY_NAME_PATTERNS = (
    re.compile(r"(?i)(\bAPI key(?: name)?\s*:\s*)(.+)$"),
    re.compile(r"(?i)(\bapi_key_name\s*=\s*)([^\s,;]+)"),
)

_ACTIVE_INTERNAL_LOG_SINK: "_InternalDiagnosticsLogSink | None" = None
_ACTIVE_INTERNAL_LOG_SINK_LOCK = threading.RLock()


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except Exception:
        try:
            return path.expanduser().absolute()
        except Exception:
            return path


def _utc_timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _utc_timestamp_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_zip_path(path: str | Path) -> Path:
    zip_path = Path(path).expanduser()
    if zip_path.suffix.lower() != ".zip":
        zip_path = zip_path.with_suffix(".zip")
    return _safe_resolve(zip_path)


def _to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        normalized: Dict[str, Any] = {}
        for key, inner_value in value.items():
            normalized[str(key)] = _to_json_safe(inner_value)
        return normalized
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(item) for item in value]
    return str(value)


def _config_dir_from_manager(config_manager: Any) -> Path:
    return _safe_resolve(Path(getattr(config_manager, "config_dir", "config_data")))


def get_diagnostics_root(config_dir: str | Path) -> Path:
    return _safe_resolve(Path(config_dir)) / _DIAGNOSTICS_DIRNAME


def get_internal_logs_dir(config_dir: str | Path) -> Path:
    return get_diagnostics_root(config_dir) / _INTERNAL_LOGS_DIRNAME


def get_prompt_snapshots_dir(config_dir: str | Path) -> Path:
    return get_diagnostics_root(config_dir) / _PROMPTS_DIRNAME


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def diagnostics_internal_log_enabled(config_manager: Any) -> bool:
    try:
        return bool(config_manager.get_setting("diagnostics", "keep_internal_log"))
    except Exception:
        return False


def diagnostics_prompt_capture_enabled(config_manager: Any) -> bool:
    try:
        return bool(config_manager.get_setting("diagnostics", "save_last_prompt"))
    except Exception:
        return False


def clear_internal_logs(config_dir: str | Path) -> None:
    logs_dir = get_internal_logs_dir(config_dir)
    if not logs_dir.exists():
        return
    try:
        shutil.rmtree(logs_dir)
    except Exception:
        pass


def clear_prompt_snapshots(config_dir: str | Path) -> None:
    prompts_dir = get_prompt_snapshots_dir(config_dir)
    if not prompts_dir.exists():
        return
    try:
        shutil.rmtree(prompts_dir)
    except Exception:
        pass


def clear_all_diagnostics_artifacts(config_dir: str | Path) -> None:
    root = get_diagnostics_root(config_dir)
    if not root.exists():
        return
    try:
        shutil.rmtree(root)
    except Exception:
        pass


def _latest_file_in_dir(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    candidates = [path for path in directory.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime)
    return candidates[-1]


def get_latest_internal_log_path(config_dir: str | Path) -> Path | None:
    with _ACTIVE_INTERNAL_LOG_SINK_LOCK:
        active_sink = _ACTIVE_INTERNAL_LOG_SINK
        if active_sink is not None and active_sink.config_dir == _safe_resolve(Path(config_dir)):
            return active_sink.log_path
    return _latest_file_in_dir(get_internal_logs_dir(config_dir), f"{_INTERNAL_LOG_PREFIX}*.txt")


def _prune_old_internal_logs(logs_dir: Path) -> None:
    try:
        files = [path for path in logs_dir.glob(f"{_INTERNAL_LOG_PREFIX}*.txt") if path.is_file()]
        files.sort(key=lambda path: path.stat().st_mtime)
        while len(files) > _INTERNAL_LOG_MAX_FILES:
            oldest = files.pop(0)
            try:
                oldest.unlink()
            except Exception:
                pass
    except Exception:
        pass


class _DiagnosticsLogRedactor:
    def __init__(self) -> None:
        self._email_labels: dict[str, str] = {}
        self._next_email_index = 1

    def redact(self, text: str) -> str:
        redacted = str(text or "")
        redacted = _URL_RE.sub(self._replace_url, redacted)
        redacted = self._redact_api_key_names(redacted)
        redacted = _EMAIL_RE.sub(self._replace_email, redacted)
        redacted = _IPV4_RE.sub(self._replace_ipv4, redacted)
        return redacted

    def _replace_url(self, match: re.Match[str]) -> str:
        raw_url = str(match.group(0) or "")
        try:
            parsed = urlsplit(raw_url)
        except Exception:
            return raw_url
        if not parsed.scheme or not parsed.netloc:
            return raw_url
        return f"{parsed.scheme}://{parsed.netloc}/"

    def _redact_api_key_names(self, text: str) -> str:
        redacted = str(text or "")
        for pattern in _API_KEY_NAME_PATTERNS:
            redacted = pattern.sub(r"\1[API key name]", redacted)
        return redacted

    def _replace_email(self, match: re.Match[str]) -> str:
        email = str(match.group(0) or "")
        normalized = email.lower()
        label = self._email_labels.get(normalized)
        if label is None:
            label = f"[email {self._next_email_index}]"
            self._email_labels[normalized] = label
            self._next_email_index += 1
        return label

    def _replace_ipv4(self, match: re.Match[str]) -> str:
        raw = str(match.group(0) or "")
        host, sep, port = raw.partition(":")
        parts = host.split(".")
        if len(parts) != 4:
            return raw
        try:
            if any((int(part) < 0 or int(part) > 255) for part in parts):
                return raw
        except Exception:
            return raw

        redacted_host = ".".join("XXX" for _unused in parts)
        if sep and port.isdigit():
            return f"{redacted_host}:{port}"
        return redacted_host


class _InternalDiagnosticsLogSink:
    def __init__(self, config_dir: str | Path) -> None:
        self.config_dir = _safe_resolve(Path(config_dir))
        self.log_dir = _ensure_dir(get_internal_logs_dir(self.config_dir))
        self.log_path = self.log_dir / f"{_INTERNAL_LOG_PREFIX}{_utc_timestamp_slug()}.txt"
        self._redactor = _DiagnosticsLogRedactor()
        self._lock = threading.RLock()
        self.callback = self.handle_log
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.touch(exist_ok=True)
        except Exception:
            pass
        _prune_old_internal_logs(self.log_dir)

    def handle_log(self, _level: Any, message: str) -> None:
        line = self._redactor.redact(str(message or ""))
        try:
            with self._lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except Exception:
            pass

    def close(self) -> None:
        return


def configure_internal_diagnostics_logging(config_manager: Any) -> None:
    global _ACTIVE_INTERNAL_LOG_SINK

    config_dir = _config_dir_from_manager(config_manager)
    enabled = diagnostics_internal_log_enabled(config_manager)
    detached_dir: Path | None = None

    with _ACTIVE_INTERNAL_LOG_SINK_LOCK:
        current_sink = _ACTIVE_INTERNAL_LOG_SINK
        current_dir = current_sink.config_dir if current_sink is not None else None

        if enabled and current_sink is not None and current_dir == config_dir:
            return

        if current_sink is not None:
            try:
                Logger.remove_listener(current_sink.callback)
            except Exception:
                pass
            try:
                current_sink.close()
            except Exception:
                pass
            _ACTIVE_INTERNAL_LOG_SINK = None
            detached_dir = current_dir

        if enabled:
            new_sink = _InternalDiagnosticsLogSink(config_dir)
            _ACTIVE_INTERNAL_LOG_SINK = new_sink
            Logger.add_listener(new_sink.callback)
            return

    clear_internal_logs(config_dir)
    if detached_dir is not None and detached_dir != config_dir:
        clear_internal_logs(detached_dir)


def capture_prompt_snapshot(
    config_manager: Any,
    provider: DriverProvider,
    prompt: str,
    *,
    system_prompt_text: str = "",
    extra_prompt_texts: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not diagnostics_prompt_capture_enabled(config_manager):
        return

    prompts_dir = _ensure_dir(get_prompt_snapshots_dir(_config_dir_from_manager(config_manager)))
    payload: Dict[str, Any] = {
        "version": _PROMPT_SNAPSHOT_VERSION,
        "provider_key": str(provider.key),
        "provider_label": str(provider.value),
        "captured_at": _utc_timestamp_iso(),
        "prompt": str(prompt or ""),
    }
    if str(system_prompt_text or "").strip():
        payload["system_prompt_text"] = str(system_prompt_text or "")

    normalized_extra_texts: Dict[str, str] = {}
    for key, value in (extra_prompt_texts or {}).items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        value_text = str(value or "")
        if not value_text.strip():
            continue
        normalized_extra_texts[key_text] = value_text
    if normalized_extra_texts:
        payload["extra_prompt_texts"] = normalized_extra_texts

    normalized_metadata = _to_json_safe(metadata or {})
    if normalized_metadata:
        payload["metadata"] = normalized_metadata

    snapshot_path = prompts_dir / f"{provider.key}.json"
    try:
        snapshot_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_prompt_snapshot(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    provider_key = str(data.get("provider_key") or path.stem).strip()
    provider_label = str(data.get("provider_label") or provider_key).strip()
    prompt = str(data.get("prompt") or "")
    if not provider_key:
        return None
    snapshot: dict[str, Any] = {
        "provider_key": provider_key,
        "provider_label": provider_label,
        "captured_at": str(data.get("captured_at") or ""),
        "prompt": prompt,
        "path": str(path),
    }
    system_prompt_text = str(data.get("system_prompt_text") or "")
    if system_prompt_text:
        snapshot["system_prompt_text"] = system_prompt_text
    extra_prompt_texts = data.get("extra_prompt_texts")
    if isinstance(extra_prompt_texts, dict):
        normalized_extra: dict[str, str] = {}
        for key, value in extra_prompt_texts.items():
            key_text = str(key or "").strip()
            if not key_text:
                continue
            normalized_extra[key_text] = str(value or "")
        if normalized_extra:
            snapshot["extra_prompt_texts"] = normalized_extra
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        snapshot["metadata"] = metadata
    return snapshot


def list_prompt_snapshots(config_dir: str | Path) -> list[dict[str, Any]]:
    prompts_dir = get_prompt_snapshots_dir(config_dir)
    if not prompts_dir.exists():
        return []

    snapshots: list[dict[str, Any]] = []
    for path in sorted(prompts_dir.glob("*.json")):
        if not path.is_file():
            continue
        snapshot = _load_prompt_snapshot(path)
        if snapshot is not None:
            snapshots.append(snapshot)
    snapshots.sort(
        key=lambda item: (
            _parse_iso_timestamp(item.get("captured_at")),
            str(item.get("provider_key") or ""),
        ),
        reverse=True,
    )
    return snapshots


def create_diagnostics_bundle_zip(config_manager: Any, output_zip: str | Path) -> tuple[bool, str]:
    config_dir = _config_dir_from_manager(config_manager)
    include_internal_log = diagnostics_internal_log_enabled(config_manager)
    include_prompts = diagnostics_prompt_capture_enabled(config_manager)

    if (not include_internal_log) and (not include_prompts):
        return (
            False,
            "Bug Reports are disabled in Settings. Enable the internal log and/or last prompt capture first, or collect the files manually.",
        )

    internal_log_path = get_latest_internal_log_path(config_dir) if include_internal_log else None
    prompt_snapshots = list_prompt_snapshots(config_dir) if include_prompts else []

    if internal_log_path is None and not prompt_snapshots:
        return (
            False,
            "No diagnostics data is available yet. Start a request first, then try again.",
        )

    zip_path = _normalize_zip_path(output_zip)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_root_name = zip_path.stem

    with tempfile.TemporaryDirectory(prefix="irpnext-bug-report-") as tmp:
        staging_root = Path(tmp) / bundle_root_name
        staging_root.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "generated_at": _utc_timestamp_iso(),
            "include_internal_log": bool(internal_log_path is not None),
            "include_prompt_snapshots": bool(prompt_snapshots),
            "prompt_snapshot_count": len(prompt_snapshots),
            "files": [],
        }

        if internal_log_path is not None and internal_log_path.is_file():
            log_target = staging_root / "internal-log.txt"
            shutil.copy2(internal_log_path, log_target)
            manifest["files"].append(log_target.name)

        if prompt_snapshots:
            prompts_root = staging_root / "prompts"
            prompts_root.mkdir(parents=True, exist_ok=True)
            prompt_index: list[dict[str, Any]] = []
            latest_snapshot = prompt_snapshots[0]
            for snapshot in prompt_snapshots:
                provider_key = str(snapshot.get("provider_key") or "provider").strip() or "provider"
                provider_label = str(snapshot.get("provider_label") or provider_key)
                captured_at = str(snapshot.get("captured_at") or "")
                is_latest_snapshot = snapshot is latest_snapshot

                prompt_target = prompts_root / f"{provider_key}-prompt.txt"
                prompt_target.write_text(str(snapshot.get("prompt") or ""), encoding="utf-8")
                manifest["files"].append(prompt_target.relative_to(staging_root).as_posix())

                snapshot_files = [prompt_target.relative_to(staging_root).as_posix()]

                system_prompt_text = str(snapshot.get("system_prompt_text") or "")
                if system_prompt_text:
                    system_target = prompts_root / f"{provider_key}-system-prompt.txt"
                    system_target.write_text(system_prompt_text, encoding="utf-8")
                    manifest["files"].append(system_target.relative_to(staging_root).as_posix())
                    snapshot_files.append(system_target.relative_to(staging_root).as_posix())

                extra_prompt_texts = snapshot.get("extra_prompt_texts")
                if isinstance(extra_prompt_texts, dict):
                    for extra_name, extra_text in extra_prompt_texts.items():
                        extra_key = re.sub(r"[^a-z0-9]+", "-", str(extra_name or "").strip().lower()).strip("-")
                        extra_key = extra_key or "extra"
                        extra_target = prompts_root / f"{provider_key}-{extra_key}.txt"
                        extra_target.write_text(str(extra_text or ""), encoding="utf-8")
                        manifest["files"].append(extra_target.relative_to(staging_root).as_posix())
                        snapshot_files.append(extra_target.relative_to(staging_root).as_posix())

                metadata_target = prompts_root / f"{provider_key}-metadata.json"
                metadata_payload = {
                    "provider_key": provider_key,
                    "provider_label": provider_label,
                    "captured_at": captured_at,
                    "latest_overall": bool(is_latest_snapshot),
                    "metadata": _to_json_safe(snapshot.get("metadata") or {}),
                }
                metadata_target.write_text(
                    json.dumps(metadata_payload, indent=2, ensure_ascii=True, sort_keys=True),
                    encoding="utf-8",
                )
                manifest["files"].append(metadata_target.relative_to(staging_root).as_posix())
                snapshot_files.append(metadata_target.relative_to(staging_root).as_posix())

                prompt_index.append(
                    {
                        "provider_key": provider_key,
                        "provider_label": provider_label,
                        "captured_at": captured_at,
                        "latest_overall": bool(is_latest_snapshot),
                        "files": snapshot_files,
                    }
                )

            latest_prompt_target = staging_root / "latest-prompt.txt"
            latest_prompt_target.write_text(str(latest_snapshot.get("prompt") or ""), encoding="utf-8")
            manifest["files"].append(latest_prompt_target.name)

            latest_system_prompt_text = str(latest_snapshot.get("system_prompt_text") or "")
            if latest_system_prompt_text:
                latest_system_target = staging_root / "latest-system-prompt.txt"
                latest_system_target.write_text(latest_system_prompt_text, encoding="utf-8")
                manifest["files"].append(latest_system_target.name)

            latest_summary_target = staging_root / "latest-prompt-metadata.json"
            latest_summary_target.write_text(
                json.dumps(
                    {
                        "provider_key": str(latest_snapshot.get("provider_key") or ""),
                        "provider_label": str(latest_snapshot.get("provider_label") or ""),
                        "captured_at": str(latest_snapshot.get("captured_at") or ""),
                    },
                    indent=2,
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            manifest["files"].append(latest_summary_target.name)

            prompt_index_target = prompts_root / "prompt-index.json"
            prompt_index_target.write_text(
                json.dumps(prompt_index, indent=2, ensure_ascii=True, sort_keys=True),
                encoding="utf-8",
            )
            manifest["files"].append(prompt_index_target.relative_to(staging_root).as_posix())

            manifest["latest_prompt"] = {
                "provider_key": str(latest_snapshot.get("provider_key") or ""),
                "provider_label": str(latest_snapshot.get("provider_label") or ""),
                "captured_at": str(latest_snapshot.get("captured_at") or ""),
            }

        manifest_target = staging_root / "manifest.json"
        manifest_target.write_text(
            json.dumps(_to_json_safe(manifest), indent=2, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )

        try:
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_path in staging_root.rglob("*"):
                    if not file_path.is_file():
                        continue
                    archive.write(file_path, arcname=file_path.relative_to(staging_root.parent).as_posix())
        except Exception as exc:
            return False, f"Failed to write bug report zip: {exc}"

    return True, f"Bug report bundle created: {zip_path}"
