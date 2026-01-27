from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional, Union

from config.location import get_active_config_dir
from .logger import Logger

class CacheManager:
    def __init__(self, cache_dir: Union[str, Path, None] = None):
        if cache_dir is None:
            cache_dir = self._default_cache_dir()
        self.cache_dir = Path(cache_dir).expanduser()
        self.ensure_cache_dir()

    def ensure_cache_dir(self):
        """Creates the cache directory if it does not exist."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            Logger.error(f"Error creating cache directory {self.cache_dir}: {e}")

    def _default_cache_dir(self) -> Path:
        """
        Resolve the default cache directory.

        Prefer placing caches inside the active config directory so they stay portable
        and easy to delete (wipe the config dir, or just its cache subfolder).
        """
        try:
            return get_active_config_dir() / "cache"
        except Exception:
            return Path("cache")

    def get_cache_path_obj(self, filename: str) -> Path:
        """Returns the full Path to a cache file."""
        return (self.cache_dir / filename).resolve()

    def get_cache_path(self, filename):
        """Returns the full path to a cache file."""
        try:
            return str(self.get_cache_path_obj(str(filename)))
        except Exception:
            return os.path.join(str(self.cache_dir), str(filename))

    def read_cache(self, filename):
        """Reads content from a cache file. Returns None if file doesn't exist."""
        return self.read_text(filename)

    def read_text(self, filename: str) -> Optional[str]:
        path = self.get_cache_path_obj(str(filename))
        if not path.exists():
            return None

        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            Logger.error(f"Error reading cache file {filename}: {e}")
            return None

    def read_bytes(self, filename: str) -> Optional[bytes]:
        path = self.get_cache_path_obj(str(filename))
        if not path.exists():
            return None

        try:
            return path.read_bytes()
        except Exception as e:
            Logger.error(f"Error reading cache file {filename}: {e}")
            return None

    def write_cache(self, filename, content):
        """Writes content to a cache file."""
        self.write_text(filename, content)

    def write_text(self, filename: str, content: str) -> None:
        path = self.get_cache_path_obj(str(filename))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")
        except Exception as e:
            Logger.error(f"Error writing to cache file {filename}: {e}")

    def write_bytes(self, filename: str, content: bytes) -> None:
        path = self.get_cache_path_obj(str(filename))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except Exception as e:
            Logger.error(f"Error writing to cache file {filename}: {e}")

    def clear_cache(self, filename):
        """Removes a specific cache file."""
        path = self.get_cache_path_obj(str(filename))
        if not path.exists():
            return

        try:
            path.unlink()
        except Exception as e:
            Logger.error(f"Error clearing cache file {filename}: {e}")

    def clear_all_cache(self):
        """Removes the entire cache directory."""
        try:
            if self.cache_dir.exists():
                shutil.rmtree(str(self.cache_dir))
            self.ensure_cache_dir()
        except Exception as e:
            Logger.error(f"Error clearing all cache: {e}")
