from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
from typing import Optional


class DriverProvider(str, Enum):
    DEEPSEEK = "DeepSeek"
    GLM_CHAT = "GLM Chat"
    MOONSHOT = "Moonshot"
    QWEN_LM = "QwenLM"
    # Backwards compatible alias (legacy label was "Moonshot / Kimi")
    MOONSHOT_KIMI = "Moonshot"

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
        if normalized in {"glm", "glm_chat", "glm chat", "z.ai", "zai", "zhipu", "zhipuai"}:
            return cls.GLM_CHAT
        if normalized in {
            "moonshot",
            "moonshot_kimi",
            "moonshot kimi",
            "moonshot / kimi",
            "moonshot/kimi",
            "kimi",
            "kimi ai",
            "kimi-ai",
        }:
            return cls.MOONSHOT
        if normalized in {
            "qwen",
            "qwenlm",
            "qwen lm",
            "qwen-lm",
            "qwen ai",
            "qwenai",
            "qwen chat",
            "chat.qwen.ai",
            "qwen chat ai",
            "qwen chat.ai",
        }:
            return cls.QWEN_LM

        return cls.DEEPSEEK

    @property
    def key(self) -> str:
        # Keep a stable storage key for Moonshot so we don't break existing
        # persistent sessions and account data when renaming display labels
        if self is DriverProvider.MOONSHOT:
            return "moonshot_kimi"
        raw = (self.value or "").strip().lower()
        return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")


def provider_options() -> list[str]:
    return [provider.value for provider in DriverProvider]


def get_playwright_profile_dir(config_dir: str | Path | None, provider: DriverProvider) -> Path:
    base_dir = Path(config_dir) if config_dir is not None else Path("config_data")
    return (base_dir.resolve() / "playwright_profiles" / provider.key)
