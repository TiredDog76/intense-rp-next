from __future__ import annotations

from typing import Any

from aistudio_driver import AIStudioDriver
from deepseek_driver import DeepSeekDriver
from glm_driver import GLMDriver
from moonshot_driver import MoonshotDriver
from qwen_driver import QwenLMDriver
from drivers.base_driver import BaseDriver
from drivers.providers import DriverProvider
from utils.logger import Logger


def create_driver(config_manager: Any) -> BaseDriver:
    provider_setting = None
    try:
        provider_setting = config_manager.get_setting("providers_credentials", "provider")
    except Exception:
        provider_setting = None

    provider = DriverProvider.from_setting(provider_setting)
    if provider is None:
        Logger.warning(f"Unknown driver provider '{provider_setting}', falling back to DeepSeek.")
        provider = DriverProvider.DEEPSEEK

    Logger.info(f"Selected driver provider: {provider.value}")

    if provider == DriverProvider.DEEPSEEK:
        return DeepSeekDriver(config_manager)
    if provider == DriverProvider.GLM_CHAT:
        return GLMDriver(config_manager)
    if provider == DriverProvider.MOONSHOT:
        return MoonshotDriver(config_manager)
    if provider == DriverProvider.QWEN_LM:
        return QwenLMDriver(config_manager)
    if provider == DriverProvider.AI_STUDIO:
        return AIStudioDriver(config_manager)

    return DeepSeekDriver(config_manager)
