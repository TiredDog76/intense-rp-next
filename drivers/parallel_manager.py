from __future__ import annotations

import inspect
from typing import Any

from drivers.base_driver import BaseDriver
from drivers.factory import create_driver_for_provider
from drivers.providers import DriverProvider
from utils.logger import Logger
from utils.providers_in_parallel import get_current_provider, get_parallel_selected_providers


class ParallelDriversManager:
    def __init__(self, config_manager: Any):
        self.config_manager = config_manager
        self.current_provider = get_current_provider(config_manager)
        self.providers = get_parallel_selected_providers(config_manager)
        self.drivers: dict[DriverProvider, BaseDriver] = {
            provider: create_driver_for_provider(config_manager, provider) for provider in self.providers
        }

        self.is_running = False
        self.notify_user_callback = None
        self.request_user_text_callback = None
        self.on_crash_callback = None
        self._crash_notified = False

    @property
    def provider(self) -> DriverProvider:
        return self.current_provider

    @property
    def provider_label(self) -> str:
        return "Providers in Parallel"

    def iter_drivers(self) -> list[tuple[DriverProvider, BaseDriver]]:
        return list(self.drivers.items())

    def get_driver(self, provider: DriverProvider) -> BaseDriver | None:
        return self.drivers.get(provider)

    def get_current_driver(self) -> BaseDriver | None:
        return self.get_driver(self.current_provider)

    def _attach_callbacks(self) -> None:
        for provider, driver in self.drivers.items():
            driver.notify_user_callback = self.notify_user_callback
            driver.request_user_text_callback = self.request_user_text_callback

            async def _handle_provider_crash(current_provider: DriverProvider = provider) -> None:
                await self._handle_driver_crash(current_provider)

            driver.on_crash_callback = _handle_provider_crash

    async def _handle_driver_crash(self, provider: DriverProvider) -> None:
        if self._crash_notified or (not self.is_running):
            return

        self._crash_notified = True
        Logger.warning(
            f"Providers in Parallel: {provider.value} browser crashed or was closed. Stopping all providers."
        )

        callback = getattr(self, "on_crash_callback", None)
        if not callback:
            return

        if inspect.iscoroutinefunction(callback):
            await callback()
            return

        callback()

    async def start(self, status_callback=None) -> None:
        self.current_provider = get_current_provider(self.config_manager)
        self._crash_notified = False
        self._attach_callbacks()

        providers_text = ", ".join(provider.value for provider in self.providers)
        Logger.info(f"Starting Providers in Parallel runtime for: {providers_text}")

        try:
            for provider in self.providers:
                driver = self.drivers[provider]
                driver_status_callback = None
                if status_callback is not None:
                    driver_status_callback = (
                        lambda message, current_provider=provider: status_callback(
                            f"{current_provider.value}: {message}"
                        )
                    )
                await driver.start(status_callback=driver_status_callback)
            self.is_running = True
            Logger.success("Providers in Parallel runtime started successfully.")
        except Exception:
            Logger.warning("Providers in Parallel runtime failed during startup. Cleaning up...")
            try:
                await self.close()
            except Exception as close_error:
                Logger.debug(f"Providers in Parallel cleanup after failed startup raised: {close_error}")
            raise

    async def close(self) -> None:
        Logger.info("Closing Providers in Parallel runtime...")
        self.is_running = False
        self._crash_notified = True

        for provider, driver in reversed(self.iter_drivers()):
            try:
                await driver.close()
            except Exception as exc:
                Logger.warning(f"Providers in Parallel: failed to close {provider.value}: {exc}")

        Logger.info("Providers in Parallel runtime closed.")
