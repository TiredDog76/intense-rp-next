from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping

from drivers.providers import DriverProvider

MODE_AUTO = "auto"
MODE_CHAT = "chat"
MODE_REASONER = "reasoner"
DEEPSEEK_MODEL_TYPE_DEFAULT = "default"
DEEPSEEK_MODEL_TYPE_EXPERT = "expert"

REAL_MODEL_SUFFIX_MODE_BY_SUFFIX: tuple[tuple[str, str], ...] = (
    ("-auto", MODE_AUTO),
    ("-reasoner", MODE_REASONER),
    ("-chat", MODE_CHAT),
)

REAL_MODEL_ID_PROVIDERS: set[DriverProvider] = {
    DriverProvider.GLM_CHAT,
    DriverProvider.QWEN_LM,
    DriverProvider.PERPLEXITY,
    DriverProvider.AI_STUDIO,
}

UMM_MODEL_IDS: tuple[str, ...] = (
    "intenserp-auto",
    "intenserp-reasoner",
    "intenserp-chat",
)

UMM_MODE_BY_MODEL_ID: Dict[str, str] = {
    "intenserp-auto": MODE_AUTO,
    "intenserp-reasoner": MODE_REASONER,
    "intenserp-chat": MODE_CHAT,
}

DEEPSEEK_UMM_EXPERT_MODE_BY_MODEL_ID: Dict[str, str] = {
    "intenserp-expert-auto": MODE_AUTO,
    "intenserp-expert-reasoner": MODE_REASONER,
    "intenserp-expert-chat": MODE_CHAT,
}

DEEPSEEK_UMM_EXPERT_MODEL_IDS: tuple[str, ...] = tuple(DEEPSEEK_UMM_EXPERT_MODE_BY_MODEL_ID.keys())


LEGACY_MODE_BY_PROVIDER: Dict[DriverProvider, Dict[str, str]] = {
    DriverProvider.DEEPSEEK: {
        "deepseek-auto": MODE_AUTO,
        "deepseek-chat": MODE_CHAT,
        "deepseek-reasoner": MODE_REASONER,
        "deepseek-expert-auto": MODE_AUTO,
        "deepseek-expert-chat": MODE_CHAT,
        "deepseek-expert-reasoner": MODE_REASONER,
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
    DriverProvider.PERPLEXITY: {
        "perplexity-auto": MODE_AUTO,
        "perplexity-chat": MODE_CHAT,
        "perplexity-reasoner": MODE_REASONER,
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
    DriverProvider.PERPLEXITY: "perplexity",
    DriverProvider.AI_STUDIO: "aistudio",
}

OWNED_BY_PROVIDER: Dict[DriverProvider, str] = {
    DriverProvider.DEEPSEEK: "deepseek",
    DriverProvider.GLM_CHAT: "glm",
    DriverProvider.MOONSHOT: "moonshot",
    DriverProvider.QWEN_LM: "qwen",
    DriverProvider.PERPLEXITY: "perplexity",
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


def is_umm_enabled(config_manager: Any) -> bool:
    try:
        return bool(config_manager.get_setting("network_settings", "enable_umm"))
    except Exception:
        return False


def _get_universal_mode_map(provider: DriverProvider) -> Dict[str, str]:
    if provider == DriverProvider.DEEPSEEK:
        return {
            **UMM_MODE_BY_MODEL_ID,
            **DEEPSEEK_UMM_EXPERT_MODE_BY_MODEL_ID,
        }
    return UMM_MODE_BY_MODEL_ID


def normalize_real_model_api_base(label: Any) -> str:
    normalized = str(label or "").strip().lower()
    if not normalized:
        return ""

    normalized = re.sub(r"[\s.]+", "-", normalized)
    normalized = re.sub(r"[^a-z0-9-]+", "", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-")


def _real_model_label_map(real_model_labels: Iterable[str] | None) -> Dict[str, str]:
    label_map: Dict[str, str] = {}
    for raw_label in real_model_labels or ():
        label = str(raw_label or "").strip()
        base_id = normalize_real_model_api_base(label)
        if not label or not base_id:
            continue
        for suffix, _mode in REAL_MODEL_SUFFIX_MODE_BY_SUFFIX:
            label_map.setdefault(f"{base_id}{suffix}", label)
    return label_map


def _real_model_mode_map(real_model_labels: Iterable[str] | None) -> Dict[str, str]:
    mode_map: Dict[str, str] = {}
    for raw_label in real_model_labels or ():
        label = str(raw_label or "").strip()
        base_id = normalize_real_model_api_base(label)
        if not label or not base_id:
            continue
        for suffix, mode in REAL_MODEL_SUFFIX_MODE_BY_SUFFIX:
            mode_map.setdefault(f"{base_id}{suffix}", mode)
    return mode_map


def get_real_model_ids_for_labels(real_model_labels: Iterable[str] | None) -> list[str]:
    return list(_real_model_label_map(real_model_labels).keys())


def resolve_real_model_label_from_model_id(
    provider: DriverProvider,
    model: Any,
    real_model_labels: Iterable[str] | None,
) -> str | None:
    normalized = str(model or "").strip().lower()
    if not normalized or provider not in REAL_MODEL_ID_PROVIDERS:
        return None

    if provider == DriverProvider.AI_STUDIO:
        normalized = _strip_aistudio_override_suffix(normalized)

    return _real_model_label_map(real_model_labels).get(normalized)


def get_model_ids_for_provider(
    provider: DriverProvider,
    config_manager: Any,
    *,
    force_legacy: bool = False,
    real_model_labels: Iterable[str] | None = None,
) -> list[str]:
    if (not force_legacy) and is_umm_enabled(config_manager):
        model_ids = list(UMM_MODEL_IDS)
        if provider == DriverProvider.DEEPSEEK:
            model_ids.extend(DEEPSEEK_UMM_EXPERT_MODEL_IDS)
        if provider in REAL_MODEL_ID_PROVIDERS:
            model_ids.extend(get_real_model_ids_for_labels(real_model_labels))
        return model_ids
    return get_legacy_model_ids(provider)


def get_model_ids_for_providers(
    providers: Iterable[DriverProvider],
    config_manager: Any,
    *,
    force_legacy: bool = False,
    real_model_labels_by_provider: Mapping[DriverProvider, Iterable[str]] | None = None,
) -> list[tuple[DriverProvider, str]]:
    items: list[tuple[DriverProvider, str]] = []
    for provider in providers:
        real_model_labels = None
        if real_model_labels_by_provider:
            real_model_labels = real_model_labels_by_provider.get(provider)
        model_ids = get_model_ids_for_provider(
            provider,
            config_manager,
            force_legacy=force_legacy,
            real_model_labels=real_model_labels,
        )
        items.extend((provider, model_id) for model_id in model_ids)
    return items


def _strip_aistudio_override_suffix(model: str) -> str:
    normalized = str(model or "").strip().lower()
    return AISTUDIO_MODEL_OVERRIDE_SUFFIX_RE.sub("", normalized)


def is_supported_model_id(
    provider: DriverProvider,
    model: Any,
    config_manager: Any = None,
    *,
    real_model_labels: Iterable[str] | None = None,
) -> bool:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return False

    if is_umm_enabled(config_manager) and normalized in _get_universal_mode_map(provider):
        return True

    if is_umm_enabled(config_manager) and provider in REAL_MODEL_ID_PROVIDERS:
        real_normalized = normalized
        if provider == DriverProvider.AI_STUDIO:
            real_normalized = _strip_aistudio_override_suffix(real_normalized)
        if real_normalized in _real_model_mode_map(real_model_labels):
            return True

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


def resolve_behavior_mode(
    model: Any,
    provider: DriverProvider,
    *,
    real_model_labels: Iterable[str] | None = None,
) -> str:
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

    universal_mode = _get_universal_mode_map(provider).get(normalized)
    if universal_mode:
        return universal_mode

    real_normalized = normalized
    if provider == DriverProvider.AI_STUDIO:
        real_normalized = _strip_aistudio_override_suffix(real_normalized)
    real_model_mode = _real_model_mode_map(real_model_labels).get(real_normalized)
    if real_model_mode:
        return real_model_mode

    if provider == DriverProvider.AI_STUDIO:
        normalized = _strip_aistudio_override_suffix(normalized)

    legacy_map = LEGACY_MODE_BY_PROVIDER.get(provider) or {}
    legacy_mode = legacy_map.get(normalized)
    if legacy_mode:
        return legacy_mode

    return MODE_AUTO


def resolve_deepseek_model_type(model: Any, provider: DriverProvider) -> str:
    normalized = str(model or "").strip().lower()
    if provider != DriverProvider.DEEPSEEK or not normalized:
        return DEEPSEEK_MODEL_TYPE_DEFAULT

    if (
        normalized in DEEPSEEK_UMM_EXPERT_MODE_BY_MODEL_ID
        or normalized.startswith("deepseek-expert-")
    ):
        return DEEPSEEK_MODEL_TYPE_EXPERT

    return DEEPSEEK_MODEL_TYPE_DEFAULT


def build_openai_model_list(ids: Iterable[str], owned_by: str) -> List[Dict[str, Any]]:
    safe_owned = str(owned_by or "").strip() or "unknown"
    out: List[Dict[str, Any]] = []
    for mid in ids:
        sid = str(mid or "").strip()
        if not sid:
            continue
        out.append({"id": sid, "object": "model", "created": 0, "owned_by": safe_owned})
    return out
