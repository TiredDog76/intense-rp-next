import asyncio
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
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
    format_messages,
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


class QwenLMDriver(BaseDriver):
    CHAT_URL = "https://chat.qwen.ai/"
    AUTH_URL = "https://chat.qwen.ai/auth"
    SETTINGS_URL = "https://chat.qwen.ai/api/v2/users/user/settings"
    SETTINGS_UPDATE_URL = "https://chat.qwen.ai/api/v2/users/user/settings/update"
    CONVERSATION_URL_RE = re.compile(r"^https://chat\.qwen\.ai/c/([^/?#]+)", re.IGNORECASE)
    INTERCEPT_FIRST_CHUNK_TIMEOUT_S = 45.0
    INTERCEPT_IDLE_TIMEOUT_S = 75.0

    COMPLETIONS_ROUTE_GLOB = "**/api/v2/chat/completions*"

    CHAT_TEXTAREA_SELECTOR = "textarea.message-input-textarea"
    SEND_BUTTON_SELECTOR = "div.chat-prompt-send-button button"
    FILE_INPUT_SELECTOR = "input#filesUpload"

    SIDEBAR_SELECTOR = "div.sidebar"
    SIDEBAR_OPEN_BUTTON_SELECTOR = "div.sidebar-side-fold-container-open"
    SIDEBAR_CLOSE_BUTTON_SELECTOR = "button.sidebar-toggle-button"
    NEW_CHAT_BUTTON_SELECTOR = "div.sidebar-entry-list > :first-child"

    THINKING_TRIGGER_SELECTOR = "span.ant-select-selection-item:has(div.qwen-select-thinking-label)"
    THINKING_LABEL_SELECTOR = "span.qwen-select-thinking-label-text"
    THINKING_OPTIONS_SELECTOR = "div.rc-virtual-list-holder-inner"

    SEARCH_MODE_CONTAINER_SELECTOR = "div.mode-select-current-mode"
    SEARCH_CLOSE_SELECTOR = "span.mode-select-current-mode-close"
    SEARCH_ENABLE_ANCHOR = "a2ty_o01.29997169.0.i44.3d4d5171h8MbwS"
    SEARCH_ENABLED_ANCHOR = "a2ty_o01.29997169.0.i49.3d4d5171h8MbwS"
    MODE_SELECT_TRIGGER_SELECTOR = "div.mode-select"
    MODE_SELECT_TRIGGER_OPEN_SELECTOR = "div.mode-select-open"
    MODE_SELECT_TRIGGER_ANY_SELECTOR = "div.mode-select-open, div.mode-select"
    MODE_SELECT_DROPDOWN_MENU_ROOT_SELECTOR = "ul.ant-dropdown-menu-root.qwen-dropdown-menu"
    MODE_SELECT_COMMON_SUBMENU_SELECTOR = (
        "li.ant-dropdown-menu-submenu.ant-dropdown-menu-submenu-vertical.mode-select-common-item"
    )
    MODE_SELECT_MENU_ITEM_SELECTOR = "li[data-menu-id]"

    MODEL_SELECTOR_TEXT_SELECTOR = "[class*='model-selector-text']"
    MODEL_SELECTOR_POPUP_SELECTOR = "div[class*='model-selector-popup']"

    MODEL_LABELS: List[str] = [
        "Qwen3.5-Plus",
        "Qwen3.5-Flash",
        "Qwen3.5-397B-A17B",
        "Qwen3.5-122B-A10B",
        "Qwen3.5-27B",
        "Qwen3.5-35B-A3B",
        "Qwen3-Max",
        "Qwen3-235B-A22B-2507",
        "Qwen3-Coder",
        "Qwen3-VL-235B-A22B",
        "Qwen3-Omni-Flash",
        "Qwen2.5-Max",
    ]

    def __init__(self, config_manager):
        super().__init__(config_manager=config_manager, provider=DriverProvider.QWEN_LM)
        self.cache_manager = CacheManager()

        # Qwen UI language detection (we refuse to operate unless the UI is English)
        self.last_document_lang: Optional[str] = None
        self.ui_language_ok: Optional[bool] = None
        self._non_english_ui_warned = False
        self._non_english_ui_warned_lang: Optional[str] = None

        self.current_model: Optional[str] = None
        self.current_send_deepthink: Optional[bool] = None
        self.thinking_active = False

        self.clean_regen_message_cache_key = "qwen_last_message.txt"
        self.clean_regen_state_cache_key = "qwen_last_message_state.json"
        self.multi_slot_cache_key = "qwen_multi_slot_cache.json"

        # Best-effort provider settings enforcement (once per session, can be retried)
        self._rp_settings_last_attempt_ts: float = 0.0
        self._abort_ui_task: asyncio.Task | None = None

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

        # Qwen has a few RP-unfriendly settings that can silently change how prompts are sent
        # we send them settings update requests to clear them up
        try:
            await self._wait_for_chat_ready(timeout_ms=60000)
            changed = await self._ensure_rp_friendly_settings()
            if changed and self.page:
                Logger.info("QwenLM: reloading chat to apply updated settings...")
                try:
                    await self.page.reload(wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    Logger.warning(f"QwenLM: reload after settings update failed: {e}")
                else:
                    await self._wait_for_chat_ready(timeout_ms=60000)
        except Exception as e:
            Logger.warning(f"QwenLM: settings enforcement skipped/failed: {e}")

    async def cleanup_background_tasks(self) -> None:
        await self._cancel_task(
            self._abort_ui_task,
            label="stopping QwenLM abort UI task",
        )
        self._abort_ui_task = None

    def request_abort(self) -> None:
        super().request_abort()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        try:
            existing = getattr(self, "_abort_ui_task", None)
            if existing and (not existing.done()):
                return
        except Exception:
            pass

        try:
            self._abort_ui_task = loop.create_task(self._abort_generation_ui())
        except Exception:
            pass

    async def abort_generation(self) -> None:
        Logger.info("QwenLM: abort generation requested...")
        self.abort_requested = True
        if self.current_abort_event:
            try:
                self.current_abort_event.set()
            except Exception:
                pass
        await self._click_stop_button(timeout_s=12.0)

    async def _abort_generation_ui(self) -> None:
        try:
            await self._click_stop_button(timeout_s=12.0)
        except Exception as e:
            Logger.debug(f"QwenLM: abort UI click failed: {e}")

    async def _click_stop_button(self, timeout_s: float = 12.0) -> bool:
        if not self.page:
            return False

        deadline = time.time() + max(float(timeout_s or 0.0), 0.0)
        container = self.page.locator("div.chat-prompt-send-button")
        buttons = container.locator("button")

        while True:
            if timeout_s and (time.time() >= deadline):
                Logger.warning("QwenLM: stop button did not become clickable before timeout.")
                return False

            count = 0
            try:
                count = await buttons.count()
            except Exception:
                count = 0

            any_visible = False
            clicked = False
            stop_present = False

            for idx in range(count - 1, -1, -1):
                btn = buttons.nth(idx)
                try:
                    if not await btn.is_visible():
                        continue
                except Exception:
                    continue

                any_visible = True

                cls = ""
                try:
                    cls = str(await btn.get_attribute("class") or "")
                except Exception:
                    cls = ""

                is_stop = "stop-button" in cls
                if not is_stop:
                    # If it isn't a stop button anymore, generation likely finished
                    return False

                stop_present = True

                disabled_attr = None
                aria_disabled = ""
                try:
                    disabled_attr = await btn.get_attribute("disabled")
                except Exception:
                    disabled_attr = None
                try:
                    aria_disabled = str(await btn.get_attribute("aria-disabled") or "").strip().lower()
                except Exception:
                    aria_disabled = ""

                is_enabled = True
                try:
                    is_enabled = await btn.is_enabled()
                except Exception:
                    is_enabled = True

                if disabled_attr is not None or aria_disabled == "true" or (not is_enabled):
                    # Stop exists but isn't clickable yet. Keep waiting
                    break

                try:
                    await btn.click(timeout=2000)
                    clicked = True
                    break
                except Exception:
                    try:
                        await btn.evaluate("el => el.click()")
                        clicked = True
                        break
                    except Exception:
                        break

            if clicked:
                return True

            if (count == 0) or (not any_visible):
                # No button visible - treat as finished/not generating
                return False

            if not stop_present:
                return False

            await asyncio.sleep(0.1)

    async def _wait_for_chat_ready(self, timeout_ms: int | None = 60000) -> None:
        if not self.page:
            raise RuntimeError("Page is not initialized.")

        await self.page.wait_for_selector(self.CHAT_TEXTAREA_SELECTOR, timeout=timeout_ms or 0)

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
            Logger.debug(f"QwenLM: failed to read document language: {e}")
            return ""

        return str(lang or "").strip()

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

        if (not self._non_english_ui_warned) or (self._non_english_ui_warned_lang != lang):
            self._non_english_ui_warned = True
            self._non_english_ui_warned_lang = lang

            detected = lang or "<unset>"
            Logger.warning(
                f"QwenLM UI language detected as '{detected}'. "
                "IntenseRP currently requires QwenLM UI language to be English (en-US). "
                "Please change QwenLM language to English and reload the page."
            )
            if status_callback:
                status_callback("QwenLM UI language is not English. Please change it to English (en-US).")

        return False

    async def require_english_ui(self) -> None:
        ok = await self.check_ui_language()
        if ok:
            return

        detected = self.last_document_lang or "<unset>"
        raise RuntimeError(
            f"QwenLM UI language is not English (detected: {detected}). "
            "IntenseRP currently requires QwenLM UI language to be English (en-US). "
            "Please change QwenLM language to English and reload the page."
        )

    async def _has_token_cookie(self) -> bool:
        context = getattr(self, "context", None)
        if not context:
            return False

        try:
            cookies = await context.cookies()
        except Exception:
            return False

        for cookie in cookies:
            try:
                name = str(cookie.get("name") or "")
                value = str(cookie.get("value") or "")
                domain = str(cookie.get("domain") or "")
            except Exception:
                continue
            if name == "token" and value and ("qwen.ai" in domain):
                return True

        return False

    async def login(self) -> None:
        if not self.page:
            raise RuntimeError("Page is not initialized.")

        try:
            if await self._has_token_cookie():
                Logger.info("QwenLM: already signed in.")
                self._mark_active_ece_pair_used()
                return
        except Exception:
            pass

        auto_login = False
        try:
            auto_login = bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
        except Exception:
            auto_login = False

        # Always land on the auth page when we need to sign in
        try:
            await self.page.goto(self.AUTH_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass

        if not auto_login:
            Logger.info("QwenLM: Auto Login disabled. Waiting for manual login...")
            self.notify_user(
                "QwenLM Login",
                "Please log in to QwenLM in the browser window, then come back here.",
                level="info",
            )
            # Wait indefinitely until we can see a session cookie and the chat UI
            while True:
                if await self._has_token_cookie():
                    break
                await asyncio.sleep(0.5)
            await self.page.goto(self.CHAT_URL, wait_until="domcontentloaded", timeout=45000)
            await self._wait_for_chat_ready(timeout_ms=60000)
            Logger.success("QwenLM: login detected.")
            self._mark_active_ece_pair_used()
            return

        pair = self.ece_active_pair()
        if not pair:
            Logger.warning(
                "QwenLM: Auto-login is enabled but no accounts are configured in Credential Manager. "
                "Waiting for manual login..."
            )
            self.notify_user(
                "QwenLM Login",
                "Auto Login is enabled, but no QwenLM accounts are saved. Please log in manually.",
                level="warning",
            )
            while True:
                if await self._has_token_cookie():
                    break
                await asyncio.sleep(0.5)
            await self.page.goto(self.CHAT_URL, wait_until="domcontentloaded", timeout=45000)
            await self._wait_for_chat_ready(timeout_ms=60000)
            Logger.success("QwenLM: login detected.")
            self._mark_active_ece_pair_used()
            return

        email = str(pair.email or "").strip()
        password = str(pair.password or "")
        if not email or not password:
            Logger.error("QwenLM account is missing an email or password.")
            return

        Logger.info("QwenLM: Auto-login enabled. Attempting login...")

        try:
            await self.page.wait_for_selector(".qwenchat-auth-pc-input-items", timeout=30000)
        except Exception as e:
            Logger.error(f"QwenLM: login form not found: {e}")
            return

        try:
            root = self.page.locator(".qwenchat-auth-pc-input-items")

            email_input = root.first.locator("input:not([type='password'])")
            if await email_input.count() == 0:
                email_input = self.page.locator("input:not([type='password'])")
            await email_input.first.fill(email)

            password_input = self.page.locator("input[type='password']")
            await password_input.first.fill(password)

            submit = self.page.locator("button.qwenchat-auth-pc-submit-button")
            await submit.first.click()
        except Exception as e:
            Logger.error(f"QwenLM: failed to fill credentials/click submit: {e}")
            return

        self.notify_user(
            "QwenLM Login",
            "If QwenLM asks for extra confirmation, please complete it in the browser window.",
            level="info",
        )

        # Wait for cookie + chat UI
        try:
            await asyncio.wait_for(self._wait_for_token_cookie(), timeout=90.0)
        except asyncio.TimeoutError:
            Logger.warning("QwenLM: login cookie not detected after submit. Waiting for manual completion...")
            await self._wait_for_token_cookie()

        try:
            await self.page.goto(self.CHAT_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass

        await self._wait_for_chat_ready(timeout_ms=60000)
        Logger.success("QwenLM: chat ready.")
        self.ece_mark_used(email)

    async def _wait_for_token_cookie(self) -> None:
        while True:
            if await self._has_token_cookie():
                return
            await asyncio.sleep(0.5)

    def _resolve_deepthink_flags(self, model: str) -> tuple[bool, bool]:
        enable_deepthink = bool(self.config_manager.get_setting("qwen_behavior", "enable_deepthink"))
        send_deepthink = bool(self.config_manager.get_setting("qwen_behavior", "send_deepthink"))

        mode = resolve_behavior_mode(model, self.provider)
        if mode == MODE_CHAT:
            return False, False
        if mode == MODE_REASONER:
            return True, send_deepthink

        return enable_deepthink, send_deepthink

    def _resolve_qwen_request_settings(self, model: str, overrides: Optional[Dict[str, bool]] = None) -> Dict[str, bool]:
        resolved_model = (model or "").strip() or "qwen-auto"
        deepthink_enabled, send_deepthink = self._resolve_deepthink_flags(resolved_model)
        enable_search = bool(self.config_manager.get_setting("qwen_behavior", "enable_search"))
        send_as_text_file = bool(self.config_manager.get_setting("qwen_behavior", "send_as_text_file"))

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

    def _extract_qwen_macros_from_text(self, text: str) -> tuple[str, Dict[str, bool]]:
        return extract_macro_overrides(text, macro_actions=COMMON_REQUEST_MACRO_ACTIONS)

    def _strip_qwen_macros_from_messages(self, messages: List[Any]) -> tuple[List[Any], Dict[str, bool]]:
        return strip_macros_from_messages(messages, macro_actions=COMMON_REQUEST_MACRO_ACTIONS)

    def _read_clean_regeneration_state(self) -> Optional[Dict[str, bool]]:
        return read_clean_regeneration_state(
            self.cache_manager,
            self.clean_regen_state_cache_key,
            log_label="Clean Regeneration (QwenLM)",
        )

    def _write_clean_regeneration_state(self, state: Dict[str, bool]) -> None:
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
            "ui_model": self._get_configured_qwen_model_label(),
        }

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
            "conversation_url": f"https://chat.qwen.ai/c/{conversation_id}",
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

    async def _open_cached_conversation(self, conversation_url: str) -> bool:
        if not self.page:
            return False

        target_url = str(conversation_url or "").strip()
        if not target_url:
            return False

        try:
            await self.page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            Logger.warning(f"Multi-Slot Cache (QwenLM): failed to open cached chat URL: {e}")
            return False

        try:
            await self._wait_for_chat_ready(timeout_ms=60000)
        except Exception as e:
            Logger.warning(f"Multi-Slot Cache (QwenLM): chat shell did not become ready: {e}")
            return False

        try:
            if not await self._has_token_cookie():
                Logger.warning("Multi-Slot Cache (QwenLM): cached chat URL is not available for the active session.")
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
            log_label="Multi-Slot Cache (QwenLM)",
        )
        entry = find_multi_slot_cache_entry(payload, account_key, formatted_message, multi_slot_state)
        if entry is None:
            return False

        current_info = await self._get_current_conversation_info()
        if current_info is None or current_info["conversation_id"] != entry["conversation_id"]:
            Logger.info("Multi-Slot Cache (QwenLM): opening cached conversation for regeneration...")
            opened = await self._open_cached_conversation(entry["conversation_url"])
            if not opened:
                return False
            current_info = await self._get_current_conversation_info()
            if current_info is None or current_info["conversation_id"] != entry["conversation_id"]:
                Logger.warning(
                    "Multi-Slot Cache (QwenLM): cached conversation URL opened, but the expected "
                    "chat ID was not available. Falling back to a new chat."
                )
                return False

        try:
            await self.apply_configured_model()
            await self.set_deepthink_state(bool(multi_slot_state.get("deepthink_enabled")))
            await self.set_search_state(bool(multi_slot_state.get("search_enabled")))
            await asyncio.sleep(0.25)
        except Exception:
            pass

        Logger.info("Multi-Slot Cache (QwenLM): cached prompt match found. Attempting to regenerate...")
        if not await self._click_regenerate(arm_event=completion_armed):
            Logger.warning(
                "Multi-Slot Cache (QwenLM): regenerate button unavailable. Removing cached entry."
            )
            remove_multi_slot_cache_entry(
                self.cache_manager,
                self.multi_slot_cache_key,
                account_key,
                entry["conversation_id"],
                log_label="Multi-Slot Cache (QwenLM)",
            )
            return False

        try:
            await asyncio.wait_for(completion_started.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            Logger.warning(
                "Multi-Slot Cache (QwenLM): completion request not observed after clicking "
                "Regenerate. Removing cached entry."
            )
            remove_multi_slot_cache_entry(
                self.cache_manager,
                self.multi_slot_cache_key,
                account_key,
                entry["conversation_id"],
                log_label="Multi-Slot Cache (QwenLM)",
            )
            return False

        return True

    async def _ensure_rp_friendly_settings(self) -> bool:
        if not self.page:
            return False

        # Don't spam settings calls; this is just a "guardrail" feature
        now = time.time()
        last_attempt = float(getattr(self, "_rp_settings_last_attempt_ts", 0.0) or 0.0)
        if (now - last_attempt) < 15.0:
            return False
        self._rp_settings_last_attempt_ts = now

        Logger.info("QwenLM: checking RP-friendly provider settings...")

        settings: Any = None
        try:
            settings = await self.page.evaluate(
                "() => fetch('/api/v2/users/user/settings', { credentials: 'include' })"
                ".then(r => r.json()).catch(() => null)"
            )
        except Exception as e:
            Logger.warning(f"QwenLM: failed to fetch user settings: {e}")
            settings = None

        def _flag_is_true(value: Any) -> bool:
            if value is True:
                return True
            if value is False or value is None:
                return False
            if isinstance(value, (int, float)):
                return value != 0
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
            return False

        desired: list[dict[str, Any]] = []

        if isinstance(settings, dict):
            data = settings.get("data")
        else:
            data = None

        def _must_force_false(section: Any, key: str) -> bool:
            if not isinstance(section, dict):
                return True
            if key not in section:
                return True
            return _flag_is_true(section.get(key))

        if isinstance(data, dict):
            ui = data.get("ui")
            memory = data.get("memory")

            if _must_force_false(ui, "largeTextAsFile"):
                desired.append({"ui": {"largeTextAsFile": False}})
            if _must_force_false(ui, "splitLargeChunks"):
                desired.append({"ui": {"splitLargeChunks": False}})
            if _must_force_false(memory, "enable_memory"):
                desired.append({"memory": {"enable_memory": False}})
            if _must_force_false(memory, "enable_history_memory"):
                desired.append({"memory": {"enable_history_memory": False}})

        if not desired:
            # if we couldn't read settings, still try a safe, idempotent "set to false" pass
            if not isinstance(data, dict):
                Logger.warning(
                    "QwenLM: could not read user settings (unexpected response). Attempting blind settings update..."
                )
                desired = [
                    {"ui": {"largeTextAsFile": False}},
                    {"ui": {"splitLargeChunks": False}},
                    {"memory": {"enable_memory": False}},
                    {"memory": {"enable_history_memory": False}},
                ]
            else:
                Logger.info("QwenLM: RP-friendly settings already look OK.")
                return False

        Logger.info(f"QwenLM: applying {len(desired)} settings tweak(s) for RP compatibility...")

        results: Any = None
        try:
            results = await self.page.evaluate(
                "async (updates) => {"
                "  const sleep = (ms) => new Promise(r => setTimeout(r, ms));"
                "  const out = [];"
                "  for (const body of (updates || [])) {"
                "    try {"
                "      const resp = await fetch('/api/v2/users/user/settings/update', {"
                "        method: 'POST',"
                "        credentials: 'include',"
                "        headers: { 'Content-Type': 'application/json' },"
                "        body: JSON.stringify(body),"
                "      });"
                "      let success = null;"
                "      try {"
                "        const j = await resp.json();"
                "        if (j && typeof j === 'object' && ('success' in j)) success = !!j.success;"
                "      } catch (e) { success = null; }"
                "      out.push({ ok: !!resp.ok, status: (resp.status || 0), success });"
                "    } catch (e) {"
                "      out.push({ ok: false, status: 0, error: String(e) });"
                "    }"
                "    await sleep(220);"
                "  }"
                "  return out;"
                "}",
                desired,
            )
        except Exception as e:
            Logger.warning(f"QwenLM: settings update calls failed: {e}")
            return True

        try:
            if isinstance(results, list) and results:
                ok_count = 0
                for r in results:
                    if isinstance(r, dict) and r.get("ok") is True:
                        ok_count += 1
                if ok_count != len(results):
                    Logger.warning(
                        f"QwenLM: {len(results) - ok_count}/{len(results)} settings update request(s) failed."
                    )
                    Logger.debug(f"QwenLM: settings update results: {results}")
        except Exception:
            pass

        return True

    async def apply_configured_model(self) -> None:
        desired = self._get_configured_qwen_model_label()
        if not desired:
            return

        try:
            await self._ensure_qwen_model_selected(desired)
        except Exception as e:
            Logger.warning(f"QwenLM: Failed to apply model selection '{desired}': {e}")

    def _get_configured_qwen_model_label(self) -> str:
        try:
            value = self.config_manager.get_setting("qwen_behavior", "model")
        except Exception:
            value = None
        return str(value or "").strip()

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().lower()

    @staticmethod
    def _canonicalize_model_label(value: str) -> str:
        normalized = QwenLMDriver._normalize_text(value)
        try:
            normalized = unicodedata.normalize("NFKC", normalized)
            normalized = (
                normalized.replace("\u200b", "")
                .replace("\u200c", "")
                .replace("\u200d", "")
                .replace("\ufeff", "")
            )
        except Exception:
            pass
        return re.sub(r"[^a-z0-9]+", "", normalized)

    async def _read_current_qwen_model_label(self) -> str:
        if not self.page:
            return ""

        try:
            label = await self.page.evaluate(
                "() => {"
                "  const el = document.querySelector(\"[class*='model-selector-text']\");"
                "  if (!el) return '';"
                "  return (el.textContent || '').toString().trim();"
                "}"
            )
        except Exception as e:
            Logger.debug(f"QwenLM: failed to read current model label: {e}")
            return ""

        return str(label or "").strip()

    async def _wait_for_qwen_model_label(self, desired_canon: str, timeout_s: float = 2.0) -> bool:
        if not self.page:
            return False
        safe = str(desired_canon or "").strip()
        if not safe:
            return False

        deadline = time.monotonic() + float(timeout_s or 0.0)
        while time.monotonic() < deadline:
            current = await self._read_current_qwen_model_label()
            if self._canonicalize_model_label(current) == safe:
                return True
            await asyncio.sleep(0.1)

        return False

    async def _open_qwen_model_dropdown(self, timeout_ms: int = 6000) -> bool:
        if not self.page:
            return False

        text_el = self.page.locator(self.MODEL_SELECTOR_TEXT_SELECTOR)
        if await text_el.count() == 0:
            Logger.warning("QwenLM: model selector not found.")
            return False

        candidates = [
            text_el.first.locator("xpath=.."),
            text_el.first.locator("xpath=../.."),
            text_el.first,
        ]
        last_error: str | None = None

        for cand in candidates:
            try:
                await cand.click(timeout=3000)
            except Exception as e:
                last_error = str(e)
                continue

            try:
                await self.page.wait_for_selector(
                    f"{self.MODEL_SELECTOR_POPUP_SELECTOR} div[class*='model-list']",
                    timeout=int(timeout_ms),
                    state="visible",
                )
                return True
            except Exception:
                continue

        if last_error:
            Logger.warning(f"QwenLM: failed to click model selector trigger: {last_error}")
        Logger.warning("QwenLM: model selector popup did not appear.")
        return False

    async def _close_qwen_model_dropdown(self) -> None:
        if not self.page:
            return

        try:
            await self.page.keyboard.press("Escape")
        except Exception:
            pass

    @staticmethod
    def _extract_qwen_summary_parts(extra: dict[str, Any], key: str) -> List[str]:
        value = extra.get(key)
        if not isinstance(value, dict):
            return []

        content = value.get("content")
        if isinstance(content, list):
            return [str(item or "").strip() for item in content]
        if isinstance(content, str):
            return [content.strip()]
        return []

    @classmethod
    def _extract_qwen_thinking_summary_text(cls, delta: dict[str, Any]) -> str:
        extra = delta.get("extra")
        if not isinstance(extra, dict):
            return ""

        titles = cls._extract_qwen_summary_parts(extra, "summary_title")
        thoughts = cls._extract_qwen_summary_parts(extra, "summary_thought")
        section_count = max(len(titles), len(thoughts))
        sections: List[str] = []

        for idx in range(section_count):
            title = titles[idx] if idx < len(titles) else ""
            thought = thoughts[idx] if idx < len(thoughts) else ""
            if title and thought:
                sections.append(f"{title}\n{thought}")
            elif title or thought:
                sections.append(title or thought)

        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _compute_missing_suffix(emitted: str, candidate: str) -> str:
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

        if len(candidate) <= 800:
            return candidate
        return ""

    @classmethod
    def _compute_missing_thinking_summary_text(cls, emitted: str, candidate: str) -> str:
        missing = cls._compute_missing_suffix(emitted, candidate)
        if emitted and missing and missing == candidate and not missing.startswith(("\n", "\r")):
            return "\n\n" + missing
        return missing

    async def _click_model_option_in_popup(self, target_label: str) -> bool:
        if not self.page:
            return False

        wanted = str(target_label or "").strip()
        if not wanted:
            return False

        popup_sel = self.MODEL_SELECTOR_POPUP_SELECTOR
        item_sel = "div[class*='model-item___']"
        name_span_sel = "div[class*='model-item-name'] span"

        async def _try_click_once() -> bool:
            try:
                return bool(
                    await self.page.evaluate(
                        "(popupSel, itemSel, nameSpanSel, wantedRaw) => {"
                        "  const canon = (v) => {"
                        "    try {"
                        "      return (v || '').toString().normalize('NFKC').replace(/[^a-z0-9]+/gi, '').toLowerCase();"
                        "    } catch (e) {"
                        "      return (v || '').toString().replace(/[^a-z0-9]+/gi, '').toLowerCase();"
                        "    }"
                        "  };"
                        "  const isVisible = (el) => {"
                        "    try {"
                        "      if (!el) return false;"
                        "      const r = el.getBoundingClientRect();"
                        "      if (!r || r.width <= 0 || r.height <= 0) return false;"
                        "      const style = window.getComputedStyle(el);"
                        "      if (!style) return false;"
                        "      if (style.visibility === 'hidden' || style.display === 'none') return false;"
                        "      return true;"
                        "    } catch (e) { return false; }"
                        "  };"
                        "  const wantedCanon = canon(wantedRaw);"
                        "  if (!wantedCanon) return false;"
                        "  const popups = Array.from(document.querySelectorAll(popupSel)).filter(isVisible);"
                        "  if (!popups.length) return false;"
                        "  for (const popup of popups) {"
                        "    let items = Array.from(popup.querySelectorAll(itemSel));"
                        "    if (!items.length) items = Array.from(popup.querySelectorAll(\"div[class*='model-item']\"));"
                        "    items = items.filter(isVisible);"
                        "    for (const item of items) {"
                        "      const nameEl = item.querySelector(\"div[class*='model-item-name']\");"
                        "      const span = (nameEl && nameEl.querySelector('span')) || item.querySelector(nameSpanSel) || item.querySelector('span');"
                        "      const raw = (span && span.textContent) ? span.textContent : ((nameEl && nameEl.textContent) ? nameEl.textContent : '');"
                        "      const labelCanon = canon(raw);"
                        "      if (!labelCanon) continue;"
                        "      if (labelCanon === wantedCanon) {"
                        "        try { item.scrollIntoView({block: 'center'}); } catch (e) {}"
                        "        try { item.click(); } catch (e) { try { (span || nameEl || item).click(); } catch (e2) {} }"
                        "        return true;"
                        "      }"
                        "    }"
                        "  }"
                        "  return false;"
                        "}",
                        popup_sel,
                        item_sel,
                        name_span_sel,
                        wanted,
                    )
                )
            except Exception:
                return False

        if await _try_click_once():
            return True

        # Expand "more models" list (it's hidden behind a hover/click target)
        try:
            revealed = await self.page.evaluate(
                "(popupSel) => {"
                "  const norm = (v) => (v || '').toString().replace(/\\s+/g, ' ').trim().toLowerCase();"
                "  const isVisible = (el) => {"
                "    try {"
                "      if (!el) return false;"
                "      const r = el.getBoundingClientRect();"
                "      if (!r || r.width <= 0 || r.height <= 0) return false;"
                "      const style = window.getComputedStyle(el);"
                "      if (!style) return false;"
                "      if (style.visibility === 'hidden' || style.display === 'none') return false;"
                "      return true;"
                "    } catch (e) { return false; }"
                "  };"
                "  const popups = Array.from(document.querySelectorAll(popupSel)).filter(isVisible);"
                "  if (!popups.length) return false;"
                "  const popup = popups[0];"
                "  const triggerText = 'expand more models';"
                "  const candidates = Array.from(popup.querySelectorAll(\"span.ant-dropdown-trigger, div[class*='view-more']\"));"
                "  for (const el of candidates) {"
                "    const t = norm(el.textContent || '');"
                "    if (!t.includes(triggerText)) continue;"
                "    const target = el;"
                "    try { target.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true})); } catch (e) {}"
                "    try { target.dispatchEvent(new MouseEvent('mouseover', {bubbles:true})); } catch (e) {}"
                "    try { target.click(); } catch (e) {}"
                "    return true;"
                "  }"
                "  return false;"
                "}",
                self.MODEL_SELECTOR_POPUP_SELECTOR,
            )
        except Exception:
            revealed = False

        if revealed:
            await asyncio.sleep(0.12)
            if await _try_click_once():
                return True

        # Scroll each list a bit to work around virtualization
        for _ in range(10):
            try:
                await self.page.evaluate(
                    f"() => {{"
                    f"  const isVisible = (el) => {{"
                    f"    try {{"
                    f"      if (!el) return false;"
                    f"      const r = el.getBoundingClientRect();"
                    f"      if (!r || r.width <= 0 || r.height <= 0) return false;"
                    f"      const style = window.getComputedStyle(el);"
                    f"      if (!style) return false;"
                    f"      if (style.visibility === 'hidden' || style.display === 'none') return false;"
                    f"      return true;"
                    f"    }} catch (e) {{ return false; }}"
                    f"  }};"
                    f"  const popups = Array.from(document.querySelectorAll('{self.MODEL_SELECTOR_POPUP_SELECTOR}')).filter(isVisible);"
                    f"  for (const popup of popups) {{"
                    f"    const lists = Array.from(popup.querySelectorAll(\"div[class*='model-list']\")).filter(isVisible);"
                    f"    for (const el of lists) {{ el.scrollTop = (el.scrollTop || 0) + 220; }}"
                    f"  }}"
                    f"}}"
                )
            except Exception:
                pass

            await asyncio.sleep(0.08)
            if await _try_click_once():
                return True

        return False

    async def _read_qwen_model_picker_labels(self) -> List[str]:
        if not self.page:
            return []

        try:
            labels = await self.page.evaluate(
                "(popupSel) => {"
                "  const isVisible = (el) => {"
                "    try {"
                "      if (!el) return false;"
                "      const r = el.getBoundingClientRect();"
                "      if (!r || r.width <= 0 || r.height <= 0) return false;"
                "      const style = window.getComputedStyle(el);"
                "      if (!style) return false;"
                "      if (style.visibility === 'hidden' || style.display === 'none') return false;"
                "      return true;"
                "    } catch (e) { return false; }"
                "  };"
                "  const popups = Array.from(document.querySelectorAll(popupSel)).filter(isVisible);"
                "  const out = [];"
                "  for (const popup of popups) {"
                "    let items = Array.from(popup.querySelectorAll(\"div[class*='model-item___']\"));"
                "    if (!items.length) items = Array.from(popup.querySelectorAll(\"div[class*='model-item']\"));"
                "    items = items.filter(isVisible);"
                "    for (const item of items) {"
                "      const nameEl = item.querySelector(\"div[class*='model-item-name']\");"
                "      const span = (nameEl && nameEl.querySelector('span')) || item.querySelector(\"div[class*='model-item-name'] span\") || item.querySelector('span');"
                "      const raw = (span && span.textContent) ? span.textContent : ((nameEl && nameEl.textContent) ? nameEl.textContent : '');"
                "      const text = (raw || '').toString().trim();"
                "      if (text) out.push(text);"
                "    }"
                "  }"
                "  return out;"
                "}",
                self.MODEL_SELECTOR_POPUP_SELECTOR,
            )
        except Exception as e:
            Logger.debug(f"QwenLM: failed to read model picker labels: {e}")
            return []

        if not isinstance(labels, list):
            return []

        out: List[str] = []
        seen: set[str] = set()
        for raw in labels:
            try:
                text = str(raw or "").strip()
            except Exception:
                continue
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            out.append(text)

        return out

    async def _click_model_option_in_popup_locator(self, target_label: str) -> bool:
        if not self.page:
            return False

        wanted = str(target_label or "").strip()
        if not wanted:
            return False

        wanted_canon = self._canonicalize_model_label(wanted)
        if not wanted_canon:
            return False

        root = self.page.locator(self.MODEL_SELECTOR_POPUP_SELECTOR)
        popup_count = await root.count()
        if popup_count == 0:
            return False

        async def _try_click() -> bool:
            for pidx in range(min(popup_count, 6)):
                popup = root.nth(pidx)
                try:
                    if not await popup.is_visible():
                        continue
                except Exception:
                    pass

                spans = popup.locator("div[class*='model-item-name'] span")
                span_count = await spans.count()
                if span_count == 0:
                    spans = popup.locator("span")
                    span_count = await spans.count()

                for sidx in range(min(span_count, 80)):
                    cand = spans.nth(sidx)
                    try:
                        text = str(await cand.text_content() or "").strip()
                    except Exception:
                        continue
                    if self._canonicalize_model_label(text) != wanted_canon:
                        continue

                    item = cand.locator("xpath=ancestor::div[contains(@class,'model-item___')][1]")
                    if await item.count() == 0:
                        item = cand.locator("xpath=ancestor::div[contains(@class,'model-item')][1]")

                    try:
                        if await item.count() > 0:
                            await item.first.click(timeout=3000)
                        else:
                            await cand.click(timeout=3000)
                        return True
                    except Exception:
                        try:
                            if await item.count() > 0:
                                await item.first.click(timeout=3000, force=True)
                            else:
                                await cand.click(timeout=3000, force=True)
                            return True
                        except Exception:
                            continue

            return False

        if await _try_click():
            return True

        # Attempt to reveal expanded model list (hover/click) and retry
        try:
            trigger = self.page.locator(
                f"{self.MODEL_SELECTOR_POPUP_SELECTOR} div[class*='view-more']",
                has_text="Expand more models",
            )
            if await trigger.count() > 0:
                try:
                    await trigger.first.hover(timeout=1500)
                except Exception:
                    pass
                await asyncio.sleep(0.08)
                if await _try_click():
                    return True

                try:
                    await trigger.first.click(timeout=2000)
                except Exception:
                    pass
                await asyncio.sleep(0.12)
                if await _try_click():
                    return True
        except Exception:
            pass

        return False

    async def _ensure_qwen_model_selected(self, desired_label: str) -> None:
        desired = str(desired_label or "").strip()
        if not desired:
            return

        desired_canon = self._canonicalize_model_label(desired)

        current = await self._read_current_qwen_model_label()
        if desired_canon and self._canonicalize_model_label(current) == desired_canon:
            return

        if not await self._open_qwen_model_dropdown():
            return

        try:
            clicked = await self._click_model_option_in_popup(desired)
            if clicked:
                if desired_canon and await self._wait_for_qwen_model_label(desired_canon, timeout_s=2.0):
                    Logger.info(f"QwenLM: selected model '{desired}'.")
                    return

                Logger.warning(
                    f"QwenLM: clicked model '{desired}' but selection did not update. "
                    "Trying locator click fallback..."
                )
                fallback_clicked = await self._click_model_option_in_popup_locator(desired)
                if fallback_clicked:
                    if desired_canon and await self._wait_for_qwen_model_label(desired_canon, timeout_s=2.0):
                        Logger.info(f"QwenLM: selected model '{desired}'.")
                        return
                Logger.warning(f"QwenLM: failed to apply model selection '{desired}' after click attempts.")
                return

            fallback_clicked = await self._click_model_option_in_popup_locator(desired)
            if fallback_clicked:
                if desired_canon and await self._wait_for_qwen_model_label(desired_canon, timeout_s=2.0):
                    Logger.info(f"QwenLM: selected model '{desired}'.")
                    return

                Logger.warning(f"QwenLM: clicked model '{desired}' via locator fallback but selection did not update.")
                return

            try:
                labels = await self._read_qwen_model_picker_labels()
                if labels:
                    shown = labels[:20]
                    extra = len(labels) - len(shown)
                    suffix = f" (+{extra} more)" if extra > 0 else ""
                    Logger.debug(f"QwenLM: model picker options: {shown}{suffix}")

                    try:
                        if desired_canon and any(self._canonicalize_model_label(l) == desired_canon for l in labels):
                            Logger.warning(
                                f"QwenLM: model '{desired}' is present in the picker but could not be selected."
                            )
                            return
                    except Exception:
                        pass
                else:
                    Logger.debug("QwenLM: model picker options: (none detected)")
            except Exception:
                pass
            Logger.warning(f"QwenLM: target model '{desired}' not found in picker.")
        finally:
            await self._close_qwen_model_dropdown()

    async def set_sidebar_status(self, open: bool) -> None:
        if not self.page:
            return

        sidebar = self.page.locator(self.SIDEBAR_SELECTOR)
        if await sidebar.count() == 0:
            Logger.warning("QwenLM: sidebar container not found.")
            return

        state_attr = ""
        try:
            state_attr = str(await sidebar.first.get_attribute("data-state") or "").strip().lower()
        except Exception:
            state_attr = ""

        is_open = state_attr == "true"
        if open and is_open:
            return
        if (not open) and (not is_open):
            return

        if open:
            btn = self.page.locator(self.SIDEBAR_OPEN_BUTTON_SELECTOR)
            if await btn.count() == 0:
                Logger.warning("QwenLM: open-sidebar button not found.")
                return
            try:
                await btn.first.click(timeout=3000)
            except Exception as e:
                Logger.warning(f"QwenLM: failed to open sidebar: {e}")
                return
        else:
            btn = self.page.locator(self.SIDEBAR_CLOSE_BUTTON_SELECTOR)
            if await btn.count() == 0:
                Logger.warning("QwenLM: close-sidebar button not found.")
                return
            try:
                await btn.first.click(timeout=3000)
            except Exception as e:
                Logger.warning(f"QwenLM: failed to close sidebar: {e}")
                return

    async def click_new_chat(self, source: str = "auto") -> None:
        if not self.page:
            return

        btn = self.page.locator(self.NEW_CHAT_BUTTON_SELECTOR)
        if await btn.count() == 0:
            # sidebar entry list exists so pick its first child via JS
            try:
                clicked = await self.page.evaluate(
                    "() => {"
                    "  const list = document.querySelector('div.sidebar-entry-list');"
                    "  if (!list) return false;"
                    "  const first = list.firstElementChild;"
                    "  if (!first) return false;"
                    "  first.click();"
                    "  return true;"
                    "}"
                )
            except Exception:
                clicked = False
            if not clicked:
                Logger.warning("QwenLM: New Chat button not found.")
            return

        try:
            await btn.first.click(timeout=3000)
        except Exception as e:
            Logger.warning(f"QwenLM: failed to click New Chat: {e}")

    async def _read_thinking_mode(self) -> str:
        if not self.page:
            return ""

        label = self.page.locator(self.THINKING_LABEL_SELECTOR)
        if await label.count() == 0:
            return ""

        try:
            text = (await label.first.inner_text() or "").strip()
        except Exception:
            return ""

        return text

    async def _set_thinking_mode(self, mode: str) -> bool:
        if not self.page:
            return False

        wanted = str(mode or "").strip()
        if not wanted:
            return False

        current = await self._read_thinking_mode()
        if self._normalize_text(current) == self._normalize_text(wanted):
            return True

        trigger = self.page.locator(self.THINKING_TRIGGER_SELECTOR)
        if await trigger.count() == 0:
            Logger.warning("QwenLM: thinking selector trigger not found.")
            return False

        try:
            await trigger.first.click(timeout=3000)
        except Exception as e:
            Logger.warning(f"QwenLM: failed to open thinking dropdown: {e}")
            return False

        option = self.page.locator(self.THINKING_OPTIONS_SELECTOR).locator("div", has_text=wanted)
        try:
            await option.first.click(timeout=3000)
            await asyncio.sleep(0.1)
            return True
        except Exception as e:
            Logger.warning(f"QwenLM: failed to select thinking mode '{wanted}': {e}")
            return False

    async def set_deepthink_state(self, state: bool) -> None:
        # Qwen exposes Auto / Thinking / Fast. IntenseRP uses a boolean switch, so we map:
        # True -> Thinking, False -> Fast
        target = "Thinking" if state else "Fast"
        ok = await self._set_thinking_mode(target)
        if not ok:
            Logger.warning(f"QwenLM: could not set Thinking mode to '{target}'.")

    async def _is_search_enabled(self) -> bool:
        if not self.page:
            return False

        container = self.page.locator(self.SEARCH_MODE_CONTAINER_SELECTOR)
        if await container.count() == 0:
            return False

        try:
            text = str(await container.first.inner_text() or "").strip().lower()
            return "search" in text
        except Exception:
            pass

        # Fallback: JS query (avoid relying on volatile anchor IDs)
        try:
            enabled = await self.page.evaluate(
                f"() => {{"
                f"  const root = document.querySelector('{self.SEARCH_MODE_CONTAINER_SELECTOR}');"
                f"  if (!root) return false;"
                f"  const text = (root.textContent || '').toString().toLowerCase();"
                f"  return text.includes('search');"
                f"}}"
            )
        except Exception:
            enabled = False

        return bool(enabled)

    async def _click_first_visible(self, locator, timeout_ms: int = 3000) -> bool:
        if not self.page:
            return False

        count = 0
        try:
            count = await locator.count()
        except Exception:
            count = 0

        for idx in range(count):
            candidate = locator.nth(idx)
            try:
                if not await candidate.is_visible():
                    continue
            except Exception:
                continue

            try:
                await candidate.scroll_into_view_if_needed(timeout=int(timeout_ms))
            except Exception:
                pass

            try:
                await candidate.click(timeout=int(timeout_ms))
                return True
            except Exception:
                pass

            try:
                await candidate.evaluate("el => el.click()")
                return True
            except Exception:
                continue

        return False

    async def _click_first_visible_playwright_click(self, locator, timeout_ms: int = 3000) -> bool:
        if not self.page:
            return False

        count = 0
        try:
            count = await locator.count()
        except Exception:
            count = 0

        for idx in range(count):
            candidate = locator.nth(idx)
            try:
                if not await candidate.is_visible():
                    continue
            except Exception:
                continue

            try:
                await candidate.scroll_into_view_if_needed(timeout=int(timeout_ms))
            except Exception:
                pass

            try:
                await candidate.click(timeout=int(timeout_ms))
                return True
            except Exception:
                pass

            try:
                await candidate.click(timeout=int(timeout_ms), force=True)
                return True
            except Exception:
                continue

        return False

    async def _open_mode_select_dropdown_menu_root(self):
        if not self.page:
            return None

        open_trigger = self.page.locator(self.MODE_SELECT_TRIGGER_OPEN_SELECTOR)
        base_trigger = self.page.locator(self.MODE_SELECT_TRIGGER_SELECTOR)
        any_trigger = self.page.locator(self.MODE_SELECT_TRIGGER_ANY_SELECTOR)

        clicked_target = None
        candidates = []
        if await open_trigger.count() > 0:
            candidates.append(open_trigger.locator("xpath=.."))
            candidates.append(open_trigger)
        if await base_trigger.count() > 0:
            candidates.append(base_trigger.locator("xpath=.."))
            candidates.append(base_trigger)
        if not candidates and await any_trigger.count() > 0:
            candidates.append(any_trigger)

        clicked = False
        for candidate in candidates:
            if await self._click_first_visible_playwright_click(candidate, timeout_ms=3000):
                clicked_target = candidate
                clicked = True
                break
            if await self._click_first_visible(candidate, timeout_ms=3000):
                clicked_target = candidate
                clicked = True
                break

        if not clicked:
            return None

        for attempt in range(2):
            try:
                await self.page.wait_for_selector(self.MODE_SELECT_DROPDOWN_MENU_ROOT_SELECTOR, timeout=1200)
                break
            except Exception:
                if attempt != 0:
                    continue
                try:
                    fallback_target = clicked_target or any_trigger
                    if await fallback_target.count() == 0:
                        continue
                    await fallback_target.first.evaluate(
                        """(el) => {
                            if (!el) return;
                            const rect = el.getBoundingClientRect();
                            const x = rect.left + rect.width / 2;
                            const y = rect.top + rect.height / 2;
                            const top = document.elementFromPoint(x, y);
                            try { top && top.click(); } catch (e) {}
                        }"""
                    )
                except Exception:
                    pass

        try:
            await self.page.wait_for_selector(self.MODE_SELECT_DROPDOWN_MENU_ROOT_SELECTOR, timeout=2500)
        except Exception:
            try:
                await self.page.wait_for_selector("ul.ant-dropdown-menu-root", timeout=2500)
            except Exception:
                pass

        menu = self.page.locator(self.MODE_SELECT_DROPDOWN_MENU_ROOT_SELECTOR)
        if await menu.count() == 0:
            menu = self.page.locator("ul.ant-dropdown-menu-root")
        if await menu.count() == 0:
            return None

        return menu

    async def _open_mode_select_common_submenu(self) -> bool:
        if not self.page:
            return False

        open_trigger = self.page.locator(self.MODE_SELECT_TRIGGER_OPEN_SELECTOR)
        base_trigger = self.page.locator(self.MODE_SELECT_TRIGGER_SELECTOR)
        any_trigger = self.page.locator(self.MODE_SELECT_TRIGGER_ANY_SELECTOR)

        clicked_target = None
        candidates = []
        if await open_trigger.count() > 0:
            candidates.append(open_trigger.locator("xpath=.."))
            candidates.append(open_trigger)
        if await base_trigger.count() > 0:
            candidates.append(base_trigger.locator("xpath=.."))
            candidates.append(base_trigger)
        if not candidates and await any_trigger.count() > 0:
            candidates.append(any_trigger)

        clicked = False
        for candidate in candidates:
            if await self._click_first_visible_playwright_click(candidate, timeout_ms=3000):
                clicked_target = candidate
                clicked = True
                break
            if await self._click_first_visible(candidate, timeout_ms=3000):
                clicked_target = candidate
                clicked = True
                break

        if not clicked:
            return False

        # If the menu didn't render, try clicking the actual topmost element at the
        # trigger's center point (helps when the click handler is on a child element)
        try:
            await self.page.wait_for_selector(self.MODE_SELECT_COMMON_SUBMENU_SELECTOR, timeout=1200)
        except Exception:
            try:
                fallback_target = clicked_target or any_trigger
                if await fallback_target.count() == 0:
                    return False
                await fallback_target.first.evaluate(
                    """(el) => {
                        if (!el) return;
                        const rect = el.getBoundingClientRect();
                        const x = rect.left + rect.width / 2;
                        const y = rect.top + rect.height / 2;
                        const top = document.elementFromPoint(x, y);
                        try { top && top.click(); } catch (e) {}
                    }"""
                )
            except Exception:
                pass

        try:
            await self.page.wait_for_selector(self.MODE_SELECT_COMMON_SUBMENU_SELECTOR, timeout=3000)
        except Exception:
            pass

        submenu = self.page.locator(self.MODE_SELECT_COMMON_SUBMENU_SELECTOR)
        if await submenu.count() == 0:
            return False

        title = submenu.first.locator("div.ant-dropdown-menu-submenu-title")
        if await title.count() > 0:
            if await self._click_first_visible(title, timeout_ms=3000):
                return True
            try:
                await title.first.hover(timeout=1500)
                return True
            except Exception:
                return False

        return await self._click_first_visible(submenu, timeout_ms=3000)

    def _mode_select_item_selector(self, suffix: str) -> str:
        wanted = str(suffix or "").strip().lower()
        if not wanted:
            return self.MODE_SELECT_MENU_ITEM_SELECTOR
        return f"{self.MODE_SELECT_MENU_ITEM_SELECTOR}[data-menu-id$='-{wanted}']"

    async def _click_mode_select_item(self, suffix: str) -> bool:
        if not self.page:
            return False

        item_selector = self._mode_select_item_selector(suffix)
        try:
            await self.page.wait_for_selector(item_selector, timeout=2500)
        except Exception:
            pass

        items = self.page.locator(item_selector)
        if await items.count() == 0:
            # Fallback: suffix match might not work if Qwen changes the id format.
            items = self.page.locator(
                f"{self.MODE_SELECT_MENU_ITEM_SELECTOR}[data-menu-id*='{str(suffix or '').strip().lower()}']"
            )

        clicked = await self._click_first_visible(items, timeout_ms=3000)
        try:
            await self.page.keyboard.press("Escape")
        except Exception:
            pass

        return bool(clicked)

    async def _enable_search_via_mode_select_dropdown(self) -> bool:
        if not self.page:
            return False

        Logger.debug("QwenLM: enabling search via mode-select dropdown...")

        try:
            await self.page.wait_for_selector(self.MODE_SELECT_TRIGGER_ANY_SELECTOR, timeout=4000)
        except Exception:
            pass

        if not await self._open_mode_select_common_submenu():
            Logger.debug("QwenLM: mode-select submenu not found/opened.")
            return False

        ok = await self._click_mode_select_item("search")
        if not ok:
            Logger.debug("QwenLM: mode-select search item not found/clicked.")
        return bool(ok)

    async def _prime_upload_flow_via_mode_select_dropdown(self) -> bool:
        """
        Prime Qwen's upload flow without opening a native file chooser dialog.

        Qwen wires file uploads through the mode-select dropdown. Clicking the Upload item
        (a root dropdown entry, not a submenu item) can trigger a file picker. We suppress
        that picker by temporarily overriding the input's .click() method while still
        letting Qwen's handler run.
        """
        if not self.page:
            return False

        try:
            primed = await self.page.evaluate(
                "async (triggerSel, menuSel, itemSel) => {"
                "  const sleep = (ms) => new Promise(r => setTimeout(r, ms));"
                "  const clickEl = (el) => {"
                "    if (!el) return false;"
                "    try { el.click(); return true; } catch (e) {}"
                "    try { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); return true; } catch (e) {}"
                "    return false;"
                "  };"
                ""
                "  const trigger = document.querySelector(triggerSel);"
                "  if (!trigger) return false;"
                "  const triggerTarget = trigger.parentElement || trigger;"
                "  clickEl(triggerTarget);"
                ""
                "  const deadline = Date.now() + 3000;"
                ""
                "  while (Date.now() < deadline) {"
                "    const menu = document.querySelector(menuSel) || document.querySelector('ul.ant-dropdown-menu-root');"
                "    if (menu) {"
                "      break;"
                "    }"
                "    await sleep(50);"
                "  }"
                ""
                "  const menu = document.querySelector(menuSel) || document.querySelector('ul.ant-dropdown-menu-root');"
                "  if (!menu) return false;"
                ""
                "  while (Date.now() < deadline) {"
                "    const items = Array.from(menu.querySelectorAll(itemSel));"
                "    const target = items.find((el) => {"
                "      const id = (el.getAttribute('data-menu-id') || '').toString();"
                "      return id.endsWith('-upload') || id.includes('upload');"
                "    });"
                "    if (target) {"
                "      const orig = HTMLInputElement.prototype.click;"
                "      HTMLInputElement.prototype.click = function() {};"
                "      try {"
                "        clickEl(target);"
                "        return true;"
                "      } catch (e) {"
                "        return false;"
                "      } finally {"
                "        HTMLInputElement.prototype.click = orig;"
                "      }"
                "    }"
                "    await sleep(50);"
                "  }"
                ""
                "  return false;"
                "}",
                self.MODE_SELECT_TRIGGER_ANY_SELECTOR,
                self.MODE_SELECT_DROPDOWN_MENU_ROOT_SELECTOR,
                self.MODE_SELECT_MENU_ITEM_SELECTOR,
            )
        except Exception:
            primed = False

        try:
            await self.page.keyboard.press("Escape")
        except Exception:
            pass

        return bool(primed)

    async def _enable_search(self) -> bool:
        if not self.page:
            return False

        # use the mode-select dropdown (more stable than the old anchor trick)
        # and it doesn't bug out in most cases
        if await self._enable_search_via_mode_select_dropdown():
            return True

        try:
            clicked = await self.page.evaluate(
                "(enableAnchor, currentModeSelector) => {"
                "  const clickAncestors = (span) => {"
                "    if (!span) return false;"
                "    let el = span;"
                "    for (let i = 0; i < 3; i++) {"
                "      if (el.parentElement) el = el.parentElement;"
                "    }"
                "    try { el.click(); return true; } catch (e) {}"
                "    try { span.click(); return true; } catch (e) {}"
                "    try { span.dispatchEvent(new MouseEvent('click', { bubbles: true })); return true; } catch (e) {}"
                "    return false;"
                "  };"
                ""
                "  try {"
                "    const byAnchor = document.querySelector(`span[data-spm-anchor-id='${enableAnchor}']`);"
                "    if (clickAncestors(byAnchor)) return true;"
                "  } catch (e) {}"
                ""
                "  const isInsideCurrent = (node) => {"
                "    try { return !!(node && node.closest && node.closest(currentModeSelector)); }"
                "    catch (e) { return false; }"
                "  };"
                ""
                "  const spans = Array.from(document.querySelectorAll('span[data-spm-anchor-id]'));"
                "  for (const s of spans) {"
                "    if (!s) continue;"
                "    if (isInsideCurrent(s)) continue;"
                "    const raw = (s.textContent || '').toString().trim().toLowerCase();"
                "    if (!raw) continue;"
                "    const text = raw.replace(/\\s+/g, ' ');"
                "    if (text === 'web search' || text.includes('web search') || (text.includes('web') && text.includes('search'))) {"
                "      if (clickAncestors(s)) return true;"
                "    }"
                "  }"
                ""
                "  return false;"
                "}",
                self.SEARCH_ENABLE_ANCHOR,
                self.SEARCH_MODE_CONTAINER_SELECTOR,
            )
        except Exception:
            clicked = False

        return bool(clicked)

    async def _disable_search(self) -> bool:
        if not self.page:
            return False

        btn = self.page.locator(self.SEARCH_CLOSE_SELECTOR)
        if await btn.count() == 0:
            return False
        try:
            await btn.first.click(timeout=3000)
            return True
        except Exception:
            return False

    async def set_search_state(self, state: bool) -> None:
        wanted = bool(state)

        for _ in range(8):
            before = await self._is_search_enabled()
            if before == wanted:
                return

            if wanted:
                await self._enable_search()
            else:
                await self._disable_search()

            await asyncio.sleep(0.25)

        after = await self._is_search_enabled()
        if after != wanted:
            Logger.warning(f"QwenLM: Search state mismatch after toggle (wanted={wanted}, actual={after}).")

    async def upload_file(self, file_spec: Any) -> None:
        await self._upload_file(file_spec)

    async def _upload_file(self, file_spec: Any) -> None:
        if not self.page:
            return

        temp_dir: str | None = None
        temp_path: str | None = None

        def _materialize_payload(payload: dict) -> str | None:
            nonlocal temp_dir, temp_path
            try:
                buffer = payload.get("buffer")
                if not isinstance(buffer, (bytes, bytearray)) or not buffer:
                    return None

                name = str(payload.get("name") or "").strip()
                if name:
                    name = name.replace("\\", "/")
                safe_name = os.path.basename(name) if name else ""
                safe_name = safe_name.strip() or "upload.bin"

                temp_dir = tempfile.mkdtemp(prefix="irp-qwen-upload-")
                temp_path = os.path.join(temp_dir, safe_name)
                with open(temp_path, "wb") as f:
                    f.write(buffer)
                return temp_path
            except Exception:
                return None

        try:
            try:
                if isinstance(file_spec, dict):
                    name = file_spec.get("name", "<payload>")
                    buffer = file_spec.get("buffer")
                    size = len(buffer) if isinstance(buffer, (bytes, bytearray)) else None
                    size_info = f" ({size} bytes)" if size is not None else ""
                    Logger.debug(f"QwenLM: uploading file payload: {name}{size_info}")
                else:
                    Logger.debug(f"QwenLM: uploading file: {file_spec}")
            except Exception:
                Logger.debug("QwenLM: uploading file (details unavailable).")

            uploaded_via_chooser = False

            # click the root Upload item (no submenu) so Qwen wires up its upload callbacks,
            # then answer the file chooser programmatically
            try:
                Logger.debug("QwenLM: attempting upload via mode-select file chooser...")
                try:
                    await self.page.wait_for_selector(self.MODE_SELECT_TRIGGER_ANY_SELECTOR, timeout=4000)
                except Exception:
                    pass

                menu_root = await self._open_mode_select_dropdown_menu_root()
                if menu_root is not None:
                    upload_item = menu_root.locator(self._mode_select_item_selector("upload"))
                    if await upload_item.count() == 0:
                        upload_item = menu_root.locator(
                            f"{self.MODE_SELECT_MENU_ITEM_SELECTOR}[data-menu-id$='-upload']"
                        )
                    if await upload_item.count() == 0:
                        upload_item = menu_root.locator(
                            f"{self.MODE_SELECT_MENU_ITEM_SELECTOR}[data-menu-id*='upload']"
                        )

                    if await upload_item.count() > 0:
                        async with self.page.expect_file_chooser(timeout=6000) as fc_info:
                            if not await self._click_first_visible_playwright_click(upload_item, timeout_ms=3000):
                                raise RuntimeError("Upload menu item was not clickable.")
                        chooser = await fc_info.value

                        chooser_files = file_spec
                        if isinstance(file_spec, dict):
                            temp_candidate = _materialize_payload(file_spec)
                            if temp_candidate:
                                chooser_files = temp_candidate

                        await chooser.set_files(chooser_files)
                        uploaded_via_chooser = True
                    else:
                        Logger.debug("QwenLM: mode-select Upload item not found in dropdown menu.")
                else:
                    Logger.debug("QwenLM: mode-select dropdown menu root not found (upload).")
            except Exception as e:
                Logger.debug(f"QwenLM: mode-select file chooser upload failed: {e}")
            finally:
                try:
                    await self.page.keyboard.press("Escape")
                except Exception:
                    pass

            if uploaded_via_chooser:
                try:
                    file_count = await self.page.evaluate(
                        "() => {"
                        "  const input = document.querySelector('#filesUpload') || document.querySelector(\"input[type='file']\");"
                        "  if (!input || !input.files) return 0;"
                        "  return input.files.length || 0;"
                        "}"
                    )
                    Logger.debug(f"QwenLM: file chooser set {int(file_count or 0)} file(s) on input.")
                except Exception:
                    pass
            else:
                Logger.debug("QwenLM: falling back to direct set_input_files() upload...")

                file_input = self.page.locator(self.FILE_INPUT_SELECTOR)
                if await file_input.count() == 0:
                    try:
                        await self.page.wait_for_selector(self.FILE_INPUT_SELECTOR, timeout=8000)
                    except Exception:
                        pass
                    file_input = self.page.locator(self.FILE_INPUT_SELECTOR)

                if await file_input.count() == 0:
                    file_input = self.page.locator("input[type='file']")
                    if await file_input.count() == 0:
                        try:
                            await self.page.wait_for_selector("input[type='file']", timeout=8000)
                        except Exception:
                            pass
                        file_input = self.page.locator("input[type='file']")

                if await file_input.count() == 0:
                    Logger.warning("QwenLM: file input not found.")
                    return

                async def _apply_files() -> bool:
                    try:
                        await file_input.first.set_input_files(file_spec)
                    except Exception as e:
                        Logger.warning(f"QwenLM: file upload failed: {e}")
                        return False

                    try:
                        await self.page.evaluate(
                            "() => {"
                            "  const inputs = Array.from(document.querySelectorAll(\"input[type='file']\"));"
                            "  for (const input of inputs) {"
                            "    try { input.dispatchEvent(new Event('input', { bubbles: true })); } catch (e) {}"
                            "    try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}"
                            "  }"
                            "}"
                        )
                    except Exception:
                        pass

                    return True

                async def _send_button_exists() -> bool:
                    btn = self.page.locator(self.SEND_BUTTON_SELECTOR)
                    try:
                        return (await btn.count() > 0) and (await btn.first.is_visible())
                    except Exception:
                        return False

                if not await _apply_files():
                    return

                appeared = False
                for _ in range(20):
                    if await _send_button_exists():
                        appeared = True
                        break
                    await asyncio.sleep(0.1)

                if not appeared:
                    Logger.debug("QwenLM: upload did not register via direct input. Priming upload flow and retrying...")
                    try:
                        await self._prime_upload_flow_via_mode_select_dropdown()
                    except Exception:
                        pass

                    file_input = self.page.locator(self.FILE_INPUT_SELECTOR)
                    if await file_input.count() == 0:
                        file_input = self.page.locator("input[type='file']")
                    if await file_input.count() == 0:
                        Logger.warning("QwenLM: file input not found after priming upload flow.")
                        return

                    if not await _apply_files():
                        return

            # Wait for upload spinner to complete (must appear at least once)
            spinner = self.page.locator(".circle-spinner.vision-spinner")
            appeared = False
            for _ in range(60):
                try:
                    if await spinner.count() > 0 and await spinner.first.is_visible():
                        appeared = True
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.1)

            if appeared:
                for _ in range(600):
                    try:
                        if await spinner.count() == 0:
                            break
                        if not await spinner.first.is_visible():
                            break
                    except Exception:
                        break
                    await asyncio.sleep(0.1)
        finally:
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

    async def enter_message(self, message: str) -> None:
        await self._enter_message(message)

    async def send_message(self, timeout: int | None = None) -> None:
        await self._send_message(timeout=timeout)

    async def _enter_message(self, message: str) -> None:
        if not self.page:
            return

        textarea = self.page.locator(self.CHAT_TEXTAREA_SELECTOR)
        if await textarea.count() == 0:
            textarea = self.page.locator("textarea")
        if await textarea.count() == 0:
            Logger.warning("QwenLM: message textarea not found.")
            return

        preview = message[:50] + "..." if len(message) > 50 else message
        Logger.debug(f"QwenLM: entering message: {preview}")
        await textarea.first.fill(message)

    async def _send_message(self, timeout: int | None = None, arm_event: asyncio.Event | None = None) -> None:
        if not self.page:
            return

        if arm_event:
            try:
                arm_event.set()
            except Exception:
                pass

        max_wait_s = 0 if not timeout else max(int(timeout), 0)
        start = time.time()
        last_error: Optional[Exception] = None

        while True:
            btn = self.page.locator(self.SEND_BUTTON_SELECTOR)
            try:
                if await btn.count() > 0 and await btn.first.is_visible():
                    disabled_attr = None
                    try:
                        disabled_attr = await btn.first.get_attribute("disabled")
                    except Exception:
                        disabled_attr = None

                    aria_disabled = ""
                    try:
                        aria_disabled = str(await btn.first.get_attribute("aria-disabled") or "").strip().lower()
                    except Exception:
                        aria_disabled = ""

                    if disabled_attr is not None or aria_disabled == "true":
                        raise RuntimeError("Send button is disabled.")

                    is_enabled = True
                    try:
                        is_enabled = await btn.first.is_enabled()
                    except Exception:
                        is_enabled = True

                    if is_enabled:
                        await btn.first.click(timeout=3000)
                        return
            except Exception as e:
                last_error = e

            if max_wait_s <= 0:
                break
            if time.time() - start >= max_wait_s:
                break
            await asyncio.sleep(0.1)

        if last_error:
            Logger.warning(f"QwenLM: failed to click send button: {last_error}")
        else:
            Logger.warning("QwenLM: send button not found (it appears only after input/upload).")

    async def _click_regenerate(self, arm_event: asyncio.Event | None = None) -> bool:
        if not self.page:
            return False

        if arm_event:
            try:
                arm_event.set()
            except Exception:
                pass

        btn = self.page.locator("div.qwen-chat-package-comp-new-action-control-container-regenerate")
        count = 0
        try:
            count = await btn.count()
        except Exception:
            count = 0

        for idx in range(count - 1, -1, -1):
            candidate = btn.nth(idx)
            try:
                if not await candidate.is_visible():
                    continue
                await candidate.click(timeout=3000)
                return True
            except Exception:
                continue

        return False

    def _format_messages(self, messages: Union[str, List[Any]]) -> str:
        return format_messages(self.config_manager, messages)

    async def generate_response(
        self,
        message: Union[str, List[Any]],
        model: str = "qwen-auto",
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

        await self.require_english_ui()
        try:
            await self._ensure_rp_friendly_settings()
        except Exception:
            pass

        self.thinking_active = False
        self.abort_requested = False
        self.current_abort_event = abort_event
        resolved_model = (model or "").strip() or "qwen-auto"
        self.current_model = resolved_model

        macros_overrides: Dict[str, bool] = {}
        message_for_formatting = message
        if isinstance(message, list):
            message_for_formatting, macros_overrides = self._strip_qwen_macros_from_messages(message)
        elif isinstance(message, str):
            message_for_formatting, macros_overrides = self._extract_qwen_macros_from_text(message)

        if macros_overrides:
            Logger.debug(f"QwenLM macros applied: {macros_overrides}")

        effective_settings = self._resolve_qwen_request_settings(resolved_model, overrides=macros_overrides)
        effective_deepthink = effective_settings["deepthink_enabled"]
        effective_send_deepthink = effective_settings["send_deepthink"]
        enable_search = effective_settings["search_enabled"]
        send_as_text_file = effective_settings["send_as_text_file"]
        self.current_send_deepthink = effective_send_deepthink

        formatted_message = self._format_messages(message_for_formatting)

        async def handle_route(route):
            nonlocal completion_claimed
            request = route.request

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

            Logger.info("Intercepting QwenLM API request...")
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
            answer_started = False
            openai_usage: dict[str, Any] | None = None
            openai_usage_emitted = False
            openai_finish_emitted = False

            try:
                count_tokens_setting = self.config_manager.get_setting("qwen_behavior", "count_tokens")
            except Exception:
                count_tokens_setting = None
            count_tokens_enabled = True if count_tokens_setting is None else bool(count_tokens_setting)

            def _normalize_openai_usage(raw: Any) -> dict[str, Any] | None:
                if not isinstance(raw, dict):
                    return None

                def _to_int(value: Any) -> int | None:
                    try:
                        return int(value)
                    except Exception:
                        return None

                prompt_tokens = _to_int(raw.get("input_tokens"))
                completion_tokens = _to_int(raw.get("output_tokens"))
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

                prompt_details = raw.get("input_tokens_details")
                if isinstance(prompt_details, dict):
                    usage["prompt_tokens_details"] = prompt_details

                completion_details = raw.get("output_tokens_details")
                if isinstance(completion_details, dict):
                    usage["completion_tokens_details"] = completion_details

                return usage

            def enqueue_openai_delta(content: str, finish_reason: str | None = None) -> None:
                if (not content) and (not finish_reason):
                    return
                model_name = self.current_model or "qwen-auto"
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

            def enqueue_openai_usage(usage: dict[str, Any]) -> None:
                nonlocal openai_usage_emitted
                if openai_usage_emitted:
                    return
                model_name = self.current_model or "qwen-auto"
                openai_chunk = {
                    "id": "chatcmpl-custom",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [],
                    "usage": usage,
                }
                response_queue.put_nowait(f"data: {json.dumps(openai_chunk)}\n\n")
                openai_usage_emitted = True

            def process_sse_line(line: str) -> None:
                nonlocal thinking_emitted, answer_started, openai_usage, openai_finish_emitted
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

                if count_tokens_enabled:
                    normalized = _normalize_openai_usage(payload.get("usage"))
                    if normalized:
                        openai_usage = normalized

                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    return

                choice0 = choices[0]
                if not isinstance(choice0, dict):
                    return

                delta = choice0.get("delta")
                if not isinstance(delta, dict):
                    return

                phase = str(delta.get("phase") or "").strip().lower()
                status = str(delta.get("status") or "").strip().lower()

                if phase == "web_search":
                    # Ignore tool-call chatter + raw search results for stability
                    return

                if phase == "thinking_summary":
                    if not self.current_send_deepthink:
                        return
                    summary_text = self._extract_qwen_thinking_summary_text(delta)
                    if not summary_text:
                        return

                    if not self.thinking_active:
                        enqueue_openai_delta("<think>")
                        self.thinking_active = True

                    missing = self._compute_missing_thinking_summary_text(thinking_emitted, summary_text)
                    if missing:
                        enqueue_openai_delta(missing)
                        thinking_emitted += missing
                    return

                if phase == "answer":
                    if self.thinking_active and self.current_send_deepthink and not answer_started:
                        enqueue_openai_delta("</think>")
                        self.thinking_active = False

                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        enqueue_openai_delta(content)
                        answer_started = True

                    if status == "finished":
                        if not openai_finish_emitted:
                            if self.thinking_active and self.current_send_deepthink:
                                enqueue_openai_delta("</think>")
                                self.thinking_active = False
                            enqueue_openai_delta("", finish_reason="stop")
                            openai_finish_emitted = True
                            if count_tokens_enabled and openai_usage:
                                enqueue_openai_usage(openai_usage)
                    return

            json_body = None
            raw_post_data = request.post_data
            if raw_post_data:
                try:
                    json_body = json.loads(raw_post_data)
                except Exception:
                    json_body = None

            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream(
                        "POST",
                        request.url,
                        headers=headers,
                        cookies=cookie_dict,
                        json=json_body,
                        timeout=90.0,
                    ) as response:
                        for k, v in response.headers.items():
                            response_headers[k] = v

                        async for chunk in response.aiter_bytes():
                            if self.abort_requested or (abort_event and abort_event.is_set()):
                                Logger.debug("Abort detected during QwenLM streaming, stopping...")
                                aborted = True
                                break

                            full_response_body.extend(chunk)
                            text_buffer.extend(chunk)

                            while True:
                                nl = text_buffer.find(b"\n", text_buffer_pos)
                                if nl == -1:
                                    break
                                raw_line = text_buffer[text_buffer_pos:nl]
                                text_buffer_pos = nl + 1
                                try:
                                    line = raw_line.decode("utf-8", errors="ignore")
                                except Exception:
                                    continue
                                process_sse_line(line)

                            if text_buffer_pos > 8192:
                                del text_buffer[:text_buffer_pos]
                                text_buffer_pos = 0

                        tail = bytes(text_buffer[text_buffer_pos:])
                        if tail.strip():
                            process_sse_line(tail.decode("utf-8", errors="ignore"))
                        text_buffer.clear()
                        text_buffer_pos = 0

            except httpx.ReadError as e:
                if not aborted and not self.abort_requested:
                    Logger.error(f"QwenLM: read error during intercepted request: {e}")
                    await response_queue.put({"error": str(e)})
            except Exception as e:
                if not aborted and not self.abort_requested:
                    Logger.error(f"QwenLM: error during intercepted request: {e}")
                    await response_queue.put({"error": str(e)})

            if aborted or self.abort_requested:
                Logger.warning("QwenLM generation aborted by user.")

            try:
                await route.fulfill(body=bytes(full_response_body), status=200, headers=response_headers)
            except Exception as e:
                Logger.error(f"QwenLM: error fulfilling route: {e}")

            await response_queue.put(None)
            if not aborted and not self.abort_requested:
                Logger.success("QwenLM response streaming completed.")

        await self.page.route(self.COMPLETIONS_ROUTE_GLOB, handle_route)

        try:
            clean_regeneration = bool(self.config_manager.get_setting("qwen_behavior", "clean_regeneration"))
            multi_slot_cache_enabled = bool(
                clean_regeneration
                and self.config_manager.get_setting("qwen_behavior", "multi_slot_cache")
            )
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
                }
                multi_slot_state = self._build_multi_slot_cache_state(
                    effective_deepthink=bool(effective_deepthink),
                    enable_search=bool(enable_search),
                    send_as_text_file=bool(send_as_text_file),
                )

                last_message = self.cache_manager.read_cache(self.clean_regen_message_cache_key)
                last_state = self._read_clean_regeneration_state()

                message_matches = last_message == formatted_message
                state_matches = last_state == clean_regen_state

                if message_matches and state_matches:
                    current_cache_matched = True
                    Logger.info(
                        "Clean Regeneration (QwenLM): Message and settings match cache. Attempting to regenerate..."
                    )

                    try:
                        await self.set_deepthink_state(effective_deepthink)
                        await self.set_search_state(enable_search)
                        await asyncio.sleep(0.25)
                    except Exception:
                        pass

                    if await self._click_regenerate(arm_event=completion_armed):
                        Logger.info("Clean Regeneration (QwenLM): Regenerate clicked. Regenerating...")
                        try:
                            await asyncio.wait_for(completion_started.wait(), timeout=20.0)
                        except asyncio.TimeoutError:
                            Logger.warning(
                                "Clean Regeneration (QwenLM): completion request not observed after clicking "
                                "Regenerate. Falling back to new chat."
                            )
                        else:
                            regenerated = True
                            self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                            self._write_clean_regeneration_state(clean_regen_state)
                    else:
                        Logger.warning(
                            "Clean Regeneration (QwenLM): Regenerate button not found/visible. Falling back to new chat."
                        )

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
                    self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                    self._write_clean_regeneration_state(clean_regen_state)

            if not regenerated:
                Logger.info("QwenLM: preparing new chat session...")
                await self.click_new_chat(source="auto")
                await asyncio.sleep(0.35)

                await self.apply_configured_model()

                await self.set_deepthink_state(effective_deepthink)
                await self.set_search_state(enable_search)
                await asyncio.sleep(0.25)

                if send_as_text_file:
                    Logger.info("QwenLM: sending message as text file...")
                    file_payload = {
                        "name": "prompt.txt",
                        "mimeType": "text/plain",
                        "buffer": formatted_message.encode("utf-8"),
                    }
                    await self._upload_file(file_payload)

                    try:
                        file_message = str(
                            self.config_manager.get_setting("qwen_behavior", "text_file_message") or ""
                        )
                    except Exception:
                        file_message = ""

                    if file_message.strip():
                        await self._enter_message(file_message)
                        await asyncio.sleep(0.1)

                    upload_timeout = int(self.config_manager.get_setting("qwen_behavior", "file_upload_timeout") or 20)
                    Logger.info("QwenLM: sending request...")
                    await self._send_message(timeout=upload_timeout, arm_event=completion_armed)
                else:
                    await self._enter_message(formatted_message)
                    await asyncio.sleep(0.1)
                    msg_send_timeout = int(self.config_manager.get_setting("qwen_behavior", "message_send_timeout") or 8)
                    Logger.info("QwenLM: sending request...")
                    await self._send_message(timeout=msg_send_timeout, arm_event=completion_armed)

                if clean_regeneration and clean_regen_state:
                    self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                    self._write_clean_regeneration_state(clean_regen_state)
                    should_record_multi_slot = bool(multi_slot_cache_enabled and multi_slot_state)

            if not completion_started.is_set():
                try:
                    await asyncio.wait_for(completion_started.wait(), timeout=20.0)
                except asyncio.TimeoutError:
                    Logger.error(
                        "QwenLM: completion request was not observed. "
                        "The UI may have swallowed the click or the endpoint changed."
                    )
                    yield f"data: {json.dumps({'error': 'QwenLM: completion request not observed'})}\n\n"
                    return

            stream_had_error = False
            async for item in self._iterate_response_queue(
                response_queue,
                abort_event=abort_event,
                first_chunk_timeout_s=self.INTERCEPT_FIRST_CHUNK_TIMEOUT_S,
                idle_timeout_s=self.INTERCEPT_IDLE_TIMEOUT_S,
                on_timeout=self._abort_generation_ui,
            ):
                if isinstance(item, dict) and "error" in item:
                    stream_had_error = True
                    yield f"data: {json.dumps(item)}\n\n"
                    break

                yield item

            if should_record_multi_slot and (not stream_had_error) and (not self.abort_requested):
                conversation_info = await self._wait_for_current_conversation_info(timeout_ms=6000)
                if conversation_info is None:
                    Logger.debug(
                        "Multi-Slot Cache (QwenLM): could not resolve conversation URL after "
                        "generation; skipping cache save."
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
                        log_label="Multi-Slot Cache (QwenLM)",
                    )
        finally:
            self.current_abort_event = None
            self.abort_requested = False
            self.current_model = None
            self.current_send_deepthink = None
            try:
                await self.page.unroute(self.COMPLETIONS_ROUTE_GLOB)
            except Exception:
                pass
