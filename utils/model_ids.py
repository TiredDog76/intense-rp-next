from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from drivers.providers import DriverProvider

MODE_AUTO = "auto"
MODE_CHAT = "chat"
MODE_REASONER = "reasoner"


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

LEGACY_MODEL_IDS_BY_PROVIDER: Dict[DriverProvider, tuple[str, ...]] = {
    provider: tuple(model_map.keys())
    for provider, model_map in LEGACY_MODE_BY_PROVIDER.items()
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

AISTUDIO_MODEL_OVERRIDE_SUFFIX_RE = re.compile(r"-(minimal|low|medium|high|r[0-4])$")


def get_legacy_model_ids(provider: DriverProvider) -> list[str]:
    default_ids = LEGACY_MODEL_IDS_BY_PROVIDER[DriverProvider.DEEPSEEK]
    return list(LEGACY_MODEL_IDS_BY_PROVIDER.get(provider, default_ids))


def get_legacy_model_prefix(provider: DriverProvider) -> str:
    return LEGACY_MODEL_PREFIX_BY_PROVIDER.get(provider, "deepseek")


def get_owned_by_for_provider(provider: DriverProvider) -> str:
    return OWNED_BY_PROVIDER.get(provider, "deepseek")


def get_model_ids_for_provider(provider: DriverProvider, config_manager: Any) -> list[str]:
    _ = config_manager
    return get_legacy_model_ids(provider)


def get_model_ids_for_providers(
    providers: Iterable[DriverProvider],
    config_manager: Any,
    *,
    force_legacy: bool = False,
) -> list[tuple[DriverProvider, str]]:
    _ = force_legacy
    items: list[tuple[DriverProvider, str]] = []
    for provider in providers:
        model_ids = get_model_ids_for_provider(provider, config_manager)
        items.extend((provider, model_id) for model_id in model_ids)
    return items


def _strip_aistudio_override_suffix(model: str) -> str:
    normalized = str(model or "").strip().lower()
    return AISTUDIO_MODEL_OVERRIDE_SUFFIX_RE.sub("", normalized)


def is_supported_model_id(provider: DriverProvider, model: Any) -> bool:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return False

    legacy_map = LEGACY_MODE_BY_PROVIDER.get(provider) or {}
    if normalized in legacy_map:
        return True

    if provider == DriverProvider.AI_STUDIO:
        stripped = _strip_aistudio_override_suffix(normalized)
        return stripped in legacy_map

    return False


def resolve_provider_from_model_id(model: Any) -> DriverProvider | None:
    for provider in LEGACY_MODE_BY_PROVIDER:
        if is_supported_model_id(provider, model):
            return provider
    return None


def resolve_behavior_mode(model: Any, provider: DriverProvider) -> str:
    """
    Resolve a requested OpenAI-style `model` string into an IntenseRP behavior mode.

    - MODE_AUTO: use the user's behavior settings
    - MODE_CHAT: force reasoning off
    - MODE_REASONER: force reasoning on

    Unknown values fall back to MODE_AUTO. Google AI Studio also accepts its
    legacy thinking-level suffixes (for example `aistudio-auto-high`).
    """

    normalized = str(model or "").strip().lower()
    if not normalized:
        return MODE_AUTO

    if provider == DriverProvider.AI_STUDIO:
        normalized = _strip_aistudio_override_suffix(normalized)

    legacy_map = LEGACY_MODE_BY_PROVIDER.get(provider) or {}
    legacy_mode = legacy_map.get(normalized)
    if legacy_mode:
        return legacy_mode

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
