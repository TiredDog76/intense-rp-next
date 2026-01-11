from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional


class DriverProvider(str, Enum):
    DEEPSEEK = "DeepSeek"

    @classmethod
    def from_setting(cls, value: Optional[str]) -> "DriverProvider":
        normalized = (value or "").strip().lower()
        if not normalized:
            return cls.DEEPSEEK

        for provider in cls:
            if provider.value.lower() == normalized:
                return provider

        if normalized == "deepseek":
            return cls.DEEPSEEK

        return cls.DEEPSEEK

    @property
    def key(self) -> str:
        return (self.value or "").strip().lower().replace(" ", "_")


def provider_options() -> list[str]:
    return [provider.value for provider in DriverProvider]


def get_playwright_profile_dir(config_dir: str | Path | None, provider: DriverProvider) -> Path:
    base_dir = Path(config_dir) if config_dir is not None else Path("config_data")
    return (base_dir.resolve() / "playwright_profiles" / provider.key)

