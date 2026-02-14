from __future__ import annotations

import asyncio
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Union

from patchright.async_api import Browser, BrowserContext, Page, async_playwright

from drivers.providers import DriverProvider, get_playwright_profile_dir
from ece.manager import EceManager
from ece.models import CredentialPair
from utils.logger import Logger


class BaseDriver(ABC):
    def __init__(self, config_manager: Any, provider: DriverProvider):
        self.config_manager = config_manager
        self.provider = provider

        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

        self.is_running = False
        self.on_crash_callback = None
        self.monitoring_active = False
        self._monitor_task: Optional[asyncio.Task] = None
        self.notify_user_callback: Optional[Callable[[str, str, str], None]] = None

        # Abort handling (provider-specific use; common surface)
        self.current_abort_event: asyncio.Event | None = None
        self.abort_requested = False

        # Optional provider UI language detection (providers may opt in)
        self.last_document_lang: Optional[str] = None

        # ECE state (set during start(), used by login() and re-auth rotation)
        self._ece_manager: EceManager | None = None
        self._ece_active_pair: CredentialPair | None = None
        self._ece_active_profile_slot: int = 0
        self._ece_pending_pair: CredentialPair | None = None
        self._ece_pending_profile_slot: int | None = None

    def _ece_is_enabled(self) -> bool:
        try:
            return bool(self.config_manager.get_setting("experimental", "ece_enabled"))
        except Exception:
            return False

    def _ece_select_least_used(self) -> bool:
        try:
            return bool(self.config_manager.get_setting("experimental", "ece_select_least_used"))
        except Exception:
            return False

    def _ece_reauth_on_no_content(self) -> bool:
        try:
            return bool(self.config_manager.get_setting("experimental", "ece_reauth_on_no_content"))
        except Exception:
            return False

    def _ece_requires_auto_login(self) -> bool:
        """
        Whether this provider requires Auto Login to enable ECE account/profile selection.

        Default is True for providers where credentials are actively used in login flow.
        Providers with manual-only auth flows can override this to False.
        """
        return True

    def ece_reauth_enabled(self) -> bool:
        if (not self._ece_is_enabled()) or (not self._ece_reauth_on_no_content()):
            return False

        if not self._ece_requires_auto_login():
            return True

        try:
            return bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
        except Exception:
            return False

    def _get_ece_manager(self) -> EceManager:
        mgr = getattr(self, "_ece_manager", None)
        if mgr:
            return mgr
        config_dir = getattr(self.config_manager, "config_dir", None) or "config_data"
        mgr = EceManager(config_dir)
        self._ece_manager = mgr
        return mgr

    def _ece_prepare_for_start(self) -> None:
        """
        Prepare ECE selection state before launching the browser.

        This is called from start() so we can pick a profile directory (ECE uses its own
        profile base dir under playwright_profiles/ece).
        """
        if not self._ece_is_enabled():
            self._ece_active_pair = None
            self._ece_active_profile_slot = 0
            self._ece_pending_pair = None
            self._ece_pending_profile_slot = None
            return

        auto_login = False
        try:
            auto_login = bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
        except Exception:
            auto_login = False

        pending_pair = getattr(self, "_ece_pending_pair", None)
        pending_slot = getattr(self, "_ece_pending_profile_slot", None)
        if pending_pair is not None:
            self._ece_active_pair = pending_pair
            self._ece_active_profile_slot = int(pending_slot or 0)
            self._ece_pending_pair = None
            self._ece_pending_profile_slot = None
            return

        # Providers can require Auto Login for ECE selection. Some providers have to work manually though, so we
        # allow bypassing this requirement for them (right now Moonshot does this)
        if self._ece_requires_auto_login() and (not auto_login):
            self._ece_active_pair = None
            self._ece_active_profile_slot = 0
            return

        try:
            pair = self._get_ece_manager().select_pair(
                self.provider,
                least_used=self._ece_select_least_used(),
            )
        except Exception as exc:
            Logger.warning(f"ECE: failed to select credential pair: {exc}")
            pair = None

        self._ece_active_pair = pair
        self._ece_active_profile_slot = 0

    def ece_active_pair(self) -> CredentialPair | None:
        if not self._ece_is_enabled():
            return None
        return getattr(self, "_ece_active_pair", None)

    def ece_mark_used(self, email: str) -> None:
        if not self._ece_is_enabled():
            return
        if not email:
            return
        try:
            self._get_ece_manager().mark_used(self.provider, email)
        except Exception:
            return

    def _mark_active_ece_pair_used(self) -> None:
        """Mark the currently active ECE pair as used (timestamp update)."""
        pair = self.ece_active_pair()
        email = getattr(pair, "email", None) if pair else None
        if isinstance(email, str) and email.strip():
            self.ece_mark_used(email)

    def ece_rotate_identity(self, reason: str) -> bool:
        """
        Rotate to a different ECE identity (pair and/or profile slot) for this provider.

        Returns True if a different identity was selected and queued for next start.
        """
        if not self._ece_is_enabled():
            return False

        auto_login = False
        try:
            auto_login = bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
        except Exception:
            auto_login = False

        if self._ece_requires_auto_login() and (not auto_login):
            return False

        current = getattr(self, "_ece_active_pair", None)
        current_email = current.email if current else None

        next_pair = None
        try:
            next_pair = self._get_ece_manager().select_pair(
                self.provider,
                least_used=self._ece_select_least_used(),
                exclude_email=current_email,
            )
        except Exception:
            next_pair = None

        # Prefer switching accounts when possible
        if next_pair is not None:
            self._ece_pending_pair = next_pair
            self._ece_pending_profile_slot = 0
            Logger.warning(f"ECE: rotating credentials due to: {reason}")
            return True

        # Fallback: same account, new profile slot
        if current_email:
            try:
                new_slot = self._get_ece_manager().rotate_profile_slot(
                    self.provider,
                    current_email,
                    getattr(self, "_ece_active_profile_slot", 0),
                )
            except Exception:
                new_slot = int(getattr(self, "_ece_active_profile_slot", 0)) + 1

            self._ece_pending_pair = current
            self._ece_pending_profile_slot = int(new_slot)
            Logger.warning(f"ECE: rotating profile slot due to: {reason}")
            return True

        return False

    async def ece_restart_with_rotation(
        self, reason: str, status_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Rotate ECE identity (pair/profile) and restart the driver to re-auth.

        Returns True only when rotation succeeded and the driver restarted successfully.
        """
        if not self.ece_rotate_identity(reason):
            return False

        Logger.warning("ECE: restarting driver to re-auth with a different profile...")
        try:
            await self.close()
        except Exception as e:
            Logger.warning(f"ECE: driver close failed during restart: {e}")

        try:
            await self.start(status_callback=status_callback)
            return True
        except Exception as e:
            Logger.error(f"ECE: driver restart failed: {e}")
            return False

    def notify_user(self, title: str, message: str, level: str = "info") -> None:
        cb = getattr(self, "notify_user_callback", None)
        if not cb:
            return

        try:
            cb(str(title or ""), str(message or ""), str(level or "info"))
        except Exception:
            return

    def _notify_on_driver_crash_enabled(self) -> bool:
        try:
            return bool(self.config_manager.get_setting("system_settings", "notify_on_driver_crash"))
        except Exception:
            return True

    @property
    def provider_label(self) -> str:
        return self.provider.value

    @property
    def required_ui_language_label(self) -> str:
        """
        Human-friendly UI language requirement for providers that enforce one.

        Providers that do not enforce a specific UI language should simply leave
        the default `check_ui_language()` implementation in place.
        """
        return "English (en-US)"

    async def check_ui_language(
        self, status_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Optional UI language check.

        Default behavior is to opt out (returns True), since many providers either:
        - do not rely on visible UI text, or
        - do not allow changing UI language.
        """
        return True

    def _get_persistent_profile_dir(self) -> str:
        config_dir = getattr(self.config_manager, "config_dir", None)
        if self._ece_is_enabled():
            pair = getattr(self, "_ece_active_pair", None)
            slot = int(getattr(self, "_ece_active_profile_slot", 0))
            try:
                return str(self._get_ece_manager().get_profile_dir(self.provider, email=pair.email if pair else None, slot=slot))
            except Exception:
                pass
        return str(get_playwright_profile_dir(config_dir, self.provider))

    async def ensure_browser_installed(
        self, status_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Ensures the patchright chromium browser is installed.
        Returns True if installation was performed/verified, False if failed.
        """
        # Directly run the install/verify command to avoid issues where the dry-run check returns false negatives
        return await self._install_browser_via_cli(status_callback)

    async def _install_browser_via_cli(
        self, status_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Run the browser installation using the patchright CLI (async).
        """
        Logger.info("Verifying/Installing Chromium browser...")
        if status_callback:
            status_callback("Verifying Browser...")

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "patchright",
                "install",
                "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

            if process.returncode == 0:
                Logger.success("Chromium browser verified/installed.")
                return True

            error_msg = (
                (stderr.decode() if stderr else "")
                or (stdout.decode() if stdout else "")
                or "Unknown error"
            )
            Logger.error(f"Failed to install Chromium browser: {error_msg}")
            raise RuntimeError(f"Failed to install Chromium browser: {error_msg}")

        except asyncio.TimeoutError:
            Logger.error("Browser installation timed out.")
            raise RuntimeError("Browser installation timed out after 5 minutes.")
        except Exception as e:
            Logger.error(f"Browser installation failed: {e}")
            raise RuntimeError(f"Browser installation failed: {e}")

    def request_abort(self) -> None:
        """
        Best-effort, non-blocking request to abort the current generation.

        Providers may additionally click a "Stop" button or cancel streams; this method
        is intentionally lightweight for use from disconnect/cancellation paths.
        """
        self.abort_requested = True
        abort_event = getattr(self, "current_abort_event", None)
        if abort_event:
            try:
                abort_event.set()
            except Exception:
                pass

    @abstractmethod
    def get_start_url(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def login(self) -> None:
        raise NotImplementedError

    async def after_start(
        self, status_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        return None

    async def apply_configured_model(self) -> None:
        """
        Optional hook: make sure the provider's *real* model selection is applied.

        Notes:
        - This is intentionally separate from the OpenAI-compatible request `model` field,
          which IntenseRP uses as a behavior preset (mode) selector.
        (NOTE FOR SELF: Might want to make the request `model` field configurable.)
        - Providers without a model selector can keep the default no-op implementation.
        """
        return None

    async def _navigate_to_start_url(self, start_url: str) -> None:
        """
        Navigate to provider start URL with tolerant readiness rules.

        Some provider pages keep the tab spinner active indefinitely due to long-lived
        network connections. Waiting for full `load` can timeout despite a usable UI.
        """
        if not self.page:
            raise RuntimeError("Page is not initialized.")

        nav_timeout_ms = 45000

        try:
            await self.page.goto(
                start_url,
                wait_until="domcontentloaded",
                timeout=nav_timeout_ms,
            )
            return
        except Exception as e:
            msg = str(e)
            is_timeout = ("timeout" in msg.lower())
            if not is_timeout:
                raise

            Logger.warning(
                f"Navigation to {start_url} timed out waiting for DOM content "
                f"({nav_timeout_ms}ms). Checking page usability..."
            )

            # Best-effort fallback: continue if page is clearly usable
            current_url = ""
            try:
                current_url = str(self.page.url or "")
            except Exception:
                current_url = ""

            ready_state = ""
            try:
                ready_state = str(await self.page.evaluate("() => document.readyState || ''"))
            except Exception:
                ready_state = ""

            body_present = False
            try:
                body_present = bool(await self.page.evaluate("() => !!document.body"))
            except Exception:
                body_present = False

            looks_usable = (
                bool(current_url)
                and (current_url != "about:blank")
                and body_present
                and (ready_state in {"interactive", "complete"})
            )
            if looks_usable:
                Logger.warning(
                    f"Proceeding after navigation timeout because page appears usable "
                    f"(url='{current_url}', readyState='{ready_state}')."
                )
                return

            raise

    async def start(self, status_callback: Optional[Callable[[str], None]] = None) -> None:
        """
        Starts the browser and navigates to the provider.

        Args:
            status_callback: Optional callback to report status updates (e.g., for UI updates)
        """
        Logger.info(f"Starting {self.provider_label} Driver...")

        self._ece_prepare_for_start()

        await self.ensure_browser_installed(status_callback)

        if status_callback:
            status_callback("Launching Browser...")

        self.playwright = await async_playwright().start()
        persistent_sessions = bool(
            self.config_manager.get_setting("system_settings", "persistent_sessions")
        )

        if persistent_sessions:
            user_data_dir = self._get_persistent_profile_dir()
            Logger.info("Launching Chromium (Persistent Sessions enabled)...")
            Logger.debug(f"Persistent profile dir: {user_data_dir}")

            try:
                import os

                os.makedirs(user_data_dir, exist_ok=True)
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir, headless=False
                )
                context_browser = getattr(self.context, "browser", None)
                self.browser = context_browser() if callable(context_browser) else context_browser
            except Exception as e:
                Logger.error(f"Failed to launch persistent context: {e}")
                Logger.warning("Falling back to non-persistent session...")
                self.browser = await self.playwright.chromium.launch(headless=False)
                self.context = await self.browser.new_context()
        else:
            Logger.info("Launching Chromium...")
            self.browser = await self.playwright.chromium.launch(headless=False)
            self.context = await self.browser.new_context()

        # Create or reuse a page
        try:
            pages = getattr(self.context, "pages", [])
            self.page = pages[0] if pages else await self.context.new_page()
        except Exception:
            self.page = await self.context.new_page()

        start_url = self.get_start_url()
        Logger.info(f"Navigating to {start_url} ...")
        await self._navigate_to_start_url(start_url)

        await self.login()
        await self.after_start(status_callback=status_callback)

        self.is_running = True
        Logger.success(f"{self.provider_label} Driver started successfully.")

        self.monitoring_active = True
        self._monitor_task = asyncio.create_task(self._monitor_browser_loop())

    async def close(self) -> None:
        """
        Closes the browser and playwright.
        """
        Logger.info(f"Closing {self.provider_label} Driver...")
        self.monitoring_active = False
        monitor_task = getattr(self, "_monitor_task", None)
        if monitor_task and (not monitor_task.done()):
            current_task = asyncio.current_task()
            if monitor_task is current_task:
                # Avoid self-cancel / self-await when close() is invoked from the monitor task.
                # The loop will exit naturally because monitoring_active is already False.
                pass
            else:
                try:
                    monitor_task.cancel()
                    done, pending = await asyncio.wait({monitor_task}, timeout=2.0)
                    if pending:
                        Logger.warning("Timeout while stopping monitor task.")
                    if done:
                        try:
                            monitor_task.exception()
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    Logger.debug(f"Error stopping monitor task: {e}")
        self._monitor_task = None

        async def _await_with_timeout(coro, timeout_s: float, label: str) -> None:
            try:
                task = asyncio.create_task(coro)
            except Exception as e:
                Logger.debug(f"Error while creating task for {label}: {e}")
                return

            try:
                done, pending = await asyncio.wait({task}, timeout=timeout_s)
                if pending:
                    Logger.warning(f"Timeout while {label}.")
                    task.cancel()
                    await asyncio.wait({task}, timeout=1.0)
                    return

                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    Logger.debug(f"Error while {label}: {e}")
            except asyncio.CancelledError:
                # Best-effort cleanup should not prevent outer cancellation.
                task.cancel()
                raise

        if self.context:
            try:
                await _await_with_timeout(self.context.close(), 10.0, "closing browser context")
            except Exception as e:
                Logger.debug(f"Error closing browser context: {e}")
        if self.browser:
            try:
                await _await_with_timeout(self.browser.close(), 10.0, "closing browser")
            except Exception as e:
                Logger.debug(f"Error closing browser: {e}")
        if self.playwright:
            try:
                await _await_with_timeout(self.playwright.stop(), 10.0, "stopping Playwright")
            except Exception as e:
                Logger.debug(f"Error stopping Playwright: {e}")

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

        self.is_running = False
        Logger.info(f"{self.provider_label} Driver closed.")

    async def _monitor_browser_loop(self) -> None:
        """
        Periodically checks if the browser is still open.
        """
        Logger.debug("Starting browser monitoring loop...")
        while self.monitoring_active:
            try:
                browser = getattr(self, "browser", None)
                if not browser or not browser.is_connected():
                    Logger.warning("Browser disconnected!")
                    await self._handle_crash()
                    break

                page = getattr(self, "page", None)
                if not page or page.is_closed():
                    Logger.warning("Page closed!")
                    await self._handle_crash()
                    break

                context = getattr(self, "context", None)
                if not context or len(context.pages) == 0:
                    Logger.warning("Context has no pages or is closed!")
                    await self._handle_crash()
                    break

            except Exception as e:
                Logger.debug(f"Error in monitoring loop: {e}")

            await asyncio.sleep(2.0)

    async def _handle_crash(self) -> None:
        """
        Handles the crash event.
        """
        if not self.monitoring_active:
            return

        Logger.warning("Browser crash detected!")
        self.is_running = False
        self.monitoring_active = False

        if self._notify_on_driver_crash_enabled():
            self.notify_user(
                f"{self.provider_label} Driver",
                "Browser was closed or crashed. Click Start to relaunch the driver.",
                level="warning",
            )

        callback = getattr(self, "on_crash_callback", None)
        if not callback:
            return

        if asyncio.iscoroutinefunction(callback):
            await callback()
            return

        callback()

    # Common provider actions (vague hooks)
    async def open_sidebar(self) -> None:
        await self.set_sidebar_status(open=True)

    async def close_sidebar(self) -> None:
        await self.set_sidebar_status(open=False)

    async def create_new_chat(self) -> None:
        await self.click_new_chat(source="auto")

    async def paste_text(self, text: str) -> None:
        await self.enter_message(text)

    @abstractmethod
    async def set_sidebar_status(self, open: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    async def click_new_chat(self, source: str = "auto") -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_deepthink_state(self, state: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_search_state(self, state: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    async def upload_file(self, file_spec: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    async def enter_message(self, message: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_message(self, timeout: int | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def generate_response(
        self,
        message: Union[str, List[Any]],
        model: str = "",
        stream: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        abort_event: asyncio.Event | None = None,
    ):
        raise NotImplementedError
