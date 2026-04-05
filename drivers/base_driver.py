from __future__ import annotations

import asyncio
import json
import secrets
import string
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

from patchright.async_api import Browser, BrowserContext, Page, async_playwright

from drivers.providers import DriverProvider, get_playwright_profile_dir
from ece.manager import EceManager
from ece.models import CredentialPair
from utils.browser_manager import install_chromium_browser, probe_browser_executable_path
from utils.logger import Logger


class BaseDriver(ABC):
    _browser_install_verified: bool = False
    _browser_install_lock: asyncio.Lock | None = None
    _browser_executable_path: str | None = None

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
        self._send_control_signature: str | None = None

        # Optional provider UI language detection (providers may opt in)
        self.last_document_lang: Optional[str] = None

        # Account selection state (set during start(), used by login() and re-auth rotation)
        self._ece_manager: EceManager | None = None
        self._ece_active_pair: CredentialPair | None = None
        self._ece_active_pair_is_pinned: bool = False
        self._ece_active_profile_slot: int = 0
        self._ece_pending_pair: CredentialPair | None = None
        self._ece_pending_profile_slot: int | None = None

    def _ece_select_least_used(self) -> bool:
        try:
            return bool(self.config_manager.get_setting("providers_credentials", "select_least_used"))
        except Exception:
            return False

    def _ece_reauth_on_no_content(self) -> bool:
        try:
            return bool(self.config_manager.get_setting("providers_credentials", "reload_on_failure"))
        except Exception:
            return False

    async def _get_context_cookie_dict(self) -> dict[str, str]:
        """Return the current browser-context cookies as a simple name/value mapping."""
        context = getattr(self, "context", None)
        if context is None:
            return {}

        try:
            cookies = await context.cookies()
        except Exception:
            return {}

        cookie_dict: dict[str, str] = {}
        for cookie in cookies or []:
            try:
                name = str(cookie.get("name") or "").strip()
                value = str(cookie.get("value") or "")
            except Exception:
                continue
            if name:
                cookie_dict[name] = value
        return cookie_dict

    async def _run_browser_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
        use_xhr: bool = False,
        referrer: str | None = None,
        timeout_ms: int = 15000,
    ) -> dict[str, Any]:
        """Run a same-session browser request from the active page.

        This is handy for provider follow-up actions like chat cleanup, where the
        provider expects the currently authenticated browser session and cookies.
        """
        if self.page is None:
            return {"ok": False, "status": 0, "error": "Browser page is not available."}

        payload = {
            "method": str(method or "GET").strip().upper() or "GET",
            "url": str(url or "").strip(),
            "headers": dict(headers or {}),
            "body": body,
            "has_body": body is not None,
            "use_xhr": bool(use_xhr),
            "referrer": str(referrer or "").strip() or None,
            "timeout_ms": max(int(timeout_ms or 0), 1000),
        }
        return await self.page.evaluate(
            """async (args) => {
                const normalizeText = async (resp) => {
                    try {
                        return await resp.text();
                    } catch (e) {
                        return "";
                    }
                };

                const buildBodyText = () => {
                    if (!args.has_body) {
                        return undefined;
                    }
                    return (typeof args.body === "string") ? args.body : JSON.stringify(args.body);
                };

                const ensureContentType = (headers) => {
                    if (!args.has_body) {
                        return headers;
                    }
                    const hasContentType = Object.keys(headers).some(
                        (key) => String(key || "").toLowerCase() === "content-type"
                    );
                    if (!hasContentType) {
                        headers["content-type"] = "application/json";
                    }
                    return headers;
                };

                if (!args.url) {
                    return { ok: false, status: 0, error: "Missing URL." };
                }

                const requestHeaders = ensureContentType({ ...(args.headers || {}) });
                const bodyText = buildBodyText();

                if (args.use_xhr) {
                    return await new Promise((resolve) => {
                        try {
                            const xhr = new XMLHttpRequest();
                            xhr.open(args.method || "GET", args.url, true);
                            xhr.withCredentials = true;
                            xhr.timeout = args.timeout_ms || 15000;

                            Object.entries(requestHeaders).forEach(([key, value]) => {
                                if (value === undefined || value === null || value === "") {
                                    return;
                                }
                                xhr.setRequestHeader(key, String(value));
                            });

                            xhr.onreadystatechange = () => {
                                if (xhr.readyState !== XMLHttpRequest.DONE) {
                                    return;
                                }
                                resolve({
                                    ok: xhr.status >= 200 && xhr.status < 300,
                                    status: xhr.status || 0,
                                    text: xhr.responseText || "",
                                });
                            };
                            xhr.onerror = () => resolve({
                                ok: false,
                                status: xhr.status || 0,
                                text: xhr.responseText || "",
                                error: "XMLHttpRequest failed.",
                            });
                            xhr.ontimeout = () => resolve({
                                ok: false,
                                status: xhr.status || 0,
                                text: xhr.responseText || "",
                                error: "XMLHttpRequest timed out.",
                            });
                            xhr.send(bodyText ?? null);
                        } catch (error) {
                            resolve({ ok: false, status: 0, error: String(error) });
                        }
                    });
                }

                try {
                    const response = await fetch(args.url, {
                        method: args.method || "GET",
                        credentials: "include",
                        headers: requestHeaders,
                        referrer: args.referrer || undefined,
                        body: bodyText,
                    });
                    return {
                        ok: !!response.ok,
                        status: response.status || 0,
                        text: await normalizeText(response),
                    };
                } catch (error) {
                    return { ok: false, status: 0, error: String(error) };
                }
            }""",
            payload,
        )

    def _ece_requires_auto_login(self) -> bool:
        """
        Whether this provider requires Auto Login to enable account/profile selection.

        Default is True for providers where credentials are actively used in login flow.
        Providers with manual-only auth flows can override this to False.
        """
        return True

    def ece_reauth_enabled(self) -> bool:
        if not self._ece_reauth_on_no_content():
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

    def _ece_is_pair_pinned(self, pair: CredentialPair | None) -> bool:
        email = str(getattr(pair, "email", "") or "").strip()
        if not email:
            return False

        try:
            return self._get_ece_manager().is_email_pinned(self.provider, email)
        except Exception:
            return False

    def _log_selected_startup_profile(self) -> None:
        pair = self.ece_active_pair()
        profile_label = str(getattr(pair, "email", "") or "").strip() or "manual"
        slot = int(getattr(self, "_ece_active_profile_slot", 0))
        if slot > 0:
            profile_label = f"{profile_label} (slot {slot})"
        if getattr(self, "_ece_active_pair_is_pinned", False):
            profile_label = f"{profile_label} [PINNED]"
        Logger.info(f"{self.provider_label}: startup profile -> {profile_label}")

    def _ece_prepare_for_start(self) -> None:
        """
        Prepare account selection state before launching the browser.

        This is called from start() so we can pick a profile directory (accounts use their own
        profile base dir under playwright_profiles/accounts).
        """
        auto_login = False
        try:
            auto_login = bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
        except Exception:
            auto_login = False

        pending_pair = getattr(self, "_ece_pending_pair", None)
        pending_slot = getattr(self, "_ece_pending_profile_slot", None)
        if pending_pair is not None:
            self._ece_active_pair = pending_pair
            self._ece_active_pair_is_pinned = self._ece_is_pair_pinned(pending_pair)
            self._ece_active_profile_slot = int(pending_slot or 0)
            self._ece_pending_pair = None
            self._ece_pending_profile_slot = None
            return

        # Providers can require Auto Login for account selection. Some providers may still support manual-only auth
        # flows, so we allow bypassing this requirement for them when needed
        if self._ece_requires_auto_login() and (not auto_login):
            self._ece_active_pair = None
            self._ece_active_pair_is_pinned = False
            self._ece_active_profile_slot = 0
            return

        try:
            pair = self._get_ece_manager().select_pair(
                self.provider,
                least_used=self._ece_select_least_used(),
                prefer_pinned=True,
            )
        except Exception as exc:
            Logger.warning(f"Account selection: failed to select account: {exc}")
            pair = None

        self._ece_active_pair = pair
        self._ece_active_pair_is_pinned = self._ece_is_pair_pinned(pair)
        self._ece_active_profile_slot = 0

    def ece_active_pair(self) -> CredentialPair | None:
        return getattr(self, "_ece_active_pair", None)

    def _get_multi_slot_cache_account_key(self) -> str:
        """
        Return a stable account bucket for provider-scoped multi-slot cache entries.

        Prefer the selected Credential Manager email when available. When the active
        account is unknown (for example manual-login flows), fall back to the active
        browser profile path so different provider profiles do not share chat IDs.
        """
        pair = self.ece_active_pair()
        email = str(getattr(pair, "email", "") or "").strip().lower()
        if email:
            return f"email:{email}"

        try:
            profile_dir = Path(self._get_persistent_profile_dir()).resolve()
            profile_text = profile_dir.as_posix().strip()
            if profile_text:
                return f"profile:{profile_text}"
        except Exception:
            pass

        return "profile:default"

    def _read_cached_prompt(self, cache_manager: Any, cache_key: str) -> str | None:
        """Read the last cached prompt used for duplicate-prompt heuristics."""
        if cache_manager is None:
            return None

        try:
            cached_prompt = cache_manager.read_cache(cache_key)
        except Exception:
            return None

        if cached_prompt is None:
            return None

        return str(cached_prompt)

    def _write_cached_prompt(self, cache_manager: Any, cache_key: str, prompt: str) -> None:
        """Persist the latest prompt text for provider-side duplicate checks."""
        if cache_manager is None:
            return

        try:
            cache_manager.write_cache(cache_key, str(prompt))
        except Exception:
            return

    def _cached_prompt_matches(self, cache_manager: Any, cache_key: str, prompt: str) -> bool:
        """Return True when the provided prompt matches the last cached prompt."""
        return self._read_cached_prompt(cache_manager, cache_key) == str(prompt)

    def _read_account_scoped_prompt_cache(self, cache_manager: Any, cache_key: str) -> dict[str, str]:
        """Load a simple account/profile -> prompt cache payload."""
        if cache_manager is None:
            return {}

        try:
            raw_payload = cache_manager.read_cache(cache_key)
        except Exception:
            return {}

        if raw_payload is None:
            return {}

        try:
            parsed = json.loads(raw_payload)
        except Exception:
            return {}

        if not isinstance(parsed, dict):
            return {}

        raw_accounts = parsed.get("accounts")
        if not isinstance(raw_accounts, dict):
            return {}

        normalized: dict[str, str] = {}
        for raw_account_key, raw_prompt in raw_accounts.items():
            account_key = str(raw_account_key or "").strip()
            if not account_key or not isinstance(raw_prompt, str):
                continue
            normalized[account_key] = raw_prompt

        return normalized

    def _read_account_scoped_cached_prompt(
        self,
        cache_manager: Any,
        cache_key: str,
        *,
        account_key: str | None = None,
    ) -> str | None:
        """Read the cached prompt for the active account/profile bucket."""
        normalized_account_key = str(account_key or self._get_multi_slot_cache_account_key() or "").strip()
        if not normalized_account_key:
            return None

        return self._read_account_scoped_prompt_cache(cache_manager, cache_key).get(normalized_account_key)

    def _write_account_scoped_cached_prompt(
        self,
        cache_manager: Any,
        cache_key: str,
        prompt: str,
        *,
        account_key: str | None = None,
    ) -> None:
        """Persist the latest prompt for the active account/profile bucket."""
        if cache_manager is None:
            return

        normalized_account_key = str(account_key or self._get_multi_slot_cache_account_key() or "").strip()
        if not normalized_account_key:
            return

        payload = {
            "version": 1,
            "accounts": self._read_account_scoped_prompt_cache(cache_manager, cache_key),
        }
        payload["accounts"][normalized_account_key] = str(prompt)

        try:
            cache_manager.write_cache(
                cache_key,
                json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
            )
        except Exception:
            return

    def _account_scoped_cached_prompt_matches(
        self,
        cache_manager: Any,
        cache_key: str,
        prompt: str,
        *,
        account_key: str | None = None,
    ) -> bool:
        """Return True when the provided prompt matches the active account/profile cache."""
        return self._read_account_scoped_cached_prompt(
            cache_manager,
            cache_key,
            account_key=account_key,
        ) == str(prompt)

    @staticmethod
    def _generate_repetition_buster_text(length: int = 128) -> str:
        """Generate a plain-ASCII cache-buster string for repetition-buster flows."""
        try:
            size = max(int(length), 1)
        except Exception:
            size = 128

        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(size))

    def ece_mark_used(self, email: str) -> None:
        if not email:
            return
        try:
            self._get_ece_manager().mark_used(self.provider, email)
        except Exception:
            return

    def _mark_active_ece_pair_used(self) -> None:
        """Mark the currently active account as used (timestamp update)."""
        pair = self.ece_active_pair()
        email = getattr(pair, "email", None) if pair else None
        if isinstance(email, str) and email.strip():
            self.ece_mark_used(email)

    def ece_rotate_identity(self, reason: str) -> bool:
        """
        Rotate to a different identity (account and/or profile slot) for this provider.

        Returns True if a different identity was selected and queued for next start.
        """
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
            Logger.warning(f"Account rotation: switching accounts due to: {reason}")
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
            Logger.warning(f"Account rotation: switching profile slot due to: {reason}")
            return True

        return False

    async def ece_restart_with_rotation(
        self, reason: str, status_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Rotate identity (account/profile) and restart the driver to re-auth.

        Returns True only when rotation succeeded and the driver restarted successfully.
        """
        prepare_loadouts = getattr(self.config_manager, "prepare_runtime_loadouts", None)
        if callable(prepare_loadouts):
            try:
                prepare_loadouts(required_providers=[self.provider])
            except Exception as exc:
                Logger.error(f"Account rotation: loadouts validation failed: {exc}")
                return False

        if not self.ece_rotate_identity(reason):
            return False

        Logger.warning("Account rotation: restarting driver to re-auth with a different profile...")
        try:
            await self.close()
        except Exception as e:
            Logger.warning(f"Account rotation: driver close failed during restart: {e}")

        try:
            await self.start(status_callback=status_callback)
            return True
        except Exception as e:
            Logger.error(f"Account rotation: driver restart failed: {e}")
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
        pair = getattr(self, "_ece_active_pair", None)
        slot = int(getattr(self, "_ece_active_profile_slot", 0))
        try:
            return str(
                self._get_ece_manager().get_profile_dir(
                    self.provider, email=pair.email if pair else None, slot=slot
                )
            )
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
        cached_path = BaseDriver._browser_executable_path
        if BaseDriver._browser_install_verified and cached_path and Path(cached_path).exists():
            return True

        lock = self._get_browser_install_lock()
        async with lock:
            cached_path = BaseDriver._browser_executable_path
            if BaseDriver._browser_install_verified and cached_path and Path(cached_path).exists():
                return True

            if await self._has_installed_browser():
                BaseDriver._browser_install_verified = True
                Logger.debug("Chromium browser already installed. Skipping patchright install.")
                return True

            installed = await self._install_browser_via_cli(status_callback)
            BaseDriver._browser_install_verified = bool(installed)
            if installed:
                await self._has_installed_browser()
            return installed

    @classmethod
    def _get_browser_install_lock(cls) -> asyncio.Lock:
        lock = BaseDriver._browser_install_lock
        if lock is None:
            lock = asyncio.Lock()
            BaseDriver._browser_install_lock = lock
        return lock

    async def _has_installed_browser(self) -> bool:
        cached_path = BaseDriver._browser_executable_path
        if cached_path and Path(cached_path).exists():
            return True

        browser_path = await probe_browser_executable_path()
        BaseDriver._browser_executable_path = browser_path or None
        return bool(browser_path)

    async def _install_browser_via_cli(
        self, status_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Run the browser installation using the patchright CLI (async).
        """
        try:
            await install_chromium_browser(status_callback=status_callback)
            return True
        except Exception:
            raise

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

    async def _iterate_response_queue(
        self,
        response_queue: asyncio.Queue,
        *,
        abort_event: asyncio.Event | None = None,
        first_chunk_timeout_s: float | None = None,
        idle_timeout_s: float | None = None,
        on_timeout: Callable[[], Any] | None = None,
        activity_counter: Callable[[], int] | None = None,
    ):
        """
        Yield provider stream items while guarding against silently stalled streams.

        The drivers all use an internal queue between the intercepted provider request
        and the async generator returned to the API layer. If the provider starts the
        request but never produces a first chunk (or stops producing follow-up chunks),
        waiting forever feels like client-side buffering. This helper surfaces a clear
        error instead and lets providers perform a best-effort UI stop action.
        """
        received_stream_item = False
        provider_activity_seen = False
        loop = asyncio.get_running_loop()
        last_activity_count: int | None = None
        if callable(activity_counter):
            try:
                last_activity_count = max(0, int(activity_counter()))
                provider_activity_seen = last_activity_count > 0
            except Exception:
                last_activity_count = None

        while True:
            if self.abort_requested or (abort_event and abort_event.is_set()):
                Logger.debug(f"Abort detected in {self.provider_label} response loop, breaking...")
                break

            wait_timeout_s = idle_timeout_s if (received_stream_item or provider_activity_seen) else first_chunk_timeout_s
            if wait_timeout_s and wait_timeout_s > 0:
                deadline = loop.time() + wait_timeout_s
                while True:
                    timeout_left = deadline - loop.time()
                    if timeout_left <= 0:
                        wait_phase = (
                            "intercepted first chunk" if not received_stream_item else "next stream chunk"
                        )
                        Logger.error(
                            f"{self.provider_label}: timed out waiting for {wait_phase} "
                            f"({wait_timeout_s:.0f}s)."
                        )
                        self.abort_requested = True
                        if callable(on_timeout):
                            try:
                                timeout_result = on_timeout()
                                if asyncio.iscoroutine(timeout_result):
                                    await timeout_result
                            except Exception as exc:
                                Logger.debug(f"{self.provider_label}: timeout handler failed: {exc}")
                        yield {
                            "error": (
                                f"{self.provider_label} timeout: no {wait_phase} "
                                f"within {wait_timeout_s:.0f}s."
                            )
                        }
                        return

                    try:
                        item = await asyncio.wait_for(
                            response_queue.get(),
                            timeout=min(timeout_left, 0.5),
                        )
                        break
                    except asyncio.TimeoutError:
                        if callable(activity_counter):
                            try:
                                current_activity_count = max(0, int(activity_counter()))
                            except Exception:
                                current_activity_count = last_activity_count
                            if (
                                current_activity_count is not None
                                and current_activity_count != last_activity_count
                            ):
                                last_activity_count = current_activity_count
                                provider_activity_seen = True
                                next_timeout_s = idle_timeout_s if idle_timeout_s and idle_timeout_s > 0 else wait_timeout_s
                                wait_timeout_s = next_timeout_s
                                deadline = loop.time() + next_timeout_s
                        if self.abort_requested or (abort_event and abort_event.is_set()):
                            Logger.debug(
                                f"Abort detected in {self.provider_label} response loop while waiting for queue data."
                            )
                            return
            else:
                item = await response_queue.get()

            if item is None:
                break

            received_stream_item = True
            yield item

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

    async def before_initial_navigation(self) -> None:
        """
        Optional hook: register routes/listeners before the first page navigation.

        This is useful for providers that need to observe startup requests that fire
        immediately when the landing page opens.
        """
        return None

    async def cleanup_background_tasks(self) -> None:
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
        self._log_selected_startup_profile()

        await self.ensure_browser_installed(status_callback)

        if status_callback:
            status_callback("Launching Browser...")

        try:
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

            try:
                pages = getattr(self.context, "pages", [])
                self.page = pages[0] if pages else await self.context.new_page()
            except Exception:
                self.page = await self.context.new_page()

            await self.before_initial_navigation()

            start_url = self.get_start_url()
            Logger.info(f"Navigating to {start_url} ...")
            await self._navigate_to_start_url(start_url)

            await self.login()
            await self.after_start(status_callback=status_callback)

            self.is_running = True
            Logger.success(f"{self.provider_label} Driver started successfully.")

            self.monitoring_active = True
            self._monitor_task = asyncio.create_task(self._monitor_browser_loop())
        except Exception:
            Logger.warning(f"{self.provider_label} Driver failed during startup. Cleaning up...")
            try:
                await self.close()
            except Exception as close_error:
                Logger.debug(f"Cleanup after failed startup raised: {close_error}")
            raise

    async def _cancel_task(
        self,
        task: asyncio.Task | None,
        *,
        label: str,
        timeout_s: float = 2.0,
    ) -> None:
        if not task or task.done():
            return

        current_task = asyncio.current_task()
        if task is current_task:
            return

        try:
            task.cancel()
            done, pending = await asyncio.wait({task}, timeout=timeout_s)
            if pending:
                Logger.warning(f"Timeout while {label}.")
                return
            if done:
                try:
                    task.exception()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            Logger.debug(f"Error while {label}: {e}")

    async def _read_control_signature(self, locator: Any) -> str | None:
        if locator is None:
            return None

        candidate = locator
        try:
            count = await candidate.count()
        except Exception:
            count = None

        if isinstance(count, int):
            if count <= 0:
                return None
            candidate = candidate.first

        try:
            return await candidate.evaluate(
                """(el) => {
                    const normalize = (value) => (value || '').toString().replace(/\\s+/g, ' ').trim();
                    const svgSummary = Array.from(el.querySelectorAll('svg')).slice(0, 6).map((svg) => {
                        return [
                            normalize(svg.getAttribute('name')),
                            normalize(svg.getAttribute('aria-label')),
                            normalize(svg.getAttribute('data-icon')),
                            normalize(svg.getAttribute('title')),
                            normalize(svg.innerHTML)
                        ].join('|');
                    }).join('||');
                    return JSON.stringify({
                        tag: normalize(el.tagName),
                        role: normalize(el.getAttribute('role')),
                        ariaLabel: normalize(el.getAttribute('aria-label')),
                        title: normalize(el.getAttribute('title')),
                        dataTestId: normalize(el.getAttribute('data-testid')),
                        text: normalize(el.textContent),
                        svg: svgSummary,
                        html: normalize(el.innerHTML),
                    });
                }"""
            )
        except Exception:
            return None

    async def _remember_send_control_signature(self, locator: Any) -> str | None:
        signature = await self._read_control_signature(locator)
        if signature:
            self._send_control_signature = signature
        return signature

    async def close(self) -> None:
        """
        Closes the browser and playwright.
        """
        Logger.info(f"Closing {self.provider_label} Driver...")
        self.monitoring_active = False
        monitor_task = getattr(self, "_monitor_task", None)
        try:
            await self._cancel_task(monitor_task, label="stopping monitor task")
        except asyncio.CancelledError:
            pass
        self._monitor_task = None

        try:
            await self.cleanup_background_tasks()
        except Exception as e:
            Logger.debug(f"Error while cleaning up provider background tasks: {e}")

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
        self._send_control_signature = None

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
        max_tokens: int | None = None,
        abort_event: asyncio.Event | None = None,
    ):
        raise NotImplementedError
