from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from drivers.providers import DriverProvider

MODE_AUTO = "auto"
MODE_CHAT = "chat"
MODE_REASONER = "reasoner"


DEEPSEEK_BETTER_BASES: tuple[str, ...] = ("deepseek-v3.2",)
MOONSHOT_BETTER_BASES: tuple[str, ...] = ("kimi-k2.5",)
GLM_BETTER_BASES: tuple[str, ...] = ("glm-4.6", "glm-4.7", "glm-5")
QWEN_BETTER_BASES: tuple[str, ...] = (
    "qwen3.5-plus",
    "qwen3.5-flash",
    "qwen3.5-397b-a17b",
    "qwen3.5-122b-a10b",
    "qwen3.5-27b",
    "qwen3.5-35b-a3b",
    "qwen3-max",
    "qwen3-235b-a22b-2507",
    "qwen3-coder",
    "qwen3-vl-235b-a22b",
    "qwen3-omni-flash",
    "qwen2.5-max",
)
AISTUDIO_LABEL_TO_BASE: Dict[str, str] = {
    "Gemini 3.1 Pro": "gemini-3.1-pro-preview",
    "Gemini 3.1 Flash Lite": "gemini-3.1-flash-lite-preview",
    "Gemini 3 Flash": "gemini-3-flash-preview",
    "Gemini 2.5 Pro": "gemini-2.5-pro",
    "Gemini 2.5 Flash": "gemini-2.5-flash",
    "Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
}
AISTUDIO_BETTER_BASES: tuple[str, ...] = tuple(AISTUDIO_LABEL_TO_BASE.values())


LEGACY_MODE_BY_PROVIDER: Dict[DriverProvider, Dict[str, str]] = {
    DriverProvider.DEEPSEEK: {
        "deepseek-auto": MODE_AUTO,
        "deepseek-chat": MODE_CHAT,
        "deepseek-reasoner": MODE_REASONER,
    },
    DriverProvider.GLM_CHAT: {
        "glm-auto": MODE_AUTO,
        "glm-chat": MODE_CHAT,
        "glm-reasoner": MODE_REASONER,
    },
    DriverProvider.MOONSHOT: {
        "moonshot-auto": MODE_AUTO,
        "moonshot-chat": MODE_CHAT,
        "moonshot-reasoner": MODE_REASONER,
    },
    DriverProvider.QWEN_LM: {
        "qwen-auto": MODE_AUTO,
        "qwen-chat": MODE_CHAT,
        "qwen-reasoner": MODE_REASONER,
    },
    DriverProvider.AI_STUDIO: {
        "aistudio-auto": MODE_AUTO,
        "aistudio-chat": MODE_CHAT,
        "aistudio-reasoner": MODE_REASONER,
    },
}

LEGACY_MODEL_PREFIX_BY_PROVIDER: Dict[DriverProvider, str] = {
    DriverProvider.DEEPSEEK: "deepseek",
    DriverProvider.GLM_CHAT: "glm",
    DriverProvider.MOONSHOT: "moonshot",
    DriverProvider.QWEN_LM: "qwen",
    DriverProvider.AI_STUDIO: "aistudio",
}

OWNED_BY_PROVIDER: Dict[DriverProvider, str] = {
    DriverProvider.DEEPSEEK: "deepseek",
    DriverProvider.GLM_CHAT: "glm",
    DriverProvider.MOONSHOT: "moonshot",
    DriverProvider.QWEN_LM: "qwen",
    DriverProvider.AI_STUDIO: "aistudio",
}


def is_better_model_names_enabled(config_manager: Any) -> bool:
    try:
        return bool(config_manager.get_setting("experimental", "better_model_names"))
    except Exception:
        return False


def get_legacy_model_ids(provider: DriverProvider) -> list[str]:
    if provider == DriverProvider.GLM_CHAT:
        return ["glm-auto", "glm-chat", "glm-reasoner"]
    if provider == DriverProvider.MOONSHOT:
        return ["moonshot-auto", "moonshot-chat", "moonshot-reasoner"]
    if provider == DriverProvider.QWEN_LM:
        return ["qwen-auto", "qwen-chat", "qwen-reasoner"]
    if provider == DriverProvider.AI_STUDIO:
        return ["aistudio-auto", "aistudio-chat", "aistudio-reasoner"]
    return ["deepseek-auto", "deepseek-chat", "deepseek-reasoner"]


def get_legacy_model_prefix(provider: DriverProvider) -> str:
    return LEGACY_MODEL_PREFIX_BY_PROVIDER.get(provider, "deepseek")


def get_owned_by_for_provider(provider: DriverProvider) -> str:
    return OWNED_BY_PROVIDER.get(provider, "deepseek")


def get_configured_glm_base_model(config_manager: Any) -> str:
    value = ""
    try:
        value = str(config_manager.get_setting("glm_behavior", "model") or "").strip()
    except Exception:
        value = ""

    normalized = value.strip().lower()
    normalized = normalized.replace("glm-4-6", "glm-4.6").replace("glm-4-7", "glm-4.7")

    if normalized in GLM_BETTER_BASES:
        return normalized

    return "glm-5"


def get_configured_qwen_base_model(config_manager: Any) -> str:
    value = ""
    try:
        value = str(config_manager.get_setting("qwen_behavior", "model") or "").strip()
    except Exception:
        value = ""

    normalized = value.strip().lower()
    normalized = normalized.replace(" ", "-").replace("_", "-")

    if normalized in QWEN_BETTER_BASES:
        return normalized

    return "qwen3.5-plus"


def _canonicalize_model_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def get_configured_aistudio_base_model(config_manager: Any) -> str:
    value = ""
    try:
        value = str(config_manager.get_setting("aistudio_behavior", "model") or "").strip()
    except Exception:
        value = ""

    normalized = str(value or "").strip().lower()
    if normalized in AISTUDIO_BETTER_BASES:
        return normalized

    wanted = _canonicalize_model_label(value)
    for label, base in AISTUDIO_LABEL_TO_BASE.items():
        if _canonicalize_model_label(label) == wanted:
            return base

    return "gemini-2.5-flash"


def get_better_model_bases(provider: DriverProvider, config_manager: Any) -> list[str]:
    if provider == DriverProvider.DEEPSEEK:
        return list(DEEPSEEK_BETTER_BASES)
    if provider == DriverProvider.MOONSHOT:
        return list(MOONSHOT_BETTER_BASES)
    if provider == DriverProvider.GLM_CHAT:
        return [get_configured_glm_base_model(config_manager)]
    if provider == DriverProvider.QWEN_LM:
        return [get_configured_qwen_base_model(config_manager)]
    if provider == DriverProvider.AI_STUDIO:
        return [get_configured_aistudio_base_model(config_manager)]
    return list(DEEPSEEK_BETTER_BASES)


def _better_bases_for_provider(provider: DriverProvider) -> set[str]:
    if provider == DriverProvider.DEEPSEEK:
        return set(DEEPSEEK_BETTER_BASES)
    if provider == DriverProvider.MOONSHOT:
        return set(MOONSHOT_BETTER_BASES)
    if provider == DriverProvider.GLM_CHAT:
        return set(GLM_BETTER_BASES)
    if provider == DriverProvider.QWEN_LM:
        return set(QWEN_BETTER_BASES)
    if provider == DriverProvider.AI_STUDIO:
        return set(AISTUDIO_BETTER_BASES)
    return set()


def build_better_model_ids_for_base(base: str) -> list[str]:
    base_id = str(base or "").strip()
    if not base_id:
        return []

    # Ordering matches the legacy /v1/models output: auto, chat, reasoner
    return [f"{base_id}-auto", base_id, f"{base_id}-think"]


def get_model_ids_for_provider(provider: DriverProvider, config_manager: Any) -> list[str]:
    if is_better_model_names_enabled(config_manager):
        ids: list[str] = []
        for base in get_better_model_bases(provider, config_manager):
            ids.extend(build_better_model_ids_for_base(base))
        return ids

    return get_legacy_model_ids(provider)


def get_model_ids_for_providers(
    providers: Iterable[DriverProvider],
    config_manager: Any,
    *,
    force_legacy: bool = False,
) -> list[tuple[DriverProvider, str]]:
    items: list[tuple[DriverProvider, str]] = []
    for provider in providers:
        model_ids = get_legacy_model_ids(provider) if force_legacy else get_model_ids_for_provider(provider, config_manager)
        items.extend((provider, model_id) for model_id in model_ids)
    return items


def resolve_provider_from_model_id(model: Any) -> DriverProvider | None:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return None

    for provider, prefix in LEGACY_MODEL_PREFIX_BY_PROVIDER.items():
        normalized_prefix = f"{prefix}-"
        if normalized == prefix or normalized.startswith(normalized_prefix):
            return provider

    return None


def resolve_behavior_mode(model: Any, provider: DriverProvider) -> str:
    """
    Resolve a requested OpenAI-style `model` string into an IntenseRP behavior mode.

    - MODE_AUTO: use the user's behavior settings
    - MODE_CHAT: force reasoning off
    - MODE_REASONER: force reasoning on (Send Reasoning follows user setting)

    This intentionally accepts both legacy IDs (deepseek-auto/chat/reasoner, etc.)
    and Better Model Names IDs (deepseek-v3.2[-auto|-think], etc.) regardless of
    whether the experimental setting is enabled. Unknown values fall back to MODE_AUTO.
    """

    normalized = str(model or "").strip().lower()
    if not normalized:
        return MODE_AUTO

    legacy_map = LEGACY_MODE_BY_PROVIDER.get(provider) or {}
    legacy_mode = legacy_map.get(normalized)
    if legacy_mode:
        return legacy_mode

    bases = _better_bases_for_provider(provider)
    if not bases:
        return MODE_AUTO

    def _split_suffix(value: str, suffix: str) -> str | None:
        if not value.endswith(suffix):
            return None
        base_part = value[: -len(suffix)].strip("-")
        return base_part or None

    base_auto = _split_suffix(normalized, "-auto")
    if base_auto and base_auto in bases:
        return MODE_AUTO

    base_think = _split_suffix(normalized, "-think")
    if base_think and base_think in bases:
        return MODE_REASONER

    # Accept a few extra aliases for convenience / backwards compatibility
    base_reasoner = _split_suffix(normalized, "-reasoner")
    if base_reasoner and base_reasoner in bases:
        return MODE_REASONER

    base_chat = _split_suffix(normalized, "-chat")
    if base_chat and base_chat in bases:
        return MODE_CHAT

    # No suffix means "chat" in the Better Model Names scheme
    if normalized in bases:
        return MODE_CHAT

    return MODE_AUTO


def build_openai_model_list(ids: Iterable[str], owned_by: str) -> List[Dict[str, Any]]:
    safe_owned = str(owned_by or "").strip() or "unknown"
    out: List[Dict[str, Any]] = []
    for mid in ids:
        sid = str(mid or "").strip()
        if not sid:
            continue
        out.append({"id": sid, "object": "model", "created": 0, "owned_by": safe_owned})
    return out
