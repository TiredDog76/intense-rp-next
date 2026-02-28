import asyncio
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Union

import httpx
from dotenv import load_dotenv

from drivers.base_driver import BaseDriver
from drivers.providers import DriverProvider
from utils.cache_manager import CacheManager
from utils.logger import Logger
from utils.model_ids import MODE_CHAT, MODE_REASONER, resolve_behavior_mode

load_dotenv()


class GLMDriver(BaseDriver):
    CHAT_URL = "https://chat.z.ai/"
    AUTH_URL = "https://chat.z.ai/auth"

    REFRESH_AFTER_GENERATION_DELAY_S = 2.0

    MODEL_SELECTOR_BUTTON_SELECTOR = "button.modelSelectorButton"
    MODEL_DROPDOWN_ID = "f8T9iEf1QC"
    MODEL_DROPDOWN_SELECTOR = f"div#{MODEL_DROPDOWN_ID}"
    MODEL_DATA_VALUE_BY_FRIENDLY: Dict[str, str] = {
        "GLM-5": "glm-5",
        "GLM-4.7": "glm-4.7",
        "GLM-4.6": "GLM-4-6-API-V1",
    }

    # Models hidden behind a collapsible section in the dropdown
    MODELS_IN_COLLAPSIBLE: set = {"GLM-4.6"}

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
            refresh_after_generation = bool(
                self.config_manager.get_setting("glm_behavior", "refresh_after_generation")
            )
        except Exception:
            refresh_after_generation = False

        self._ui_timeout = max(ui_timeout, 500)
        self._post_delay_s = max(post_delay, 0) / 1000.0
        self._msg_send_timeout = max(msg_send_timeout, 1)
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
        self.cache_manager.clear_cache(self.clean_regen_message_cache_key)
        self.cache_manager.clear_cache(self.clean_regen_state_cache_key)

    async def apply_configured_model(self) -> None:
        desired_friendly = self._get_configured_glm_model_friendly()
        if not desired_friendly:
            return

        try:
            await self._ensure_glm_model_selected(desired_friendly)
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
        """Expand the collapsible section in the model dropdown (houses older models like GLM-4.6)."""
        if not self.page:
            return False

        try:
            trigger = self.page.locator("button[data-melt-collapsible-trigger]")
            if await trigger.count() == 0:
                return False

            await trigger.first.click(timeout=self._ui_timeout)

            # Wait for the content to appear
            content = self.page.locator("div[data-melt-collapsible-content]")
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

        option = self.page.locator(
            f"{self.MODEL_DROPDOWN_SELECTOR} button[data-value='{safe_value}']"
        )
        if await option.count() == 0:
            option = self.page.locator(f"button[data-value='{safe_value}']")

        count = await option.count()

        # If the option is not visible, it may be inside a collapsed section
        if count == 0 and friendly_name in self.MODELS_IN_COLLAPSIBLE:
            if await self._expand_collapsible_section():
                # Re-query after expanding
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
                if await cand.is_visible():
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

    async def _ensure_glm_model_selected(self, desired_friendly: str) -> None:
        if not self.page:
            return

        desired = str(desired_friendly or "").strip()
        if not desired:
            return

        desired_data_value = self.MODEL_DATA_VALUE_BY_FRIENDLY.get(desired)
        if not desired_data_value:
            Logger.warning(f"GLM Chat: unknown configured model '{desired}'.")
            return

        try:
            await self.page.wait_for_selector(self.MODEL_SELECTOR_BUTTON_SELECTOR, timeout=10000, state="visible")
        except Exception:
            Logger.warning("GLM Chat: model selector is not available yet.")
            return

        current_label = await self._read_current_glm_model_label()
        if self._normalize_model_label(current_label) == self._normalize_model_label(desired):
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

        ece_enabled = bool(self.config_manager.get_setting("experimental", "ece_enabled"))
        using_ece = False

        email = ""
        password = ""

        if ece_enabled:
            pair = self.ece_active_pair()
            if not pair:
                Logger.warning("ECE is enabled but no GLM credential pairs are configured. Waiting for manual login...")
                await self.page.goto(self.AUTH_URL)
                await self._wait_for_chat_ready(timeout_ms=None)
                Logger.success("GLM Chat: manual login detected.")
                return

            using_ece = True
            email = pair.email
            password = pair.password
        else:
            email = self.config_manager.get_setting("providers_credentials", "glm_email") or ""
            password = self.config_manager.get_setting("providers_credentials", "glm_password") or ""

        if not email or not password:
            Logger.error("GLM Chat email or password not found in settings.")
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

        if using_ece:
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
        if not text:
            return text, {}

        macro_actions: Dict[str, tuple[str, bool]] = {
            # Deep Think
            "think": ("deepthink_enabled", True),
            "r1": ("deepthink_enabled", True),
            "nothink": ("deepthink_enabled", False),
            "no_think": ("deepthink_enabled", False),
            "r0": ("deepthink_enabled", False),

            # Search
            "search": ("search_enabled", True),
            "nosearch": ("search_enabled", False),
            "no_search": ("search_enabled", False),
            "no-search": ("search_enabled", False),

            # Send as text file
            "file": ("send_as_text_file", True),
            "sendfile": ("send_as_text_file", True),
            "nofile": ("send_as_text_file", False),
            "no_file": ("send_as_text_file", False),
        }

        overrides: Dict[str, bool] = {}
        macro_pattern = re.compile(r"\[\[\s*([a-zA-Z0-9_-]+)\s*\]\]")

        def _replace_macro(match: re.Match) -> str:
            macro = (match.group(1) or "").strip().lower()
            action = macro_actions.get(macro)
            if not action:
                return match.group(0)

            key, value = action
            overrides[key] = value
            return ""

        cleaned = macro_pattern.sub(_replace_macro, text)
        return cleaned, overrides

    def _strip_glm_macros_from_messages(self, messages: List[Any]) -> tuple[List[Any], Dict[str, bool]]:
        last_user_index = None
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            role = ""
            if isinstance(msg, dict):
                role = str(msg.get("role", "") or "")
            else:
                try:
                    role = str(getattr(msg, "role", "") or "")
                except Exception:
                    role = ""
            if role.strip().lower() == "user":
                last_user_index = idx
                break

        if last_user_index is None:
            return messages, {}

        last_msg = messages[last_user_index]
        if isinstance(last_msg, dict):
            content = last_msg.get("content", "")
        else:
            try:
                content = getattr(last_msg, "content", "")
            except Exception:
                content = ""

        if not isinstance(content, str):
            return messages, {}

        cleaned_content, overrides = self._extract_glm_macros_from_text(content)
        if not overrides:
            return messages, {}

        cleaned_messages = list(messages)
        if isinstance(last_msg, dict):
            updated = dict(last_msg)
            updated["content"] = cleaned_content
            cleaned_messages[last_user_index] = updated
        else:
            role_value = ""
            name_value = None
            try:
                role_value = getattr(last_msg, "role", "")
            except Exception:
                role_value = ""
            try:
                name_value = getattr(last_msg, "name", None)
            except Exception:
                name_value = None

            updated = {"role": role_value, "content": cleaned_content}
            if name_value is not None:
                updated["name"] = name_value
            cleaned_messages[last_user_index] = updated

        return cleaned_messages, overrides

    def _read_clean_regeneration_state(self) -> Optional[Dict[str, bool]]:
        raw = self.cache_manager.read_cache(self.clean_regen_state_cache_key)
        if raw is None:
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            Logger.warning("Clean Regeneration (GLM): Cached state is invalid JSON, ignoring.")
            return None

        if not isinstance(data, dict):
            return None

        required_keys = ("deepthink_enabled", "search_enabled", "send_as_text_file")
        if not all(k in data for k in required_keys):
            return None

        return {
            "deepthink_enabled": bool(data.get("deepthink_enabled")),
            "search_enabled": bool(data.get("search_enabled")),
            "send_as_text_file": bool(data.get("send_as_text_file")),
        }

    def _write_clean_regeneration_state(self, state: Dict[str, bool]) -> None:
        payload = {
            "deepthink_enabled": bool(state.get("deepthink_enabled")),
            "search_enabled": bool(state.get("search_enabled")),
            "send_as_text_file": bool(state.get("send_as_text_file")),
        }
        self.cache_manager.write_cache(
            self.clean_regen_state_cache_key,
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        )

    def _format_messages(self, messages: Union[str, List[Any]]) -> str:
        """
        Applies formatting rules to the messages (shared behavior with DeepSeek).
        """
        apply_formatting = self.config_manager.get_setting("formatting", "apply_formatting")

        # If formatting is disabled, we still need to convert list to string if it's a list
        if not apply_formatting:
            if isinstance(messages, list):
                formatted_parts = []
                for msg in messages:
                    role = getattr(msg, "role", msg.get("role") if isinstance(msg, dict) else "")
                    content = getattr(msg, "content", msg.get("content") if isinstance(msg, dict) else "")
                    formatted_parts.append(f"{role}: {content}")
                return "\n".join(formatted_parts)
            return messages

        # 1. Parse Names
        user_name = "User"
        char_name = "Character"

        msgs_to_scan = messages if isinstance(messages, list) else []

        def _get_msg_field(msg: Any, key: str, default: Any = None) -> Any:
            try:
                value = getattr(msg, key)
            except Exception:
                value = None

            if value is not None:
                return value

            if isinstance(msg, dict):
                return msg.get(key, default)

            return default

        def _get_msg_name(msg: Any) -> Any:
            name_value = _get_msg_field(msg, "name")
            if name_value:
                return name_value
            return _get_msg_field(msg, "irp-next")  # For patcher compat

        if self.config_manager.get_setting("formatting", "enable_msg_objects"):
            for msg in msgs_to_scan:
                role = getattr(msg, "role", msg.get("role") if isinstance(msg, dict) else "")
                name = _get_msg_name(msg)
                if name:
                    if role == "user":
                        user_name = name
                    elif role == "assistant":
                        char_name = name

        enable_ir2 = self.config_manager.get_setting("formatting", "enable_ir2")
        enable_classic = self.config_manager.get_setting("formatting", "enable_classic_irp")

        if enable_ir2 or enable_classic:
            for msg in msgs_to_scan:
                role = getattr(msg, "role", msg.get("role") if isinstance(msg, dict) else "")
                content = getattr(msg, "content", msg.get("content") if isinstance(msg, dict) else "")

                if role == "system":
                    if enable_ir2:
                        ir2_match = re.search(r"\[\[IR2u\]\](.*?)\[\[/IR2u\]\]-\[\[IR2a\]\](.*?)\[\[/IR2a\]\]", content)
                        if ir2_match:
                            user_name = ir2_match.group(1)
                            char_name = ir2_match.group(2)

                    if enable_classic:
                        classic_match = re.search(r'DATA1: \"(.*?)\"\s*DATA2: \"(.*?)\"', content)
                        if classic_match:
                            char_name = classic_match.group(1)
                            user_name = classic_match.group(2)

        # 2. Format Messages
        template = self.config_manager.get_setting("formatting", "formatting_template") or ""
        divider = self.config_manager.get_setting("formatting", "formatting_divider") or ""

        template = str(template).replace("\\n", "\n")
        divider = str(divider).replace("\\n", "\n")

        formatted_parts = []

        if isinstance(messages, list):
            for msg in messages:
                role_raw = getattr(msg, "role", msg.get("role") if isinstance(msg, dict) else "")
                content = getattr(msg, "content", msg.get("content") if isinstance(msg, dict) else "")

                msg_name = None
                if self.config_manager.get_setting("formatting", "enable_msg_objects"):
                    msg_name = _get_msg_name(msg)

                display_role = "System"
                display_name = "System"

                if role_raw == "user":
                    display_role = "User"
                    display_name = msg_name if msg_name else user_name
                elif role_raw == "assistant":
                    display_role = "Character"
                    display_name = msg_name if msg_name else char_name

                part = (
                    template.replace("{{name}}", display_name)
                    .replace("{{role}}", display_role)
                    .replace("{{content}}", content)
                )
                formatted_parts.append(part)
        else:
            part = (
                template.replace("{{name}}", user_name)
                .replace("{{role}}", "User")
                .replace("{{content}}", messages)
            )
            formatted_parts.append(part)

        final_message = divider.join(formatted_parts)

        # 3. Injection
        injection_pos = self.config_manager.get_setting("formatting", "injection_position")
        injection_content = self.config_manager.get_setting("formatting", "injection_content")

        def _render_injection(text: str) -> str:
            rendered = "" if text is None else str(text)
            rendered = rendered.replace("{{user}}", user_name)
            rendered = rendered.replace("{{char}}", char_name)
            rendered = rendered.replace("{username}", user_name)
            rendered = rendered.replace("{asstname}", char_name)
            rendered = rendered.replace("{{username}}", user_name)
            rendered = rendered.replace("{{asstname}}", char_name)
            return rendered

        if injection_content:
            injection_content = _render_injection(injection_content)
            if injection_pos == "Before":
                final_message = injection_content + "\n" + final_message
            else:
                final_message = final_message + "\n" + injection_content

        return final_message

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

        selector = "button#sidebar-new-chat-button" if is_open else "button#new-chat-button"
        btn = self.page.locator(selector)
        if await btn.count() == 0:
            Logger.warning("GLM Chat: New Chat button not found.")
            return

        try:
            await btn.first.click(timeout=self._ui_timeout)
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
        abort_event: asyncio.Event | None = None,
    ):
        response_queue: asyncio.Queue = asyncio.Queue()
        completion_armed = asyncio.Event()
        completion_started = asyncio.Event()
        completion_claim_lock = asyncio.Lock()
        completion_claimed = False

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

        async def handle_route(route):
            nonlocal completion_claimed
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
                            for k, v in response.headers.items():
                                response_headers[k] = v

                            async for chunk in response.aiter_bytes():
                                if self.abort_requested or (abort_event and abort_event.is_set()):
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
                                and (not self.abort_requested)
                                and count_tokens_enabled
                                and (openai_usage is not None)
                                and (not openai_usage_emitted)
                            ):
                                enqueue_openai_usage(openai_usage)
                    except httpx.ReadError as e:
                        if not aborted and not self.abort_requested:
                            Logger.error(f"Read error during GLM intercepted request: {e}")
                            response_queue.put_nowait(f"data: {json.dumps({'error': str(e)})}\n\n")
                    except Exception as e:
                        if not aborted and not self.abort_requested:
                            Logger.error(f"Error during GLM intercepted request: {e}")
                            response_queue.put_nowait(f"data: {json.dumps({'error': str(e)})}\n\n")
            except RuntimeError as e:
                if "async generator" in str(e) or "cancel scope" in str(e):
                    Logger.debug(f"Ignored expected error during abort: {e}")
                else:
                    raise

            if aborted or self.abort_requested:
                Logger.warning("GLM Chat generation aborted by user.")

            if (not aborted) and (not self.abort_requested) and (not emitted_openai_chunk):
                # Surface a helpful error instead of silently returning an empty stream.
                msg = (
                    "GLM Chat: intercepted completion produced no streamable output. "
                    "This may indicate a GLM API / frontend change."
                )
                Logger.warning(msg)
                response_queue.put_nowait(f"data: {json.dumps({'error': msg})}\n\n")

            try:
                await route.fulfill(body=bytes(full_response_body), status=200, headers=response_headers)
            except Exception as e:
                Logger.error(f"GLM Chat: error fulfilling route: {e}")

            await response_queue.put(None)
            if not aborted and not self.abort_requested:
                Logger.success("GLM Chat response streaming completed.")

        route_owner = self.context or self.page
        if not route_owner:
            raise RuntimeError("GLM Chat: browser context is not available.")

        await route_owner.route("**/api/v2/chat/completions**", handle_route)

        try:
            clean_regeneration = bool(self.config_manager.get_setting("glm_behavior", "clean_regeneration"))
            regenerated = False
            clean_regen_state: Dict[str, bool] | None = None

            if clean_regeneration:
                clean_regen_state = {
                    "deepthink_enabled": bool(effective_deepthink),
                    "search_enabled": bool(enable_search),
                    "send_as_text_file": bool(send_as_text_file),
                }

                last_message = self.cache_manager.read_cache(self.clean_regen_message_cache_key)
                last_state = self._read_clean_regeneration_state()

                message_matches = last_message == formatted_message
                state_matches = last_state == clean_regen_state

                if message_matches and state_matches:
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
                            self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
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

            if not regenerated:
                Logger.info("GLM Chat: preparing new chat session...")
                await self.click_new_chat(source="auto")
                await asyncio.sleep(self._post_delay_s)

                await self.apply_configured_model()

                await self.set_deepthink_state(effective_deepthink)
                await self.set_search_state(enable_search)
                await asyncio.sleep(self._post_delay_s)

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
                    await self._enter_message(formatted_message)
                    await asyncio.sleep(self._post_delay_s)
                    Logger.info("GLM Chat: sending request...")
                    await self._send_message(timeout=self._msg_send_timeout, arm_event=completion_armed)

                if clean_regeneration and clean_regen_state:
                    self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                    self._write_clean_regeneration_state(clean_regen_state)

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

            stream_completed = False
            while True:
                if self.abort_requested or (abort_event and abort_event.is_set()):
                    Logger.debug("Abort detected in GLM response loop, breaking...")
                    break

                item = await response_queue.get()
                if item is None:
                    stream_completed = True
                    break
                if isinstance(item, dict) and "error" in item:
                    yield f"data: {json.dumps(item)}\n\n"
                    break
                yield item

            if stream_completed:
                self._schedule_refresh_after_generation()

        finally:
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
