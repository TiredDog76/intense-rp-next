import asyncio
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Union

import httpx
from dotenv import load_dotenv

from drivers.base_driver import BaseDriver
from drivers.providers import DriverProvider
from drivers.shared_utils import (
    COMMON_REQUEST_MACRO_ACTIONS,
    clear_clean_regeneration_cache,
    extract_macro_overrides,
    find_multi_slot_cache_entry,
    format_request_messages,
    read_clean_regeneration_state,
    read_multi_slot_cache_payload,
    remove_multi_slot_cache_entry,
    strip_macros_from_messages,
    upsert_multi_slot_cache_entry,
    write_clean_regeneration_state,
)
from utils.cache_manager import CacheManager
from utils.logger import Logger
from utils.model_ids import MODE_CHAT, MODE_REASONER, resolve_behavior_mode

load_dotenv()


class GLMDriver(BaseDriver):
    CHAT_URL = "https://chat.z.ai/"
    AUTH_URL = "https://chat.z.ai/auth"
    CONVERSATION_URL_RE = re.compile(r"^https://chat\.z\.ai/c/([^/?#]+)", re.IGNORECASE)

    REFRESH_AFTER_GENERATION_DELAY_S = 2.0
    INTERCEPT_FIRST_CHUNK_TIMEOUT_S = 45.0
    INTERCEPT_IDLE_TIMEOUT_S = 75.0
    MODEL_SELECTOR_READY_TIMEOUT_MS = 20000

    SIDEBAR_NEW_CHAT_BUTTON_SELECTOR = "button#sidebar-new-chat-button"
    QUICK_NEW_CHAT_BUTTON_SELECTOR = "button[data-scene='chat']"
    LEGACY_QUICK_NEW_CHAT_BUTTON_SELECTOR = "button#new-chat-button"

    MODEL_SELECTOR_BUTTON_SELECTOR = "button.modelSelectorButton"
    MODEL_DROPDOWN_ID = "f8T9iEf1QC"
    MODEL_DROPDOWN_SELECTOR = f"div#{MODEL_DROPDOWN_ID}"
    MODEL_DATA_VALUE_BY_FRIENDLY: Dict[str, str] = {
        "GLM-5": "glm-5",
        "GLM-5-Turbo": "GLM-5-Turbo",
        "GLM-5V-Turbo": "GLM-5v-Turbo",
        "GLM-4.7": "glm-4.7",
        "GLM-4.6": "GLM-4-6-API-V1",
    }

    # Models hidden behind a collapsible section in the dropdown
    MODELS_IN_COLLAPSIBLE: set = {"GLM-4.7", "GLM-4.6"}

    def __init__(self, config_manager):
        super().__init__(config_manager=config_manager, provider=DriverProvider.GLM_CHAT)
        self.cache_manager = CacheManager()

        # GLM UI language detection (we refuse to operate unless the UI is English)
        self.last_document_lang: Optional[str] = None
        self.ui_language_ok: Optional[bool] = None
        self._non_english_ui_warned = False
        self._non_english_ui_warned_lang: Optional[str] = None

        self.current_model: Optional[str] = None
        self.current_send_deepthink: Optional[bool] = None
        self.thinking_active = False

        self.clean_regen_message_cache_key = "glm_last_message.txt"
        self.clean_regen_state_cache_key = "glm_last_message_state.json"
        self.multi_slot_cache_key = "glm_multi_slot_cache.json"
        self.repetition_buster_cache_key = "glm_repetition_buster_prompt_cache.json"

        self._refresh_after_generation = False
        self._refresh_after_generation_task: asyncio.Task | None = None

        self._refresh_quirks()

    def _refresh_quirks(self) -> None:
        """Read quirks settings from config and cache them as instance attributes."""
        try:
            ui_timeout = int(self.config_manager.get_setting("glm_behavior", "ui_click_timeout") or 3000)
        except Exception:
            ui_timeout = 3000
        try:
            post_delay = int(self.config_manager.get_setting("glm_behavior", "post_action_delay") or 500)
        except Exception:
            post_delay = 500
        try:
            msg_send_timeout = int(self.config_manager.get_setting("glm_behavior", "message_send_timeout") or 5)
        except Exception:
            msg_send_timeout = 5
        try:
            first_chunk_timeout = float(
                self.config_manager.get_setting("glm_behavior", "first_chunk_timeout") or self.INTERCEPT_FIRST_CHUNK_TIMEOUT_S
            )
        except Exception:
            first_chunk_timeout = self.INTERCEPT_FIRST_CHUNK_TIMEOUT_S
        try:
            refresh_after_generation = bool(
                self.config_manager.get_setting("glm_behavior", "refresh_after_generation")
            )
        except Exception:
            refresh_after_generation = False

        self._ui_timeout = max(ui_timeout, 500)
        self._post_delay_s = max(post_delay, 0) / 1000.0
        self._msg_send_timeout = max(msg_send_timeout, 1)
        self._first_chunk_timeout_s = max(first_chunk_timeout, 5.0)
        self._refresh_after_generation = bool(refresh_after_generation)

    async def _await_pending_refresh_after_generation(self, abort_event: asyncio.Event | None = None) -> None:
        task = getattr(self, "_refresh_after_generation_task", None)
        if not task:
            return

        if abort_event and abort_event.is_set():
            try:
                if not task.done():
                    task.cancel()
            except Exception:
                pass
            self._refresh_after_generation_task = None
            return

        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            Logger.warning(f"GLM Chat: Refresh After Generation task failed: {e}")
        finally:
            self._refresh_after_generation_task = None

    def _schedule_refresh_after_generation(self) -> None:
        if not self.page:
            return
        if not getattr(self, "_refresh_after_generation", False):
            return

        try:
            if self.page.is_closed():
                return
        except Exception:
            pass

        existing = getattr(self, "_refresh_after_generation_task", None)
        if existing and (not existing.done()):
            try:
                existing.cancel()
            except Exception:
                pass

        self._refresh_after_generation_task = asyncio.create_task(self._refresh_page_after_generation())

    async def _refresh_page_after_generation(self) -> None:
        if not self.page:
            return

        try:
            await asyncio.sleep(self.REFRESH_AFTER_GENERATION_DELAY_S)
        except asyncio.CancelledError:
            return

        try:
            if self.page.is_closed():
                return
        except Exception:
            pass

        Logger.info("GLM Chat: Refresh After Generation enabled, reloading page...")

        try:
            await self.page.reload(wait_until="domcontentloaded", timeout=45000)
        except asyncio.CancelledError:
            return
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to reload after generation: {e}")
            return

        try:
            await self._wait_for_chat_shell_ready(timeout_ms=60000)
        except Exception as e:
            Logger.warning(f"GLM Chat: page reload completed but chat shell was not ready: {e}")
            return

        # Best-effort: if the session expired, warn early so the next request isn't a surprise
        try:
            if await self._chat_page_contains_sign_in():
                Logger.warning("GLM Chat: after reload, Sign in was detected - you may need to log in again.")
        except Exception:
            pass

    @property
    def required_ui_language_label(self) -> str:
        return "English (en-US)"

    def get_start_url(self) -> str:
        return self.CHAT_URL

    async def after_start(self, status_callback: Optional[Callable[[str], None]] = None) -> None:
        await self.check_ui_language(status_callback=status_callback)
        clear_clean_regeneration_cache(
            self.cache_manager,
            self.clean_regen_message_cache_key,
            self.clean_regen_state_cache_key,
        )

    async def cleanup_background_tasks(self) -> None:
        await self._cancel_task(
            self._refresh_after_generation_task,
            label="stopping GLM refresh-after-generation task",
        )
        self._refresh_after_generation_task = None

    async def apply_configured_model(self, wait_until_ready: bool = False) -> None:
        desired_friendly = self._get_configured_glm_model_friendly()
        if not desired_friendly:
            return

        # GLM's model picker is unreliable outside the fresh-new-chat flow
        # Keep the generic provider hook as a harmless no-op and only perform
        # actual picker work when a caller explicitly opts into waiting
        if not wait_until_ready:
            return

        try:
            await self._ensure_glm_model_selected(desired_friendly, wait_until_ready=wait_until_ready)
        except Exception as e:
            Logger.warning(f"GLM Chat: Failed to apply model selection '{desired_friendly}': {e}")

    def _get_configured_glm_model_friendly(self) -> str:
        try:
            value = self.config_manager.get_setting("glm_behavior", "model")
        except Exception:
            value = None
        return str(value or "").strip()

    @staticmethod
    def _normalize_model_label(value: str) -> str:
        return re.sub(r"\\s+", " ", str(value or "")).strip().lower()

    async def _is_glm_model_selector_ready(self) -> bool:
        if not self.page:
            return False

        expression = (
            "selector => {"
            "  const btn = document.querySelector(selector);"
            "  if (!btn) return false;"
            "  const style = window.getComputedStyle(btn);"
            "  if (!style || style.display === 'none' || style.visibility === 'hidden') return false;"
            "  const rect = btn.getBoundingClientRect();"
            "  if (!rect || rect.width <= 0 || rect.height <= 0) return false;"
            "  if (btn.disabled) return false;"
            "  return true;"
            "}"
        )
        try:
            ready = await self.page.evaluate(expression, self.MODEL_SELECTOR_BUTTON_SELECTOR)
        except Exception as e:
            Logger.debug(f"GLM Chat: failed to read model selector readiness: {e}")
            return False
        return bool(ready)

    async def _wait_for_glm_model_selector_ready(self, timeout_ms: int = 10000) -> bool:
        if not self.page:
            return False

        expression = (
            "selector => {"
            "  const btn = document.querySelector(selector);"
            "  if (!btn) return false;"
            "  const style = window.getComputedStyle(btn);"
            "  if (!style || style.display === 'none' || style.visibility === 'hidden') return false;"
            "  const rect = btn.getBoundingClientRect();"
            "  if (!rect || rect.width <= 0 || rect.height <= 0) return false;"
            "  if (btn.disabled) return false;"
            "  return true;"
            "}"
        )
        try:
            await self.page.wait_for_function(expression, self.MODEL_SELECTOR_BUTTON_SELECTOR, timeout=int(timeout_ms))
            return True
        except Exception:
            return False

    async def _wait_and_open_glm_model_dropdown(self, timeout_ms: int = 10000) -> bool:
        if not self.page:
            return False

        deadline = time.time() + max(0.0, float(timeout_ms) / 1000.0)
        while True:
            if await self._open_glm_model_dropdown(timeout_ms=min(self._ui_timeout, 1000)):
                return True

            if time.time() >= deadline:
                return False

            await asyncio.sleep(0.2)

    async def _read_current_glm_model_label(self) -> str:
        if not self.page:
            return ""

        try:
            label = await self.page.evaluate(
                "() => {"
                "  const btn = document.querySelector('button.modelSelectorButton');"
                "  if (!btn) return '';"
                "  const div = btn.querySelector('div');"
                "  if (!div) return '';"
                "  const node = div.childNodes && div.childNodes[0];"
                "  const text = (node && node.textContent) ? node.textContent : (div.textContent || '');"
                "  return (text || '').toString().trim();"
                "}"
            )
        except Exception as e:
            Logger.debug(f"GLM Chat: failed to read current model label: {e}")
            return ""

        return str(label or "").strip()

    async def _open_glm_model_dropdown(self, timeout_ms: int = 5000) -> bool:
        if not self.page:
            return False

        button = self.page.locator(self.MODEL_SELECTOR_BUTTON_SELECTOR)
        if await button.count() == 0:
            Logger.warning("GLM Chat: model selector button not found.")
            return False

        try:
            await button.first.click(timeout=self._ui_timeout)
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to click model selector button: {e}")
            return False

        # Wait for the dropdown content to appear.
        try:
            await self.page.wait_for_selector(
                f"{self.MODEL_DROPDOWN_SELECTOR} button[data-value]",
                timeout=int(timeout_ms),
                state="visible",
            )
            return True
        except Exception:
            pass

        # Fallback if the dropdown id changes.
        try:
            await self.page.wait_for_selector("button[data-value]", timeout=int(timeout_ms), state="visible")
            return True
        except Exception:
            Logger.warning("GLM Chat: model dropdown did not appear after clicking the selector (this is usually very bad).")
            return False

    async def _close_glm_model_dropdown(self) -> None:
        if not self.page:
            return

        button = self.page.locator(self.MODEL_SELECTOR_BUTTON_SELECTOR)
        if await button.count() == 0:
            return

        try:
            await button.first.click(timeout=self._ui_timeout)
        except Exception:
            return

        try:
            await self.page.wait_for_selector(self.MODEL_DROPDOWN_SELECTOR, timeout=self._ui_timeout, state="hidden")
        except Exception:
            return

    async def _expand_collapsible_section(self) -> bool:
        """Expand the model dropdown's More Models section when it is collapsed."""
        if not self.page:
            return False

        try:
            content = self.page.locator("div[data-melt-collapsible-content]")
            if await content.count() > 0:
                try:
                    if await content.first.is_visible():
                        return True
                except Exception:
                    pass

            trigger = self.page.locator("button[data-melt-collapsible-trigger]")
            if await trigger.count() == 0:
                return False

            await trigger.first.click(timeout=self._ui_timeout)

            # Wait for the content to appear
            await content.first.wait_for(state="visible", timeout=self._ui_timeout)
            return True
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to expand collapsible section: {e}")
            return False

    async def _click_glm_model_option(self, data_value: str, friendly_name: str = "") -> bool:
        if not self.page:
            return False

        safe_value = str(data_value or "").strip()
        if not safe_value:
            return False

        if friendly_name in self.MODELS_IN_COLLAPSIBLE:
            await self._expand_collapsible_section()

        option = self.page.locator(
            f"{self.MODEL_DROPDOWN_SELECTOR} button[data-value='{safe_value}']"
        )
        if await option.count() == 0:
            option = self.page.locator(f"button[data-value='{safe_value}']")
        if await option.count() == 0 and friendly_name not in self.MODELS_IN_COLLAPSIBLE:
            await self._expand_collapsible_section()
            option = self.page.locator(
                f"{self.MODEL_DROPDOWN_SELECTOR} button[data-value='{safe_value}']"
            )
            if await option.count() == 0:
                option = self.page.locator(f"button[data-value='{safe_value}']")

        count = await option.count()
        if count == 0:
            return False

        for idx in range(min(count, 10)):
            cand = option.nth(idx)
            try:
                if not await cand.is_visible():
                    continue
                await cand.click(timeout=self._ui_timeout)
                return True
            except Exception:
                continue

        try:
            await option.first.click(timeout=self._ui_timeout)
            return True
        except Exception:
            return False

    async def _click_first_glm_model_option(self) -> Optional[str]:
        if not self.page:
            return None

        options = self.page.locator(f"{self.MODEL_DROPDOWN_SELECTOR} button[data-value]")
        if await options.count() == 0:
            options = self.page.locator("button[data-value]")

        count = await options.count()
        if count == 0:
            return None

        for idx in range(min(count, 25)):
            cand = options.nth(idx)
            try:
                if not await cand.is_visible():
                    continue
            except Exception:
                pass

            try:
                data_value = (await cand.get_attribute("data-value")) or ""
            except Exception:
                data_value = ""

            try:
                await cand.click(timeout=self._ui_timeout)
            except Exception:
                continue

            return str(data_value or "").strip() or None

        return None

    async def _ensure_glm_model_selected(self, desired_friendly: str, wait_until_ready: bool = False) -> None:
        if not self.page:
            return

        desired = str(desired_friendly or "").strip()
        if not desired:
            return

        desired_data_value = self.MODEL_DATA_VALUE_BY_FRIENDLY.get(desired)
        if not desired_data_value:
            Logger.warning(f"GLM Chat: unknown configured model '{desired}'.")
            return

        current_label = await self._read_current_glm_model_label()
        if self._normalize_model_label(current_label) == self._normalize_model_label(desired):
            return

        if wait_until_ready:
            if not await self._wait_and_open_glm_model_dropdown(timeout_ms=self.MODEL_SELECTOR_READY_TIMEOUT_MS):
                Logger.warning("GLM Chat: model selector did not become openable in time.")
                return
        else:
            if not await self._is_glm_model_selector_ready():
                Logger.debug("GLM Chat: model selector is not ready for interaction.")
                return
            if not await self._open_glm_model_dropdown(timeout_ms=5000):
                return

        try:
            clicked = await self._click_glm_model_option(desired_data_value, friendly_name=desired)
            if not clicked:
                Logger.error(
                    f"GLM Chat: desired model '{desired}' not found in dropdown (data-value '{desired_data_value}'). "
                    "Selecting the first available model instead."
                )
                fallback_value = await self._click_first_glm_model_option()
                if fallback_value:
                    Logger.warning(f"GLM Chat: selected fallback model data-value '{fallback_value}'.")
        finally:
            await self._close_glm_model_dropdown()

    async def _get_document_lang(self) -> str:
        if not self.page:
            return ""

        try:
            lang = await self.page.evaluate(
                "() => {"
                "  const el = document.documentElement;"
                "  if (!el) return '';"
                "  return (el.getAttribute('lang') || el.lang || '').toString();"
                "}"
            )
        except Exception as e:
            Logger.debug(f"Failed to read GLM document language: {e}")
            return ""

        if not isinstance(lang, str):
            try:
                lang = str(lang)
            except Exception:
                return ""

        return lang.strip()

    @staticmethod
    def _is_english_lang(lang: str) -> bool:
        normalized = (lang or "").strip().lower()
        if not normalized:
            return False
        if normalized == "en-us":
            return True
        if normalized == "en" or normalized.startswith("en-"):
            return True
        return False

    async def check_ui_language(self, status_callback: Optional[Callable[[str], None]] = None) -> bool:
        lang = await self._get_document_lang()
        self.last_document_lang = lang or None

        ok = self._is_english_lang(lang)
        self.ui_language_ok = ok

        if ok:
            self._non_english_ui_warned = False
            self._non_english_ui_warned_lang = None
            return True

        # Warn only once per detected language value to avoid log spam
        if (not self._non_english_ui_warned) or (self._non_english_ui_warned_lang != lang):
            self._non_english_ui_warned = True
            self._non_english_ui_warned_lang = lang

            detected = lang or "<unset>"
            Logger.warning(
                f"GLM Chat UI language detected as '{detected}'. "
                "IntenseRP currently expects English UI (en-US). "
                "Please change GLM Chat language to English in the browser window, then refresh/reload."
            )
            if status_callback:
                status_callback("GLM Chat UI language is not English. Please change it to English (en-US).")

        return False

    async def require_english_ui(self) -> None:
        ok = await self.check_ui_language()
        if ok:
            return

        detected = self.last_document_lang or "<unset>"
        raise RuntimeError(
            f"GLM Chat UI language is not English (detected: {detected}). "
            "IntenseRP currently requires GLM Chat UI language to be English (en-US). "
            "Please change GLM Chat language to English and reload the page."
        )

    async def _chat_page_contains_sign_in(self) -> bool:
        if not self.page:
            return False

        # Prefer a real element match over brittle body-text scans
        # (Body innerText may not be fully populated during loading screens)
        try:
            sign_in_controls = self.page.locator(
                "button:has-text('Sign in'), a:has-text('Sign in'), [role='button']:has-text('Sign in')"
            )
            count = await sign_in_controls.count()
            if count > 0:
                # Only treat as auth-needed if at least one is actually visible.
                for idx in range(min(count, 10)):
                    try:
                        if await sign_in_controls.nth(idx).is_visible():
                            return True
                    except Exception:
                        continue
        except Exception:
            pass

        try:
            # js fallback 1
            return bool(
                await self.page.evaluate(
                    "() => {"
                    "  const el = document.body;"
                    "  if (!el) return false;"
                    "  const text = (el.innerText || '');"
                    "  return text.includes('Sign in');"
                    "}"
                )
            )
        except Exception:
            return False

    async def _wait_for_chat_ready(self, timeout_ms: int | None = None) -> None:
        if not self.page:
            return

        timeout = 0 if timeout_ms is None else int(timeout_ms)
        await self.page.wait_for_selector("textarea#chat-input, #chat-input", timeout=timeout, state="visible")

    async def _wait_for_chat_shell_ready(self, timeout_ms: int | None = None) -> None:
        """
        Wait for GLM's initial loading screen to resolve into a stable UI.

        GLM can show a splash/loading view where auth text isn't present yet.
        We treat the page as "ready for auth detection" once either:
        - the chat composer appears, or
        - a visible Sign in control suddenly appears, confirming all your fears.
        """
        if not self.page:
            return

        timeout = 0 if timeout_ms is None else int(timeout_ms)
        await self.page.wait_for_selector(
            "textarea#chat-input, #chat-input, "
            "button:has-text('Sign in'), a:has-text('Sign in'), [role='button']:has-text('Sign in')",
            timeout=timeout,
            state="visible",
        )

    async def login(self) -> None:
        """
        GLM Chat does not auto-redirect to the auth page, so we must detect auth state.
        """
        if not self.page:
            return

        try:
            await self.page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass

        # GLM shows an initial loading screen; auth UI is unreliable to detect until the
        # app transitions into its stable shell. Wait for composer/sign-in UI before checking auth
        try:
            await self._wait_for_chat_shell_ready(timeout_ms=60000)
        except Exception as e:
            # If the composer never appears (UI change / slow load), fall back to best-effort auth detection
            Logger.debug(f"GLM Chat: chat composer not detected before auth check: {e}")

        needs_auth = await self._chat_page_contains_sign_in()
        if not needs_auth:
            Logger.info("GLM Chat: already signed in (or Sign in not detected).")
            self._mark_active_ece_pair_used()
            return

        auto_login = bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
        if not auto_login:
            Logger.info("GLM Chat: Auto-login disabled. Waiting for manual login...")
            await self.page.goto(self.AUTH_URL)
            await self._wait_for_chat_ready(timeout_ms=None)
            Logger.success("GLM Chat: manual login detected.")
            return

        email = ""
        password = ""

        pair = self.ece_active_pair()
        if not pair:
            Logger.warning(
                "GLM Chat: Auto-login is enabled but no accounts are configured in Credential Manager. "
                "Waiting for manual login..."
            )
            await self.page.goto(self.AUTH_URL)
            await self._wait_for_chat_ready(timeout_ms=None)
            Logger.success("GLM Chat: manual login detected.")
            return

        email = pair.email
        password = pair.password

        if not email or not password:
            Logger.error("GLM Chat account is missing an email or password.")
            return

        Logger.info("GLM Chat: Auto-login enabled. Attempting login...")
        await self.page.goto(self.AUTH_URL)

        try:
            await self.page.wait_for_selector(".loginFormUni", timeout=30000)
        except Exception as e:
            Logger.error(f"GLM Chat: login form not found: {e}")
            return

        form_root = self.page.locator(".loginFormUni")
        if await form_root.count() == 0:
            form_root = self.page.locator("body")

        # Select the email login button: second <button> under loginFormUni
        try:
            email_button = form_root.first.locator("button").nth(1)
            if await email_button.count() > 0:
                await email_button.click()
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to click email login button: {e}")

        # Fill credentials
        try:
            email_input = self.page.locator("input[type='email']")
            password_input = self.page.locator("input[type='password']")
            await email_input.first.fill(str(email))
            await password_input.first.fill(str(password))
        except Exception as e:
            Logger.error(f"GLM Chat: failed to fill credentials: {e}")
            return

        # Submit
        try:
            submit_button = self.page.locator("button[type='submit']")
            await submit_button.first.click()
        except Exception as e:
            Logger.error(f"GLM Chat: failed to click submit: {e}")
            return

        # CAPTCHA is required and must be solved manually.
        self.notify_user(
            "GLM Chat Login",
            "Please solve the CAPTCHA in the GLM Chat browser window, then click Sign in.",
            level="warning",
        )
        Logger.warning("GLM Chat: waiting for CAPTCHA / manual confirmation...")

        await self._wait_for_chat_ready(timeout_ms=None)
        Logger.success("GLM Chat: chat ready.")

        self.ece_mark_used(email)

    def _resolve_deepthink_flags(self, model: str) -> tuple[bool, bool]:
        enable_deepthink = bool(self.config_manager.get_setting("glm_behavior", "enable_deepthink"))
        send_deepthink = bool(self.config_manager.get_setting("glm_behavior", "send_deepthink"))

        mode = resolve_behavior_mode(model, self.provider)
        if mode == MODE_CHAT:
            return False, False
        if mode == MODE_REASONER:
            return True, send_deepthink

        return enable_deepthink, send_deepthink

    def _resolve_glm_request_settings(self, model: str, overrides: Optional[Dict[str, bool]] = None) -> Dict[str, bool]:
        resolved_model = (model or "").strip() or "glm-auto"
        deepthink_enabled, send_deepthink = self._resolve_deepthink_flags(resolved_model)
        enable_search = bool(self.config_manager.get_setting("glm_behavior", "enable_search"))
        send_as_text_file = bool(self.config_manager.get_setting("glm_behavior", "send_as_text_file"))

        settings = {
            "deepthink_enabled": bool(deepthink_enabled),
            "send_deepthink": bool(send_deepthink),
            "search_enabled": bool(enable_search),
            "send_as_text_file": bool(send_as_text_file),
        }

        if overrides:
            for key in ("deepthink_enabled", "send_deepthink", "search_enabled", "send_as_text_file"):
                if key in overrides:
                    settings[key] = bool(overrides[key])

        return settings

    def _extract_glm_macros_from_text(self, text: str) -> tuple[str, Dict[str, bool]]:
        return extract_macro_overrides(text, macro_actions=COMMON_REQUEST_MACRO_ACTIONS)

    def _strip_glm_macros_from_messages(self, messages: List[Any]) -> tuple[List[Any], Dict[str, bool]]:
        return strip_macros_from_messages(messages, macro_actions=COMMON_REQUEST_MACRO_ACTIONS)

    def _read_clean_regeneration_state(self) -> Optional[Dict[str, Any]]:
        return read_clean_regeneration_state(
            self.cache_manager,
            self.clean_regen_state_cache_key,
            log_label="Clean Regeneration (GLM)",
        )

    def _write_clean_regeneration_state(self, state: Dict[str, Any]) -> None:
        write_clean_regeneration_state(
            self.cache_manager,
            self.clean_regen_state_cache_key,
            state,
        )

    def _build_multi_slot_cache_state(
        self,
        *,
        effective_deepthink: bool,
        enable_search: bool,
        send_as_text_file: bool,
    ) -> Dict[str, Any]:
        return {
            "deepthink_enabled": bool(effective_deepthink),
            "search_enabled": bool(enable_search),
            "send_as_text_file": bool(send_as_text_file),
            "ui_model": self._get_configured_glm_model_friendly(),
        }

    async def _prepare_new_chat_request_ui(
        self,
        *,
        effective_deepthink: bool,
        enable_search: bool,
        log_label: str = "GLM Chat: preparing new chat session...",
    ) -> None:
        Logger.info(log_label)
        await self.click_new_chat(source="auto")
        await asyncio.sleep(self._post_delay_s)

        await self.apply_configured_model(wait_until_ready=True)
        await self.set_deepthink_state(bool(effective_deepthink))
        await self.set_search_state(bool(enable_search))
        await asyncio.sleep(self._post_delay_s)

    async def _send_text_request(
        self,
        message: str,
        *,
        send_timeout: int | None,
        arm_event: asyncio.Event | None = None,
        log_label: str = "GLM Chat: sending request...",
    ) -> None:
        await self._enter_message(message)
        await asyncio.sleep(self._post_delay_s)
        Logger.info(log_label)
        await self._send_message(timeout=send_timeout, arm_event=arm_event)

    async def _run_repetition_buster(
        self,
        *,
        effective_deepthink: bool,
        enable_search: bool,
        auto_delete_after_send: bool = False,
    ) -> None:
        Logger.info(
            "Repetition Buster (GLM): duplicate prompt detected. Sending a 128-character "
            "cache-buster prompt in a throwaway chat first..."
        )
        await self._prepare_new_chat_request_ui(
            effective_deepthink=effective_deepthink,
            enable_search=enable_search,
            log_label="Repetition Buster (GLM): opening throwaway chat...",
        )
        await self._send_text_request(
            self._generate_repetition_buster_text(128),
            send_timeout=self._msg_send_timeout,
            log_label="Repetition Buster (GLM): sending cache-buster prompt...",
        )
        await asyncio.sleep(self._post_delay_s)
        if auto_delete_after_send:
            await self._auto_delete_current_chat(log_context="Repetition Buster (GLM)")

    def _parse_conversation_info_from_url(self, url: str) -> Optional[Dict[str, str]]:
        normalized_url = str(url or "").strip()
        if not normalized_url:
            return None

        match = self.CONVERSATION_URL_RE.match(normalized_url)
        if not match:
            return None

        conversation_id = str(match.group(1) or "").strip()
        if not conversation_id:
            return None

        return {
            "conversation_id": conversation_id,
            "conversation_url": f"https://chat.z.ai/c/{conversation_id}",
        }

    async def _get_current_conversation_info(self) -> Optional[Dict[str, str]]:
        if not self.page:
            return None

        try:
            current_url = str(self.page.url or "")
        except Exception:
            current_url = ""

        return self._parse_conversation_info_from_url(current_url)

    async def _wait_for_current_conversation_info(
        self,
        timeout_ms: int = 6000,
        poll_interval_s: float = 0.2,
    ) -> Optional[Dict[str, str]]:
        deadline = time.time() + max(0.0, float(timeout_ms) / 1000.0)
        while True:
            info = await self._get_current_conversation_info()
            if info is not None:
                return info

            if time.time() >= deadline:
                return None

            await asyncio.sleep(max(0.05, float(poll_interval_s)))

    async def _delete_conversation_by_id(self, conversation_id: str) -> bool:
        normalized_id = str(conversation_id or "").strip()
        if not normalized_id:
            return False

        result = await self._run_browser_request(
            method="DELETE",
            url=f"https://chat.z.ai/api/v1/chats/{normalized_id}",
            referrer="https://chat.z.ai/",
        )
        if bool(result.get("ok")):
            return True

        detail = str(result.get("error") or result.get("text") or "").strip()
        status = int(result.get("status") or 0)
        suffix = f" ({detail[:180]})" if detail else ""
        Logger.warning(
            f"GLM Chat: failed to auto-delete chat {normalized_id} (status={status}){suffix}"
        )
        return False

    async def _auto_delete_current_chat(self, *, log_context: str = "GLM Chat") -> bool:
        current_info = await self._get_current_conversation_info()
        if current_info is None:
            Logger.debug(f"{log_context}: auto-delete skipped because the current chat ID was not available.")
            return False

        conversation_id = str(current_info.get("conversation_id") or "").strip()
        if not conversation_id:
            Logger.debug(f"{log_context}: auto-delete skipped because the current chat ID was empty.")
            return False

        try:
            await self.click_new_chat(source="auto")
            await asyncio.sleep(self._post_delay_s)
        except Exception as e:
            Logger.warning(
                f"{log_context}: auto-delete skipped because a replacement chat could not be prepared: {e}"
            )
            return False

        if await self._delete_conversation_by_id(conversation_id):
            Logger.info(f"{log_context}: auto-deleted the completed chat.")
            return True

        return False

    async def _open_cached_conversation(self, conversation_url: str) -> bool:
        if not self.page:
            return False

        target_url = str(conversation_url or "").strip()
        if not target_url:
            return False

        try:
            await self.page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            Logger.warning(f"Multi-Slot Cache (GLM): failed to open cached chat URL: {e}")
            return False

        try:
            await self._wait_for_chat_shell_ready(timeout_ms=60000)
        except Exception as e:
            Logger.warning(f"Multi-Slot Cache (GLM): chat shell did not become ready: {e}")
            return False

        try:
            if await self._chat_page_contains_sign_in():
                Logger.warning("Multi-Slot Cache (GLM): cached chat URL requires sign-in.")
                return False
        except Exception:
            pass

        return True

    async def _try_multi_slot_regeneration(
        self,
        *,
        formatted_message: str,
        multi_slot_state: Dict[str, Any],
        completion_armed: asyncio.Event,
        completion_started: asyncio.Event,
    ) -> bool:
        account_key = self._get_multi_slot_cache_account_key()
        payload = read_multi_slot_cache_payload(
            self.cache_manager,
            self.multi_slot_cache_key,
            log_label="Multi-Slot Cache (GLM)",
        )
        entry = find_multi_slot_cache_entry(payload, account_key, formatted_message, multi_slot_state)
        if entry is None:
            return False

        current_info = await self._get_current_conversation_info()
        if current_info is None or current_info["conversation_id"] != entry["conversation_id"]:
            Logger.info("Multi-Slot Cache (GLM): opening cached conversation for regeneration...")
            opened = await self._open_cached_conversation(entry["conversation_url"])
            if not opened:
                return False
            current_info = await self._get_current_conversation_info()
            if current_info is None or current_info["conversation_id"] != entry["conversation_id"]:
                Logger.warning(
                    "Multi-Slot Cache (GLM): cached conversation URL opened, but the expected "
                    "chat ID was not available. Falling back to a new chat."
                )
                return False

        try:
            await self.set_deepthink_state(bool(multi_slot_state.get("deepthink_enabled")))
            await self.set_search_state(bool(multi_slot_state.get("search_enabled")))
            await asyncio.sleep(self._post_delay_s)
        except Exception:
            pass

        regen_timeout = max(int(getattr(self, "_ui_timeout", 3000)), 5000)
        Logger.info("Multi-Slot Cache (GLM): cached prompt match found. Attempting to regenerate...")
        if not await self._click_regenerate(timeout_ms=regen_timeout, arm_event=completion_armed):
            Logger.warning(
                "Multi-Slot Cache (GLM): regenerate button unavailable. Removing cached entry."
            )
            remove_multi_slot_cache_entry(
                self.cache_manager,
                self.multi_slot_cache_key,
                account_key,
                entry["conversation_id"],
                log_label="Multi-Slot Cache (GLM)",
            )
            return False

        try:
            await asyncio.wait_for(completion_started.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            Logger.warning(
                "Multi-Slot Cache (GLM): completion request not observed after clicking "
                "Regenerate. Removing cached entry."
            )
            remove_multi_slot_cache_entry(
                self.cache_manager,
                self.multi_slot_cache_key,
                account_key,
                entry["conversation_id"],
                log_label="Multi-Slot Cache (GLM)",
            )
            return False

        return True

    def _format_messages(self, messages: Union[str, List[Any]]) -> str:
        return format_request_messages(self.config_manager, messages)

    async def set_sidebar_status(self, open: bool) -> None:
        if not self.page:
            return

        sidebar = self.page.locator("#sidebar")
        if await sidebar.count() == 0:
            Logger.warning("GLM Chat: sidebar container not found.")
            return

        state = (await sidebar.first.get_attribute("data-state")) or ""
        is_open = state.strip().lower() == "true"

        if is_open == open:
            return

        if open:
            toggle = self.page.locator("button#sidebar-toggle-button")
        else:
            toggle = (
                sidebar.first.locator("div").nth(0).locator("div").nth(0).locator("button").nth(0)
            )

        if await toggle.count() == 0:
            Logger.warning("GLM Chat: sidebar toggle button not found.")
            return

        try:
            await toggle.first.click(timeout=self._ui_timeout)
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to click sidebar toggle: {e}")
            return

        # Wait for state to flip
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                state_now = (await sidebar.first.get_attribute("data-state")) or ""
                open_now = state_now.strip().lower() == "true"
                if open_now == open:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.1)

    async def click_new_chat(self, source: str = "auto") -> None:
        if not self.page:
            return

        sidebar = self.page.locator("#sidebar")
        is_open = False
        try:
            state = (await sidebar.first.get_attribute("data-state")) or ""
            is_open = state.strip().lower() == "true"
        except Exception:
            is_open = False

        if source == "sidebar":
            is_open = True
        elif source == "simple":
            is_open = False
        elif source != "auto":
            Logger.warning(f"GLM Chat: unknown new chat source '{source}'.")

        selectors = (
            [
                self.SIDEBAR_NEW_CHAT_BUTTON_SELECTOR,
                self.QUICK_NEW_CHAT_BUTTON_SELECTOR,
                self.LEGACY_QUICK_NEW_CHAT_BUTTON_SELECTOR,
            ]
            if is_open
            else [
                self.QUICK_NEW_CHAT_BUTTON_SELECTOR,
                self.LEGACY_QUICK_NEW_CHAT_BUTTON_SELECTOR,
                self.SIDEBAR_NEW_CHAT_BUTTON_SELECTOR,
            ]
        )

        btn = None
        for selector in selectors:
            locator = self.page.locator(selector)
            count = await locator.count()
            for idx in range(min(count, 5)):
                candidate = locator.nth(idx)
                try:
                    if await candidate.is_visible():
                        btn = candidate
                        break
                except Exception:
                    continue
            if btn is not None:
                break

        if btn is None:
            Logger.warning("GLM Chat: New Chat button not found.")
            return

        try:
            await btn.click(timeout=self._ui_timeout)
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to click New Chat: {e}")

    async def _find_deepthink_button(self):
        """Find the DeepThink button by its ``data-autothink`` attribute."""
        if not self.page:
            return None

        try:
            candidates = self.page.locator("button[data-autothink]")
            count = await candidates.count()
        except Exception:
            return None

        for idx in range(min(count, 25)):
            cand = candidates.nth(idx)
            try:
                if await cand.is_visible():
                    return cand
            except Exception:
                pass

        return candidates.first if count > 0 else None

    async def _find_search_button(self):
        """Find the Search button by its ``data-melt-tooltip-trigger`` attribute,
        excluding the DeepThink button (which carries ``data-autothink``)."""
        if not self.page:
            return None

        try:
            candidates = self.page.locator(
                "button[data-melt-tooltip-trigger]:not([data-autothink])"
            )
            count = await candidates.count()
        except Exception:
            return None

        for idx in range(min(count, 25)):
            cand = candidates.nth(idx)
            try:
                if await cand.is_visible():
                    return cand
            except Exception:
                pass

        return candidates.first if count > 0 else None

    async def set_deepthink_state(self, state: bool) -> None:
        if not self.page:
            return

        button = await self._find_deepthink_button()
        if not button:
            Logger.warning("GLM Chat: Deep Think button not found.")
            return

        try:
            attr = await button.get_attribute("data-autothink")
            is_enabled = str(attr or "").strip().lower() == "true"
        except Exception:
            is_enabled = False

        if is_enabled == state:
            return

        try:
            await button.click()
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to toggle Deep Think: {e}")

    async def set_search_state(self, state: bool) -> None:
        if not self.page:
            return

        wrapper = await self._find_search_button()
        if not wrapper:
            Logger.warning("GLM Chat: Search button not found.")
            return

        # The outer element (data-melt-tooltip-trigger) wraps an inner <button>
        # that is the actual toggle and carries the "bg-black/6" class when active
        inner = wrapper.locator("button").first

        try:
            is_enabled = bool(await inner.evaluate("el => el.classList.contains('bg-black/6')"))
        except Exception:
            is_enabled = False

        if is_enabled == state:
            return

        try:
            await inner.click(timeout=self._ui_timeout)
        except Exception as e:
            Logger.warning(f"GLM Chat: failed to toggle Search: {e}")

    async def upload_file(self, file_spec: Any) -> None:
        await self._upload_file(file_spec)

    async def _upload_file(self, file_spec: Any) -> None:
        if not self.page:
            return

        file_input = self.page.locator("input[type='file']")
        if await file_input.count() == 0:
            Logger.warning("GLM Chat: file input not found.")
            return

        await file_input.first.set_input_files(file_spec)
        await asyncio.sleep(0.5)

    async def enter_message(self, message: str) -> None:
        await self._enter_message(message)

    async def _enter_message(self, message: str) -> None:
        if not self.page:
            return

        textarea = self.page.locator("textarea#chat-input")
        if await textarea.count() == 0:
            Logger.warning("GLM Chat: message textarea not found.")
            return

        # Use JS to set the value through the native property setter and dispatch
        # events so that Svelte's reactive bindings pick up the change. This is
        # more reliable than Playwright's .fill() for large inputs on slow machines.
        try:
            await self.page.evaluate(
                """(msg) => {
                    const ta = document.querySelector('textarea#chat-input');
                    if (!ta) return;
                    ta.focus();
                    const setter = Object.getOwnPropertyDescriptor(
                        HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    setter.call(ta, msg);
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    ta.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                message,
            )
        except Exception as e:
            Logger.debug(f"GLM Chat: JS text entry failed ({e}), falling back to .fill()")
            await textarea.first.fill(message)

    async def send_message(self, timeout: int | None = None) -> None:
        await self._send_message(timeout=timeout)

    async def _verify_send_clicked(self, poll_timeout: float = 1.5) -> bool:
        """
        Verify that the send button click actually registered.

        After a successful send, the send button's parent container changes its
        aria-label from "Send Message" to "Stop" (and the send button itself
        disappears). Poll for this state change to confirm the click went through.
        """
        if not self.page:
            return False

        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            try:
                result = await self.page.evaluate(
                    "() => {"
                    "  const btn = document.querySelector('button#send-message-button');"
                    "  if (!btn) return 'gone';"
                    "  const parent = btn.parentElement;"
                    "  if (!parent) return 'unknown';"
                    "  return (parent.getAttribute('aria-label') || '').trim().toLowerCase();"
                    "}"
                )
                if result == "gone" or result == "stop":
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.15)

        return False

    async def _click_stop_button(self) -> bool:
        if not self.page:
            return False

        stop_targets = (
            self.page.locator("div[aria-label='Stop']")
        )

        for target in stop_targets:
            try:
                if await target.count() <= 0:
                    continue
                button = target.first
                if not await button.is_visible():
                    continue
                try:
                    await button.scroll_into_view_if_needed(timeout=self._ui_timeout)
                except Exception:
                    pass
                await button.click(timeout=self._ui_timeout)
                Logger.debug("GLM Chat: Stop button clicked.")
                return True
            except Exception:
                continue

        try:
            clicked = await self.page.evaluate(
                """() => {
                    const match = document.querySelector("div[aria-label='Stop']");
                    if (!match) return false;
                    match.click();
                    return true;
                }"""
            )
            if clicked:
                Logger.debug("GLM Chat: Stop button clicked via JS fallback.")
                return True
        except Exception as e:
            Logger.debug(f"GLM Chat: JS stop click failed: {e}")

        Logger.debug("GLM Chat: Stop button not found.")
        return False

    async def _send_message(
        self, timeout: int | None = None, arm_event: asyncio.Event | None = None
    ) -> None:
        if not self.page:
            return

        send_button = self.page.locator("button#send-message-button")
        if await send_button.count() == 0:
            Logger.warning("GLM Chat: send button not found.")
            return

        if timeout and timeout > 0:
            start = time.time()
            while time.time() - start < timeout:
                try:
                    if not await send_button.first.is_disabled():
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.25)

        try:
            if await send_button.first.is_disabled():
                Logger.warning("GLM Chat: send button is disabled. Cannot send message.")
                return
        except Exception:
            pass

        # Brief stabilization delay to let the UI settle before clicking,
        # helps with long RPs where the button may not be fully interactive yet
        await asyncio.sleep(0.3)

        toaster = self.page.locator("ol[data-sonner-toaster]")
        max_retries = 5

        if arm_event:
            try:
                arm_event.set()
            except Exception:
                pass

        for attempt in range(max_retries):
            try:
                await send_button.first.click()
            except Exception as e:
                Logger.debug(f"GLM Chat: send button click failed: {e}")
                await asyncio.sleep(0.4)
                continue

            # Check if a "still uploading" toast appeared
            await asyncio.sleep(0.8)
            try:
                if await toaster.count() > 0:
                    toast_text = (await toaster.first.inner_text() or "").lower()
                    if "still uploading" in toast_text:
                        Logger.info(
                            f"GLM Chat: file still uploading (attempt {attempt + 1}/{max_retries}), "
                            f"waiting 3s before retry..."
                        )
                        await asyncio.sleep(3)
                        continue
            except Exception:
                pass

            # Verify the click actually registered (parent aria-label changes to "Stop")
            if await self._verify_send_clicked(poll_timeout=1.5):
                return

            # Playwright click didn't register -> try a direct JS click as fallback
            Logger.debug(
                f"GLM Chat: send click may not have registered (attempt {attempt + 1}/{max_retries}), "
                f"retrying with JS click..."
            )
            try:
                await self.page.evaluate(
                    "() => {"
                    "  const btn = document.querySelector('button#send-message-button');"
                    "  if (btn) btn.click();"
                    "}"
                )
            except Exception as e:
                Logger.debug(f"GLM Chat: JS click fallback failed: {e}")

            await asyncio.sleep(0.5)
            if await self._verify_send_clicked(poll_timeout=1.5):
                return

            Logger.debug(f"GLM Chat: send click not confirmed (attempt {attempt + 1}/{max_retries}).")
            await asyncio.sleep(0.3)

        Logger.warning("GLM Chat: send button click did not register after all retry attempts, giving up.")

    async def _click_regenerate(
        self,
        timeout_ms: int | None = None,
        arm_event: asyncio.Event | None = None,
    ) -> bool:
        if not self.page:
            return False

        timeout = self._ui_timeout if timeout_ms is None else max(int(timeout_ms), 0)
        deadline = time.time() + (float(timeout) / 1000.0 if timeout > 0 else 0.0)

        regen = self.page.locator("div[aria-label='Regenerate'] button")
        if await regen.count() == 0:
            regen = self.page.locator("[aria-label='Regenerate'] button")

        last_error: Exception | None = None

        while True:
            try:
                if await regen.count() > 0 and await regen.first.is_visible():
                    try:
                        aria_disabled = (await regen.first.get_attribute("aria-disabled") or "").strip().lower()
                        if aria_disabled == "true":
                            return False
                    except Exception:
                        pass

                    if arm_event:
                        try:
                            arm_event.set()
                        except Exception:
                            pass

                    try:
                        await regen.first.scroll_into_view_if_needed(timeout=self._ui_timeout)
                    except Exception:
                        pass

                    try:
                        await regen.first.click(timeout=self._ui_timeout)
                        return True
                    except Exception as e:
                        last_error = e

                    # Fallback: JS click (Playwright click can be swallowed by GLM's UI)
                    try:
                        clicked = await self.page.evaluate(
                            "() => {"
                            "  const btn = document.querySelector(\"div[aria-label='Regenerate'] button, [aria-label='Regenerate'] button\");"
                            "  if (!btn) return false;"
                            "  btn.click();"
                            "  return true;"
                            "}"
                        )
                        if clicked:
                            return True
                    except Exception as e:
                        last_error = e
            except Exception as e:
                last_error = e

            if timeout <= 0 or time.time() >= deadline:
                if last_error:
                    Logger.debug(f"GLM Chat: regenerate click failed: {last_error}")
                return False

            await asyncio.sleep(0.25)

    @staticmethod
    def _strip_details_tags(text: str) -> str:
        if not text:
            return ""
        # Remove opening <details ...> and closing </details> tags if present
        text = re.sub(r"<details[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"</details>", "", text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _strip_glm_blocks_from_stream_chunk(text: str, in_glm_block: bool) -> tuple[str, bool]:
        """
        Strip GLM's internal <glm_block ...>...</glm_block> tool payloads from the stream.

        These blocks contain tool/search metadata and results and should never be forwarded to the client.

        Returns (cleaned_text, new_in_glm_block_state).
        """
        if not text:
            return "", bool(in_glm_block)

        start_token = "<glm_block"
        end_token = "</glm_block>"

        out: list[str] = []
        i = 0
        active = bool(in_glm_block)

        while i < len(text):
            if active:
                end = text.find(end_token, i)
                if end == -1:
                    return "".join(out), True
                i = end + len(end_token)
                active = False
                continue

            start = text.find(start_token, i)
            if start == -1:
                # If we see a closing tag without a visible opening tag in this chunk,
                # assume we're still inside a block (e.g. the opening tag was split across
                # chunks) and drop everything up to and including the closing tag
                end = text.find(end_token, i)
                if end != -1:
                    i = end + len(end_token)
                    active = False
                    continue
                out.append(text[i:])
                return "".join(out), False

            out.append(text[i:start])
            end = text.find(end_token, start)
            if end == -1:
                return "".join(out), True
            i = end + len(end_token)
            active = False

        return "".join(out), active

    @staticmethod
    def _strip_partial_details_opening_tail(text: str) -> str:
        """
        GLM sometimes emits an edit_content patch that starts mid-way through the opening
        <details ...> tag (e.g. starts with: 'true" duration="5" ...>').

        In that case, strip the remaining tag attributes up to and including the first
        '>' so we don't leak raw HTML attributes into <think> output.
        """
        if not text:
            return ""

        preview = text[:200].lower()
        if "<details" in preview:
            return text

        # Heuristic: only strip when it looks like a details tag attribute tail
        if any(token in preview for token in ("done=", "duration=", "last_tool_call", "view=")):
            gt_idx = text.find(">")
            if 0 <= gt_idx <= 200:
                return text[gt_idx + 1 :].lstrip("\n\r")

        return text

    @classmethod
    def _extract_reasoning_from_edit_content(cls, text: str) -> str:
        if not text:
            return ""

        marker = "</details>"
        idx = text.find(marker)
        if idx == -1:
            return ""

        reasoning = text[:idx]
        reasoning = cls._strip_details_tags(reasoning)
        reasoning = cls._strip_partial_details_opening_tail(reasoning)
        return reasoning

    @staticmethod
    def _extract_answer_tail_from_edit_content(text: str) -> str:
        if not text:
            return ""
        marker = "</details>"
        idx = text.rfind(marker)
        if idx == -1:
            return ""
        return text[idx + len(marker) :].lstrip("\n\r")

    @staticmethod
    def _compute_missing_suffix(emitted: str, candidate: str) -> str:
        """
        Compute the text suffix that exists in candidate but has not yet been emitted.

        GLM can resend (or patch) the full reasoning/answer content via edit_content. We
        want to forward only the newly-added tail to avoid duplicate chunks.
        """
        if not candidate:
            return ""
        if not emitted:
            return candidate
        if candidate.startswith(emitted):
            return candidate[len(emitted) :]

        idx = candidate.rfind(emitted)
        if idx != -1:
            return candidate[idx + len(emitted) :]

        anchor_len = min(200, len(emitted))
        if anchor_len > 0:
            anchor = emitted[-anchor_len:]
            idx = candidate.rfind(anchor)
            if idx != -1:
                return candidate[idx + anchor_len :]

        max_check = min(500, len(emitted), len(candidate))
        for k in range(max_check, 0, -1):
            if emitted.endswith(candidate[:k]):
                return candidate[k:]

        # Avoid dumping the entire reasoning again if we failed to align
        if len(candidate) <= 800:
            return candidate
        return ""

    async def generate_response(
        self,
        message: Union[str, List[Any]],
        model: str = "glm-auto",
        stream: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        abort_event: asyncio.Event | None = None,
    ):
        _ = max_tokens
        response_queue: asyncio.Queue = asyncio.Queue()
        completion_armed = asyncio.Event()
        completion_started = asyncio.Event()
        completion_claim_lock = asyncio.Lock()
        completion_claimed = False
        intercepted_activity_count = 0
        intercepted_response: httpx.Response | None = None
        intercepted_request_abort = asyncio.Event()
        intercepted_request_finished = asyncio.Event()

        def get_intercepted_activity_count() -> int:
            return intercepted_activity_count

        async def abort_intercepted_request() -> None:
            intercepted_request_abort.set()
            response = intercepted_response
            if response is not None:
                try:
                    await response.aclose()
                except Exception as e:
                    Logger.debug(f"GLM Chat: failed to close intercepted response: {e}")
            try:
                await self._click_stop_button()
            except Exception as e:
                Logger.debug(f"GLM Chat: failed to click Stop during timeout handling: {e}")

        await self._await_pending_refresh_after_generation(abort_event=abort_event)

        await self.require_english_ui()
        self._refresh_quirks()

        # Reset state for new generation
        self.thinking_active = False
        self.abort_requested = False
        self.current_abort_event = abort_event
        resolved_model = (model or "").strip() or "glm-auto"
        self.current_model = resolved_model

        macros_overrides: Dict[str, bool] = {}
        message_for_formatting = message
        if isinstance(message, list):
            message_for_formatting, macros_overrides = self._strip_glm_macros_from_messages(message)
        elif isinstance(message, str):
            message_for_formatting, macros_overrides = self._extract_glm_macros_from_text(message)

        if macros_overrides:
            Logger.debug(f"GLM macros applied: {macros_overrides}")

        effective_settings = self._resolve_glm_request_settings(resolved_model, overrides=macros_overrides)
        effective_deepthink = effective_settings["deepthink_enabled"]
        effective_send_deepthink = effective_settings["send_deepthink"]
        enable_search = effective_settings["search_enabled"]
        send_as_text_file = effective_settings["send_as_text_file"]
        self.current_send_deepthink = effective_send_deepthink

        formatted_message = self._format_messages(message_for_formatting)
        glm_extra_prompt_texts: Dict[str, str] = {}
        if send_as_text_file:
            try:
                glm_text_file_filler = str(
                    self.config_manager.get_setting("glm_behavior", "text_file_filler") or "."
                )
            except Exception:
                glm_text_file_filler = "."
            if glm_text_file_filler.strip():
                glm_extra_prompt_texts["text_file_filler"] = glm_text_file_filler
        self._capture_diagnostics_prompt_snapshot(
            formatted_message,
            extra_prompt_texts=glm_extra_prompt_texts or None,
            metadata={
                "model": resolved_model,
                "ui_model": self._get_configured_glm_model_friendly(),
                "deepthink_enabled": bool(effective_deepthink),
                "send_deepthink": bool(effective_send_deepthink),
                "search_enabled": bool(enable_search),
                "send_as_text_file": bool(send_as_text_file),
            },
        )

        try:
            repetition_buster_enabled = bool(
                self.config_manager.get_setting("glm_behavior", "repetition_buster")
            )
        except Exception:
            repetition_buster_enabled = False
        try:
            clean_regeneration_requested = bool(
                self.config_manager.get_setting("glm_behavior", "clean_regeneration")
            )
        except Exception:
            clean_regeneration_requested = False
        try:
            multi_slot_cache_requested = bool(
                self.config_manager.get_setting("glm_behavior", "multi_slot_cache")
            )
        except Exception:
            multi_slot_cache_requested = False
        try:
            auto_delete_requested = bool(
                self.config_manager.get_setting("glm_behavior", "auto_delete_chats")
            )
        except Exception:
            auto_delete_requested = False

        if repetition_buster_enabled and clean_regeneration_requested:
            Logger.debug(
                "Repetition Buster (GLM): Clean Regeneration is also enabled in config, "
                "but Repetition Buster takes priority."
            )

        clean_regeneration = bool((not repetition_buster_enabled) and clean_regeneration_requested)
        multi_slot_cache_enabled = bool(clean_regeneration and multi_slot_cache_requested)
        auto_delete_enabled = bool(auto_delete_requested and (not clean_regeneration))
        if auto_delete_requested and clean_regeneration:
            Logger.warning(
                "GLM Chat: Delete Chat After Reply is skipped for this request because "
                "Reuse Matching Chat is enabled."
            )
        prompt_matches_last = False
        if repetition_buster_enabled:
            prompt_matches_last = self._account_scoped_cached_prompt_matches(
                self.cache_manager,
                self.repetition_buster_cache_key,
                formatted_message,
            )
        elif clean_regeneration:
            prompt_matches_last = self._cached_prompt_matches(
                self.cache_manager,
                self.clean_regen_message_cache_key,
                formatted_message,
            )

        if repetition_buster_enabled and prompt_matches_last:
            await self._run_repetition_buster(
                effective_deepthink=bool(effective_deepthink),
                enable_search=bool(enable_search),
                auto_delete_after_send=auto_delete_enabled,
            )

        async def handle_route(route):
            nonlocal completion_claimed, intercepted_activity_count, intercepted_response
            request = route.request

            # Ignore preflight and any requests we aren't actively expecting to stream.
            # GLM can sometimes fire background requests to the same endpoint.
            try:
                method = str(request.method or "").upper()
            except Exception:
                method = ""
            if method == "OPTIONS":
                await route.continue_()
                return

            if not completion_armed.is_set():
                await route.continue_()
                return

            async with completion_claim_lock:
                if completion_claimed:
                    await route.continue_()
                    return
                completion_claimed = True
                completion_started.set()

            Logger.info("Intercepting GLM Chat API request...")
            Logger.debug(f"Intercepted request to: {request.url}")

            headers = await request.all_headers()
            headers.pop("content-length", None)
            headers.pop("host", None)

            cookies = await self.context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}

            response_headers: Dict[str, str] = {}
            full_response_body = bytearray()
            aborted = False
            text_buffer = bytearray()
            text_buffer_pos = 0
            thinking_emitted = ""
            answer_emitted = False
            glm_block_active = False
            emitted_openai_chunk = False
            openai_usage: dict[str, Any] | None = None
            openai_usage_emitted = False
            openai_finish_emitted = False

            try:
                count_tokens_setting = self.config_manager.get_setting("glm_behavior", "count_tokens")
            except Exception:
                count_tokens_setting = None
            # Default to enabled, even if the setting isn't present (older configs)
            count_tokens_enabled = True if count_tokens_setting is None else bool(count_tokens_setting)

            def _normalize_openai_usage(raw: Any) -> dict[str, Any] | None:
                if not isinstance(raw, dict):
                    return None

                def _to_int(value: Any) -> int | None:
                    try:
                        return int(value)
                    except Exception:
                        return None

                prompt_tokens = _to_int(raw.get("prompt_tokens"))
                completion_tokens = _to_int(raw.get("completion_tokens"))
                total_tokens = _to_int(raw.get("total_tokens"))

                if prompt_tokens is None and completion_tokens is None and total_tokens is None:
                    return None

                prompt_tokens = 0 if prompt_tokens is None else max(prompt_tokens, 0)
                completion_tokens = 0 if completion_tokens is None else max(completion_tokens, 0)
                if total_tokens is None:
                    total_tokens = prompt_tokens + completion_tokens
                else:
                    total_tokens = max(total_tokens, 0)

                usage: dict[str, Any] = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }

                prompt_details = raw.get("prompt_tokens_details")
                if isinstance(prompt_details, dict):
                    usage["prompt_tokens_details"] = prompt_details

                completion_details = raw.get("completion_tokens_details")
                if isinstance(completion_details, dict):
                    usage["completion_tokens_details"] = completion_details

                return usage

            def enqueue_openai_delta(content: str, finish_reason: str | None = None) -> None:
                nonlocal emitted_openai_chunk
                if (not content) and (not finish_reason):
                    return
                model_name = self.current_model or "glm-auto"
                openai_chunk = {
                    "id": "chatcmpl-custom",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content} if content else {},
                            "finish_reason": finish_reason,
                        }
                    ],
                }
                response_queue.put_nowait(f"data: {json.dumps(openai_chunk)}\n\n")
                emitted_openai_chunk = True

            def enqueue_openai_usage(usage: dict[str, Any]) -> None:
                nonlocal emitted_openai_chunk, openai_usage_emitted
                if openai_usage_emitted:
                    return

                model_name = self.current_model or "glm-auto"
                openai_chunk = {
                    "id": "chatcmpl-custom",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [],
                    "usage": usage,
                }
                response_queue.put_nowait(f"data: {json.dumps(openai_chunk)}\n\n")
                emitted_openai_chunk = True
                openai_usage_emitted = True

            def process_sse_line(line: str) -> None:
                nonlocal thinking_emitted, answer_emitted, glm_block_active, openai_usage, openai_finish_emitted
                line = line.strip()
                if not line.startswith("data:"):
                    return

                data_str = line[len("data:") :].strip()
                if not data_str or data_str == "[DONE]":
                    return

                try:
                    payload = json.loads(data_str)
                except Exception:
                    return

                if not isinstance(payload, dict):
                    return

                payload_type = str(payload.get("type") or "").strip().lower()
                # Regeneration can use the same endpoint with slightly different type labels.
                if not payload_type.startswith("chat:completion"):
                    return

                data = payload.get("data")
                if not isinstance(data, dict):
                    return

                phase = str(data.get("phase") or "").strip().lower()

                if count_tokens_enabled:
                    normalized_usage = _normalize_openai_usage(data.get("usage"))
                    if normalized_usage:
                        openai_usage = normalized_usage

                if phase == "done" and bool(data.get("done")):
                    if not openai_finish_emitted:
                        if self.thinking_active and self.current_send_deepthink:
                            enqueue_openai_delta("</think>")
                            self.thinking_active = False
                        enqueue_openai_delta("", finish_reason="stop")
                        openai_finish_emitted = True
                    return

                delta_content = data.get("delta_content")
                edit_content = data.get("edit_content")

                if isinstance(delta_content, str):
                    if phase == "thinking":
                        if not self.current_send_deepthink:
                            return
                        if not self.thinking_active:
                            enqueue_openai_delta("<think>")
                            self.thinking_active = True
                        stripped = self._strip_details_tags(delta_content)
                        if stripped:
                            enqueue_openai_delta(stripped)
                            thinking_emitted += stripped
                        return

                    if phase == "answer":
                        if self.thinking_active and self.current_send_deepthink:
                            enqueue_openai_delta("</think>")
                            self.thinking_active = False
                        enqueue_openai_delta(delta_content)
                        answer_emitted = True
                        return

                    return

                if isinstance(edit_content, str):
                    edit_content, glm_block_active = self._strip_glm_blocks_from_stream_chunk(
                        edit_content, glm_block_active
                    )

                    # When thinking is enabled, GLM often sends a huge edit_content that includes the full
                    # <details> reasoning plus the first token(s) of the answer. Extract only the answer tail
                    if phase == "answer":
                        if self.current_send_deepthink and (self.thinking_active or not answer_emitted):
                            reasoning = self._extract_reasoning_from_edit_content(edit_content)
                            if reasoning:
                                missing = self._compute_missing_suffix(thinking_emitted, reasoning)
                                if missing:
                                    if not self.thinking_active:
                                        enqueue_openai_delta("<think>")
                                        self.thinking_active = True
                                    enqueue_openai_delta(missing)
                                    thinking_emitted += missing

                        if self.thinking_active and self.current_send_deepthink:
                            enqueue_openai_delta("</think>")
                            self.thinking_active = False
                        tail = self._extract_answer_tail_from_edit_content(edit_content)
                        if tail:
                            enqueue_openai_delta(tail)
                            answer_emitted = True
                        return

                    # GLM sometimes finalizes the answer with an "other" edit_content frame (tail append)
                    # If we ignore this, the client can miss the last chunk of the message
                    # So we handle it here
                    if phase == "other":
                        if self.thinking_active and self.current_send_deepthink:
                            enqueue_openai_delta("</think>")
                            self.thinking_active = False
                        if edit_content:
                            enqueue_openai_delta(edit_content)
                            answer_emitted = True
                        return

                    # At this point answer content may already be streaming via delta_content; only
                    # treat tool_call edit_content as answer tail if we've already emitted answer
                    if phase == "tool_call":
                        if self.thinking_active and self.current_send_deepthink:
                            enqueue_openai_delta("</think>")
                            self.thinking_active = False
                        if answer_emitted and edit_content:
                            enqueue_openai_delta(edit_content)
                            answer_emitted = True
                        return

            try:
                json_body = None
                raw_post_data = request.post_data
                if raw_post_data:
                    try:
                        json_body = request.post_data_json
                    except Exception:
                        json_body = None

                async with httpx.AsyncClient() as client:
                    try:
                        request_kwargs: Dict[str, Any] = {
                            "headers": headers,
                            "cookies": cookie_dict,
                            "timeout": 60.0,
                        }
                        if json_body is not None:
                            request_kwargs["json"] = json_body
                        elif raw_post_data:
                            request_kwargs["content"] = str(raw_post_data).encode("utf-8")

                        async with client.stream(
                            request.method,
                            request.url,
                            **request_kwargs,
                        ) as response:
                            intercepted_response = response
                            for k, v in response.headers.items():
                                response_headers[k] = v

                            async for chunk in response.aiter_bytes():
                                intercepted_activity_count += 1
                                if (
                                    intercepted_request_abort.is_set()
                                    or self.abort_requested
                                    or (abort_event and abort_event.is_set())
                                ):
                                    Logger.debug("Abort detected during GLM streaming, stopping...")
                                    aborted = True
                                    break

                                full_response_body.extend(chunk)
                                text_buffer.extend(chunk)

                                while True:
                                    newline_idx = text_buffer.find(b"\n", text_buffer_pos)
                                    if newline_idx == -1:
                                        break

                                    line_bytes = text_buffer[text_buffer_pos:newline_idx]
                                    text_buffer_pos = newline_idx + 1
                                    try:
                                        process_sse_line(
                                            bytes(line_bytes).decode("utf-8", errors="ignore")
                                        )
                                    except Exception:
                                        continue

                                # Periodically compact the buffer to avoid unbounded growth
                                if text_buffer_pos > 8192:
                                    del text_buffer[:text_buffer_pos]
                                    text_buffer_pos = 0

                            # Flush any final SSE line if the stream didn't end with a newline
                            tail = bytes(text_buffer[text_buffer_pos:])
                            if tail.strip():
                                process_sse_line(tail.decode("utf-8", errors="ignore"))
                            text_buffer.clear()
                            text_buffer_pos = 0

                            if (
                                (not aborted)
                                and (not intercepted_request_abort.is_set())
                                and (not self.abort_requested)
                                and count_tokens_enabled
                                and (openai_usage is not None)
                                and (not openai_usage_emitted)
                            ):
                                enqueue_openai_usage(openai_usage)
                    except httpx.ReadError as e:
                        if (
                            not aborted
                            and (not intercepted_request_abort.is_set())
                            and not self.abort_requested
                        ):
                            Logger.error(f"Read error during GLM intercepted request: {e}")
                            response_queue.put_nowait(f"data: {json.dumps({'error': str(e)})}\n\n")
                    except Exception as e:
                        if (
                            not aborted
                            and (not intercepted_request_abort.is_set())
                            and not self.abort_requested
                        ):
                            Logger.error(f"Error during GLM intercepted request: {e}")
                            response_queue.put_nowait(f"data: {json.dumps({'error': str(e)})}\n\n")
            except RuntimeError as e:
                if "async generator" in str(e) or "cancel scope" in str(e):
                    Logger.debug(f"Ignored expected error during abort: {e}")
                else:
                    raise
            finally:
                intercepted_response = None

            if aborted or intercepted_request_abort.is_set() or self.abort_requested:
                Logger.warning("GLM Chat generation was aborted before completion.")

            if (
                (not aborted)
                and (not intercepted_request_abort.is_set())
                and (not self.abort_requested)
                and (not emitted_openai_chunk)
            ):
                # Surface a helpful error instead of silently returning an empty stream.
                msg = (
                    "GLM Chat: intercepted completion produced no streamable output. "
                    "This may indicate a GLM API / frontend change."
                )
                Logger.warning(msg)
                response_queue.put_nowait(f"data: {json.dumps({'error': msg})}\n\n")

            try:
                if aborted or intercepted_request_abort.is_set() or self.abort_requested:
                    await route.abort()
                else:
                    await route.fulfill(body=bytes(full_response_body), status=200, headers=response_headers)
            except Exception as e:
                Logger.error(f"GLM Chat: error finalizing route: {e}")

            await response_queue.put(None)
            intercepted_request_finished.set()
            if (
                not aborted
                and (not intercepted_request_abort.is_set())
                and not self.abort_requested
            ):
                Logger.success("GLM Chat response streaming completed.")

        route_owner = self.context or self.page
        if not route_owner:
            raise RuntimeError("GLM Chat: browser context is not available.")

        await route_owner.route("**/api/v2/chat/completions**", handle_route)

        try:
            regenerated = False
            clean_regen_state: Dict[str, bool] | None = None
            multi_slot_state: Dict[str, Any] | None = None
            current_cache_matched = False
            should_record_multi_slot = False

            if clean_regeneration:
                clean_regen_state = {
                    "deepthink_enabled": bool(effective_deepthink),
                    "search_enabled": bool(enable_search),
                    "send_as_text_file": bool(send_as_text_file),
                    "ui_model": self._get_configured_glm_model_friendly(),
                }
                multi_slot_state = self._build_multi_slot_cache_state(
                    effective_deepthink=bool(effective_deepthink),
                    enable_search=bool(enable_search),
                    send_as_text_file=bool(send_as_text_file),
                )

                last_state = self._read_clean_regeneration_state()

                message_matches = prompt_matches_last
                state_matches = last_state == clean_regen_state

                if message_matches and state_matches:
                    current_cache_matched = True
                    Logger.info(
                        "Clean Regeneration (GLM): Message and settings match cache. Attempting to regenerate..."
                    )

                    #  toggles must match before regenerating (GLM UI can reset them on refresh)
                    try:
                        await self.set_deepthink_state(effective_deepthink)
                        await self.set_search_state(enable_search)
                        await asyncio.sleep(self._post_delay_s)
                    except Exception:
                        pass

                    regen_timeout = max(int(getattr(self, "_ui_timeout", 3000)), 5000)
                    if await self._click_regenerate(timeout_ms=regen_timeout, arm_event=completion_armed):
                        Logger.info("Clean Regeneration (GLM): Regenerate clicked. Regenerating...")
                        try:
                            await asyncio.wait_for(completion_started.wait(), timeout=20.0)
                        except asyncio.TimeoutError:
                            Logger.warning(
                                "Clean Regeneration (GLM): completion request not observed after clicking "
                                "Regenerate. Falling back to new chat."
                            )
                        else:
                            regenerated = True
                            self._write_cached_prompt(
                                self.cache_manager,
                                self.clean_regen_message_cache_key,
                                formatted_message,
                            )
                            self._write_clean_regeneration_state(clean_regen_state)
                    else:
                        Logger.warning(
                            "Clean Regeneration (GLM): Regenerate button not found/visible. Falling back to new chat."
                        )
                elif message_matches and not state_matches:
                    Logger.info(
                        "Clean Regeneration (GLM): Message matches cache but settings changed. Creating new chat."
                    )
                else:
                    Logger.debug("Clean Regeneration (GLM): Message differs from cache. Creating new chat.")

            if (
                (not regenerated)
                and multi_slot_cache_enabled
                and multi_slot_state
                and (not current_cache_matched)
            ):
                regenerated = await self._try_multi_slot_regeneration(
                    formatted_message=formatted_message,
                    multi_slot_state=multi_slot_state,
                    completion_armed=completion_armed,
                    completion_started=completion_started,
                )
                if regenerated and clean_regen_state:
                    self._write_cached_prompt(
                        self.cache_manager,
                        self.clean_regen_message_cache_key,
                        formatted_message,
                    )
                    self._write_clean_regeneration_state(clean_regen_state)

            if not regenerated:
                await self._prepare_new_chat_request_ui(
                    effective_deepthink=bool(effective_deepthink),
                    enable_search=bool(enable_search),
                )

                if send_as_text_file:
                    Logger.info("GLM Chat: sending message as text file...")
                    file_payload = {
                        "name": "prompt.txt",
                        "mimeType": "text/plain",
                        "buffer": formatted_message.encode("utf-8"),
                    }
                    await self._upload_file(file_payload)

                    # GLM requires some text alongside the file to enable the send button
                    filler = self.config_manager.get_setting("glm_behavior", "text_file_filler") or "."
                    await self._enter_message(str(filler))
                    # It Just Works™
                    # Copyright © ONCE IN A LIFETIME Bethesda Softworks LLC

                    upload_timeout = int(self.config_manager.get_setting("glm_behavior", "file_upload_timeout") or 15)
                    Logger.info("GLM Chat: sending request...")
                    await self._send_message(timeout=upload_timeout, arm_event=completion_armed)
                else:
                    await self._send_text_request(
                        formatted_message,
                        send_timeout=self._msg_send_timeout,
                        arm_event=completion_armed,
                    )

                if clean_regeneration and clean_regen_state:
                    self._write_cached_prompt(
                        self.cache_manager,
                        self.clean_regen_message_cache_key,
                        formatted_message,
                    )
                    self._write_clean_regeneration_state(clean_regen_state)
                    should_record_multi_slot = bool(multi_slot_cache_enabled and multi_slot_state)
                elif repetition_buster_enabled:
                    self._write_account_scoped_cached_prompt(
                        self.cache_manager,
                        self.repetition_buster_cache_key,
                        formatted_message,
                    )

            if not completion_started.is_set():
                try:
                    await asyncio.wait_for(completion_started.wait(), timeout=20.0)
                except asyncio.TimeoutError:
                    Logger.error(
                        "GLM Chat: completion request was not observed. "
                        "The UI may have swallowed the click or the endpoint changed."
                    )
                    yield f"data: {json.dumps({'error': 'GLM: completion request not observed'})}\n\n"
                    return

            stream_completed = True
            async for item in self._iterate_response_queue(
                response_queue,
                abort_event=abort_event,
                first_chunk_timeout_s=self._first_chunk_timeout_s,
                idle_timeout_s=self.INTERCEPT_IDLE_TIMEOUT_S,
                on_timeout=abort_intercepted_request,
                activity_counter=get_intercepted_activity_count,
            ):
                if isinstance(item, dict) and "error" in item:
                    stream_completed = False
                    yield f"data: {json.dumps(item)}\n\n"
                    break
                yield item

            if should_record_multi_slot and stream_completed and not self.abort_requested and not (abort_event and abort_event.is_set()):
                conversation_info = await self._wait_for_current_conversation_info(timeout_ms=6000)
                if conversation_info is None:
                    Logger.debug(
                        "Multi-Slot Cache (GLM): could not resolve conversation URL after generation; "
                        "skipping cache save."
                    )
                else:
                    upsert_multi_slot_cache_entry(
                        self.cache_manager,
                        self.multi_slot_cache_key,
                        self._get_multi_slot_cache_account_key(),
                        {
                            "conversation_id": conversation_info["conversation_id"],
                            "conversation_url": conversation_info["conversation_url"],
                            "prompt": formatted_message,
                            "state": multi_slot_state,
                        },
                        log_label="Multi-Slot Cache (GLM)",
                    )

            if stream_completed and not self.abort_requested and not (abort_event and abort_event.is_set()):
                self._schedule_refresh_after_generation()

            if (
                auto_delete_enabled
                and stream_completed
                and not self.abort_requested
                and not (abort_event and abort_event.is_set())
            ):
                await self._auto_delete_current_chat()

        finally:
            if completion_started.is_set() and not intercepted_request_finished.is_set():
                try:
                    await asyncio.wait_for(intercepted_request_finished.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    Logger.debug("GLM Chat: timed out waiting for intercepted request cleanup.")
            self.current_abort_event = None
            self.abort_requested = False
            self.current_model = None
            self.current_send_deepthink = None
            self.thinking_active = False
            try:
                await route_owner.unroute("**/api/v2/chat/completions**", handle_route)
            except Exception:
                try:
                    await route_owner.unroute("**/api/v2/chat/completions**")
                except Exception:
                    pass
