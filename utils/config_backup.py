from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from cryptography.fernet import Fernet

from config.location import get_local_anchor_dir
from utils.logger import Logger


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except Exception:
        try:
            return path.expanduser().absolute()
        except Exception:
            return path


def _is_subpath(child: Path, parent: Path) -> bool:
    try:
        _safe_resolve(child).relative_to(_safe_resolve(parent))
        return True
    except Exception:
        return False


def _looks_like_config_dir(path: Path) -> bool:
    return (
        (path / "settings.json.enc").is_file()
        or (path / "settings.key").is_file()
        or (path / "playwright_profiles").is_dir()
    )


def _ensure_safe_target_config_dir(config_dir: Path) -> tuple[bool, str]:
    target = _safe_resolve(config_dir)

    # Never allow filesystem roots
    if target == Path(target.anchor):
        return False, "Refusing to use a filesystem root as a config directory."

    # Never allow wiping/moving the app directory or any directory containing it
    anchor = _safe_resolve(get_local_anchor_dir())
    if target == anchor or _is_subpath(anchor, target):
        return (
            False,
            "Refusing to use the application folder (or a parent of it) as the config directory.",
        )

    if target.exists():
        if not target.is_dir():
            return False, "Config directory path exists but is not a directory."

        try:
            has_any = any(target.iterdir())
        except Exception:
            has_any = True

        if has_any and not _looks_like_config_dir(target):
            return (
                False,
                "Config directory is not empty and does not look like an IntenseRP Next config directory.",
            )

    return True, ""


def _normalize_zip_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if p.suffix.lower() != ".zip":
        p = p.with_suffix(".zip")
    return _safe_resolve(p)


def create_config_backup_zip(config_dir: str | Path, output_zip: str | Path) -> tuple[bool, str]:
    src_dir = _safe_resolve(Path(config_dir))
    zip_path = _normalize_zip_path(output_zip)

    if not src_dir.exists() or not src_dir.is_dir():
        return False, f"Config directory does not exist: {src_dir}"

    zip_path.parent.mkdir(parents=True, exist_ok=True)

    skipped: list[str] = []
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in src_dir.rglob("*"):
                if not file_path.is_file():
                    continue

                try:
                    if _safe_resolve(file_path) == zip_path:
                        continue
                except Exception:
                    pass

                try:
                    arcname = file_path.relative_to(src_dir).as_posix()
                except Exception:
                    arcname = file_path.name

                try:
                    zf.write(file_path, arcname=arcname)
                except Exception as e:
                    skipped.append(f"{arcname} ({e})")
    except Exception as e:
        return False, f"Failed to write zip: {e}"

    if skipped:
        preview = "\n".join(skipped[:10])
        suffix = "\n\nSome files could not be added. Stop the app (or stop services) and try again for a complete backup."
        if len(skipped) > 10:
            suffix = f"\n\n...and {len(skipped) - 10} more." + suffix
        Logger.warning(f"Backup zip created with skipped files ({len(skipped)}).")
        return True, f"Backup created: {zip_path}\n\nSkipped files:\n{preview}{suffix}"

    return True, f"Backup created: {zip_path}"


def _validate_decryptable_settings(root: Path) -> tuple[bool, str]:
    key_file = root / "settings.key"
    settings_file = root / "settings.json.enc"

    if not key_file.is_file():
        return False, "Backup is missing settings.key."
    if not settings_file.is_file():
        return False, "Backup is missing settings.json.enc."

    try:
        key = key_file.read_bytes()
        cipher = Fernet(key)
        decrypted = cipher.decrypt(settings_file.read_bytes())
        json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        return False, f"Backup settings could not be decrypted/parsed: {e}"

    return True, ""


def _is_unsafe_zip_member(name: str) -> bool:
    if not name or name in (".", ".."):
        return True
    if "\\" in name:
        return True

    posix = PurePosixPath(name)
    if posix.is_absolute():
        return True

    if any(part in ("..", "") for part in posix.parts):
        return True

    # Block Windows drive prefixes like "C:/..."
    if posix.parts and ":" in posix.parts[0]:
        return True

    return False


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                name = info.filename
                if name.endswith("/"):
                    # directory entry
                    continue
                if _is_unsafe_zip_member(name):
                    return False, f"Zip contains an unsafe path: {name}"

                rel = PurePosixPath(name)
                out_path = dest_dir.joinpath(*rel.parts)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                with zf.open(info, "r") as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except Exception as e:
        return False, f"Failed to read/extract zip: {e}"

    return True, ""


def _find_backup_root(extract_dir: Path) -> Path | None:
    if _looks_like_config_dir(extract_dir):
        return extract_dir

    try:
        entries = list(extract_dir.iterdir())
    except Exception:
        return None

    dirs = [p for p in entries if p.is_dir()]
    files = [p for p in entries if p.is_file()]

    if len(dirs) == 1 and not files:
        candidate = dirs[0]
        if _looks_like_config_dir(candidate):
            return candidate

    return None


def import_config_backup_zip(zip_file: str | Path, target_config_dir: str | Path) -> tuple[bool, str]:
    zip_path = _safe_resolve(Path(zip_file))
    target_dir = _safe_resolve(Path(target_config_dir))

    if not zip_path.is_file():
        return False, f"Zip file does not exist: {zip_path}"

    ok, reason = _ensure_safe_target_config_dir(target_dir)
    if not ok:
        return False, reason

    with tempfile.TemporaryDirectory(prefix="irpnext-import-") as tmp:
        extract_dir = Path(tmp)

        ok, reason = _safe_extract_zip(zip_path, extract_dir)
        if not ok:
            return False, reason

        root = _find_backup_root(extract_dir)
        if root is None:
            return False, "Zip does not look like an IntenseRP Next config backup (missing settings/key)."

        ok, reason = _validate_decryptable_settings(root)
        if not ok:
            return False, reason

        parent = target_dir.parent
        parent.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        staging_dir = parent / f"__irpnext_config_import_staging_{ts}"
        old_dir = parent / f"__irpnext_config_import_old_{ts}"

        for i in range(2, 1000):
            if staging_dir.exists() or old_dir.exists():
                staging_dir = parent / f"__irpnext_config_import_staging_{ts}_{i}"
                old_dir = parent / f"__irpnext_config_import_old_{ts}_{i}"
                continue
            break

        try:
            shutil.copytree(root, staging_dir)
        except Exception as e:
            try:
                shutil.rmtree(staging_dir)
            except Exception:
                pass
            return False, f"Failed to stage imported config directory: {e}"

        try:
            if target_dir.exists():
                if old_dir.exists():
                    shutil.rmtree(old_dir)
                target_dir.rename(old_dir)
            staging_dir.rename(target_dir)
        except Exception as e:
            # Roll back best-effort: restore original and remove staging
            try:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir)
            except Exception:
                pass
            try:
                if old_dir.exists() and not target_dir.exists():
                    old_dir.rename(target_dir)
            except Exception:
                pass
            return False, f"Failed to replace config directory contents: {e}"

        # Cleanup old config dir after successful swap
        try:
            if old_dir.exists():
                shutil.rmtree(old_dir)
        except Exception as e:
            Logger.warning(f"Imported settings, but failed to delete old config dir '{old_dir}': {e}")

    return True, f"Import complete. Settings restored into: {target_dir}"

