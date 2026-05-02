from __future__ import annotations

import os
import re
import sys
import tarfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests


GITHUB_OWNER = "LyubomirT"
GITHUB_REPO = "intense-rp-next"


class AutoUpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadProgress:
    bytes_downloaded: int
    total_bytes: Optional[int]
    speed_bytes_per_s: float


@dataclass(frozen=True)
class PreparedUpdate:
    tag: str
    release_name: str
    release_html_url: str
    asset_name: str
    asset_download_url: str
    extracted_app_root: Path


def get_current_platform() -> str:
    """Returns 'windows' or 'linux' based on current platform."""
    if sys.platform.startswith("win"):
        return "windows"
    elif sys.platform.startswith("linux"):
        return "linux"
    raise AutoUpdateError(f"Unsupported platform: {sys.platform}")


def normalize_tag(version: str) -> str:
    value = (version or "").strip()
    if not value:
        raise AutoUpdateError("Missing version tag.")
    if value.lower().startswith("v"):
        value = value[1:].strip()
    if not value or value.lower() == "unknown":
        raise AutoUpdateError("Invalid version tag.")
    return f"v{value}"


def fetch_release_by_tag(
    *,
    owner: str,
    repo: str,
    tag: str,
    timeout_s: float = 10.0,
) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    response = requests.get(
        url,
        timeout=timeout_s,
        headers={"User-Agent": "IntenseRP-Next-AutoUpdater"},
    )
    if response.status_code == 404:
        raise AutoUpdateError(f"Release not found for tag {tag}.")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise AutoUpdateError("Unexpected response from GitHub API.")
    return data


def _score_asset_name(name: str, platform: str) -> int:
    """Score an asset name based on how well it matches the target platform."""
    lowered = (name or "").lower()
    score = 0

    # Archive format scoring
    if platform == "windows":
        if lowered.endswith(".zip"):
            score += 100
    else:  # linux
        if lowered.endswith((".tar.gz", ".tgz")):
            score += 100
        elif lowered.endswith(".zip"):
            score += 50  # zip is acceptable but tar.gz preferred

    # Platform keyword scoring
    if platform == "windows":
        if "win" in lowered or "windows" in lowered:
            score += 40
        if "win32" in lowered:
            score += 10
    else:  # linux
        if "linux" in lowered:
            score += 40

    # Architecture scoring (common to both)
    if "x64" in lowered or "amd64" in lowered or "x86_64" in lowered:
        score += 20

    return score


def select_platform_asset(release: dict, platform: Optional[str] = None) -> dict:
    """Select the best asset for the specified platform (defaults to current)."""
    if platform is None:
        platform = get_current_platform()

    assets = release.get("assets")
    if not isinstance(assets, list) or not assets:
        raise AutoUpdateError("No release assets found.")

    best = None
    best_score = -1
    best_size = -1

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not name or not url:
            continue
        score = _score_asset_name(name, platform)
        size = int(asset.get("size") or 0)
        if score > best_score or (score == best_score and size > best_size):
            best = asset
            best_score = score
            best_size = size

    min_score = 50  # At least needs a valid archive format
    if best is None or best_score < min_score:
        raise AutoUpdateError(f"Could not locate a {platform} asset in the release.")
    return best


# Keep old name as alias for backwards compatibility in case I'm stupid and forgot to update something
# P.S. I know I am stupid sometimes
def select_windows_zip_asset(release: dict) -> dict:
    return select_platform_asset(release, platform="windows")


def download_with_progress(
    *,
    url: str,
    dest_path: Path,
    timeout_s: float = 30.0,
    chunk_size: int = 1024 * 256,
    progress_cb: Optional[Callable[[DownloadProgress], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    bytes_downloaded = 0
    total_bytes: Optional[int] = None
    started_at = time.monotonic()
    last_tick = started_at
    last_bytes = 0
    speed_bps = 0.0

    with requests.get(
        url,
        stream=True,
        timeout=timeout_s,
        headers={"User-Agent": "IntenseRP-Next-AutoUpdater"},
    ) as response:
        response.raise_for_status()
        try:
            total_bytes = int(response.headers.get("Content-Length") or 0) or None
        except Exception:
            total_bytes = None

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if should_cancel is not None and should_cancel():
                    raise AutoUpdateError("Download canceled.")
                if not chunk:
                    continue
                f.write(chunk)
                bytes_downloaded += len(chunk)

                now = time.monotonic()
                if now - last_tick >= 0.25:
                    dt = max(now - last_tick, 1e-6)
                    db = bytes_downloaded - last_bytes
                    inst = db / dt
                    # Smooth speed to avoid jitter.
                    speed_bps = (speed_bps * 0.8) + (inst * 0.2) if speed_bps else inst
                    last_tick = now
                    last_bytes = bytes_downloaded
                    if progress_cb is not None:
                        progress_cb(
                            DownloadProgress(
                                bytes_downloaded=bytes_downloaded,
                                total_bytes=total_bytes,
                                speed_bytes_per_s=speed_bps,
                            )
                        )

    # Final callback.
    elapsed = max(time.monotonic() - started_at, 1e-6)
    if progress_cb is not None:
        progress_cb(
            DownloadProgress(
                bytes_downloaded=bytes_downloaded,
                total_bytes=total_bytes,
                speed_bytes_per_s=bytes_downloaded / elapsed,
            )
        )


def extract_archive(archive_path: Path, extract_dir: Path) -> None:
    """Extract .zip or .tar.gz archives."""
    if not archive_path.exists():
        raise AutoUpdateError(f"Archive not found: {archive_path}")
    extract_dir.mkdir(parents=True, exist_ok=True)

    name_lower = archive_path.name.lower()
    try:
        if name_lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_dir)
        elif name_lower.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(extract_dir)
        else:
            raise AutoUpdateError(f"Unsupported archive format: {archive_path.name}")
    except (zipfile.BadZipFile, tarfile.TarError) as exc:
        raise AutoUpdateError("Downloaded file is not a valid archive.") from exc


# Keep old name as alias
# I swear I'm losing touch with reality
def extract_zip(zip_path: Path, extract_dir: Path) -> None:
    extract_archive(zip_path, extract_dir)


def _looks_like_app_root(path: Path, expected_exe_name: Optional[str]) -> bool:
    if not path.is_dir():
        return False
    try:
        entries = {p.name for p in path.iterdir()}
    except Exception:
        return False

    if "version.json" not in entries:
        return False

    # Trust the expected executable name
    if not expected_exe_name:
        return False
    return expected_exe_name in entries


def find_extracted_app_root(extract_dir: Path, expected_exe_name: Optional[str]) -> Path:
    if not extract_dir.exists():
        raise AutoUpdateError(f"Extract directory not found: {extract_dir}")

    # Common layout: <extract>/<archive-name>/<app-files...>
    candidates: list[Path] = []
    for root, dirs, _files in os.walk(extract_dir):
        root_path = Path(root)
        if _looks_like_app_root(root_path, expected_exe_name):
            candidates.append(root_path)

    if not candidates:
        raise AutoUpdateError(
            "Could not locate the extracted app folder (expected executable and version.json)."
        )

    # Prefer the shallowest match to avoid nested duplicates.
    candidates.sort(key=lambda p: (len(p.parts), str(p).lower()))
    return candidates[0]


def prepare_update_from_github(
    *,
    remote_version: str,
    expected_exe_name: Optional[str],
    download_dir: Path,
    extract_dir: Path,
    owner: str = GITHUB_OWNER,
    repo: str = GITHUB_REPO,
    progress_cb: Optional[Callable[[DownloadProgress], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PreparedUpdate:
    tag = normalize_tag(remote_version)
    release = fetch_release_by_tag(owner=owner, repo=repo, tag=tag)

    asset = select_platform_asset(release)
    asset_name = str(asset.get("name") or "")
    asset_download_url = str(asset.get("browser_download_url") or "")
    if not asset_name or not asset_download_url:
        raise AutoUpdateError("Release asset is missing a download URL.")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", asset_name) or "update.archive"
    archive_path = (download_dir / safe_name).resolve()

    download_with_progress(
        url=asset_download_url,
        dest_path=archive_path,
        progress_cb=progress_cb,
        should_cancel=should_cancel,
    )

    extract_archive(archive_path, extract_dir)
    app_root = find_extracted_app_root(extract_dir, expected_exe_name=expected_exe_name)

    release_name = str(release.get("name") or tag)
    release_html_url = str(release.get("html_url") or "")
    if not release_html_url:
        release_html_url = f"https://github.com/{owner}/{repo}/releases/tag/{tag}"

    return PreparedUpdate(
        tag=tag,
        release_name=release_name,
        release_html_url=release_html_url,
        asset_name=asset_name,
        asset_download_url=asset_download_url,
        extracted_app_root=app_root,
    )
