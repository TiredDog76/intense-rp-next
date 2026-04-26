from __future__ import annotations

from typing import Any

from drivers.providers import DriverProvider


PARALLEL_PROVIDER_FIELD_BY_PROVIDER: dict[DriverProvider, str] = {
    DriverProvider.DEEPSEEK: "parallel_enable_deepseek",
    DriverProvider.GLM_CHAT: "parallel_enable_glm",
    DriverProvider.MOONSHOT: "parallel_enable_moonshot",
    DriverProvider.QWEN_LM: "parallel_enable_qwen",
    DriverProvider.PERPLEXITY: "parallel_enable_perplexity",
    DriverProvider.AI_STUDIO: "parallel_enable_aistudio",
}


def get_current_provider(config_manager: Any) -> DriverProvider:
    try:
        provider_setting = config_manager.get_setting("providers_credentials", "provider")
    except Exception:
        provider_setting = None

    provider = DriverProvider.from_setting(provider_setting)
    return provider if provider is not None else DriverProvider.DEEPSEEK


def is_parallel_feature_enabled(config_manager: Any) -> bool:
    try:
        return bool(config_manager.get_setting("experimental", "providers_in_parallel"))
    except Exception:
        return False


def is_parallel_request_queue_feature_enabled(config_manager: Any) -> bool:
    try:
        return bool(config_manager.get_setting("experimental", "parallelize_request_queue"))
    except Exception:
        return False


def get_parallel_selected_providers(config_manager: Any) -> list[DriverProvider]:
    current_provider = get_current_provider(config_manager)
    selected: list[DriverProvider] = [current_provider]

    for provider in DriverProvider:
        if provider == current_provider:
            continue

        field_key = PARALLEL_PROVIDER_FIELD_BY_PROVIDER.get(provider)
        if not field_key:
            continue

        try:
            enabled = bool(config_manager.get_setting("experimental", field_key))
        except Exception:
            enabled = False

        if enabled:
            selected.append(provider)

    return selected


def is_parallel_runtime_active(config_manager: Any) -> bool:
    return is_parallel_feature_enabled(config_manager) and (len(get_parallel_selected_providers(config_manager)) >= 2)


def is_parallel_request_queue_active(config_manager: Any) -> bool:
    return is_parallel_runtime_active(config_manager) and is_parallel_request_queue_feature_enabled(
        config_manager
    )
