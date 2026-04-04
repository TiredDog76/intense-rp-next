import codecs
import time
import json
import asyncio
import re
import httpx
from typing import List, Union, Any, Dict, Callable, Optional
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
    remove_multi_slot_cache_entry,
    strip_macros_from_messages,
    upsert_multi_slot_cache_entry,
    read_multi_slot_cache_payload,
    write_clean_regeneration_state,
)
from utils.cache_manager import CacheManager
from utils.logger import Logger
from utils.model_ids import MODE_CHAT, MODE_REASONER, resolve_behavior_mode

load_dotenv()

class DeepSeekDriver(BaseDriver):
    INTERCEPT_FIRST_CHUNK_TIMEOUT_S = 45.0
    INTERCEPT_IDLE_TIMEOUT_S = 75.0
    CONVERSATION_URL_RE = re.compile(r"^https://chat\.deepseek\.com/a/chat/s/([^/?#]+)", re.IGNORECASE)
    CHAT_READY_SELECTORS = [
        "textarea[placeholder='Message DeepSeek']",
        "textarea",
    ]
    SIGN_IN_SELECTORS = [
        ".ds-sign-in-form__main",
        ".ds-sign-in-form-wrapper",
        ".ds-auth-form-wrapper",
        ".ds-sign-up-form__main",
        "input[autocomplete='current-password']",
        "input[type='password']",
        "button:has-text('Log in')",
        "button:has-text('Sign in')",
    ]

    def __init__(self, config_manager):
        super().__init__(config_manager=config_manager, provider=DriverProvider.DEEPSEEK)
        self.cache_manager = CacheManager()

        # DeepSeek UI language detection (some selectors rely on English UI text)
        self.last_document_lang: Optional[str] = None
        self.ui_language_ok: Optional[bool] = None
        self._non_english_ui_warned = False
        self._non_english_ui_warned_lang: Optional[str] = None
        
        self.current_model = None
        self.current_send_deepthink = None
        self.clean_regen_message_cache_key = "last_message.txt"
        self.clean_regen_state_cache_key = "last_message_state.json"
        self.multi_slot_cache_key = "deepseek_multi_slot_cache.json"
        self._last_generation_censored = False
        self._reset_stream_parser()

    def _reset_stream_parser(self) -> None:
        self._stream_text_decoder = codecs.getincrementaldecoder("utf-8")()
        self._stream_text_buffer = ""

    def get_start_url(self) -> str:
        return "https://chat.deepseek.com/"

    async def after_start(self, status_callback: Optional[Callable[[str], None]] = None) -> None:
        # Detect DeepSeek UI language early (warn only; hard-requirement is enforced per-request)
        await self.check_ui_language(status_callback=status_callback)

        # Invalidate cache on start
        clear_clean_regeneration_cache(
            self.cache_manager,
            self.clean_regen_message_cache_key,
            self.clean_regen_state_cache_key,
        )
        try:
            await self._remember_send_control_signature(self.page.locator("div.ds-icon-button._7436101"))
        except Exception:
            pass

    async def _has_visible_selector(
        self,
        selectors: List[str],
        *,
        max_candidates: int = 8,
    ) -> bool:
        if not self.page:
            return False

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                count = await locator.count()
            except Exception:
                continue

            for idx in range(min(count, max_candidates)):
                try:
                    if await locator.nth(idx).is_visible():
                        return True
                except Exception:
                    continue

        return False

    async def _detect_deepseek_shell_state(self) -> str:
        if not self.page:
            return "unknown"

        try:
            url_lower = str(self.page.url or "").lower()
        except Exception:
            url_lower = ""

        if any(token in url_lower for token in ("sign_in", "signin", "sign-in")):
            return "auth"
        if await self._has_visible_selector(self.SIGN_IN_SELECTORS):
            return "auth"
        if await self._has_visible_selector(self.CHAT_READY_SELECTORS):
            return "chat"
        return "unknown"

    async def _wait_for_deepseek_shell_state(
        self,
        timeout_ms: int = 60000,
        poll_interval_s: float = 0.25,
    ) -> str:
        deadline = time.time() + max(0.0, float(timeout_ms) / 1000.0)

        while True:
            state = await self._detect_deepseek_shell_state()
            if state != "unknown":
                return state

            if time.time() >= deadline:
                return "unknown"

            await asyncio.sleep(max(0.05, float(poll_interval_s)))

    async def login(self):
        """
        Handles the login process if redirected to the sign-in page.
        """
        try:
            await self.page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass

        shell_state = await self._wait_for_deepseek_shell_state(timeout_ms=60000)
        if shell_state == "unknown":
            Logger.debug(
                "DeepSeek: chat/auth UI did not stabilize before auth check. "
                "Proceeding with best-effort state detection."
            )
            shell_state = await self._detect_deepseek_shell_state()

        is_sign_in_page = shell_state == "auth"

        # Check if we were redirected to sign in
        if is_sign_in_page:
            Logger.info("Redirected to sign in page.")
            
            auto_login = bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
            
            if auto_login:
                email = ""
                password = ""
                pair = self.ece_active_pair()
                if not pair:
                    Logger.warning(
                        "Auto-login is enabled but no DeepSeek accounts are configured in Credential Manager. "
                        "Waiting for manual login..."
                    )
                    try:
                        await self.page.wait_for_selector("textarea", timeout=0)
                        Logger.success("Manual login detected.")
                    except Exception as e:
                        Logger.error(f"Error waiting for manual login: {e}")
                    return

                email = pair.email
                password = pair.password

                if not email or not password:
                    Logger.error("DeepSeek account is missing an email or password.")
                    return

                Logger.info("Auto-login enabled. Attempting to log in...")

                try:
                    # Wait for the form to appear
                    await self.page.wait_for_selector(
                        ".ds-sign-in-form__main, .ds-sign-in-form-wrapper, .ds-auth-form-wrapper, .ds-sign-up-form__main",
                        timeout=30000,
                    )

                    form_root = self.page.locator(
                        ".ds-sign-in-form-wrapper, .ds-sign-up-form-wrapper, .ds-auth-form-wrapper"
                    )
                    if await form_root.count() == 0:
                        form_root = self.page.locator("body")
                    
                    # Fill email
                    Logger.debug(f"Entering email: {email}")
                    email_input = form_root.first.locator(
                        "input[autocomplete='username'], "
                        "input[type='text'][placeholder*='email'], "
                        "input[type='text'][placeholder*='Email'], "
                        "input[type='text'][placeholder*='Phone']"
                    )
                    if await email_input.count() == 0:
                        email_input = form_root.first.locator("input[type='text']")
                    await email_input.first.fill(email)
                    
                    # Fill password
                    Logger.debug("Entering password...")
                    password_input = form_root.first.locator(
                        "input[autocomplete='current-password'], input[type='password']"
                    )
                    await password_input.first.fill(password)
                    
                    # Click login button
                    Logger.debug("Clicking login button...")
                    login_button = form_root.first.locator("button", has_text="Log in")
                    if await login_button.count() == 0:
                        login_button = form_root.first.locator("button.ds-basic-button--primary")
                    if await login_button.count() == 0:
                        login_button = self.page.locator("button", has_text="Log in")
                    await login_button.first.click()
                    
                    # Wait for navigation back to the chat page
                    await self.page.wait_for_selector("textarea", timeout=60000)
                    Logger.success("Login successful.")

                    self.ece_mark_used(email)
                    
                except Exception as e:
                    Logger.error(f"Error during auto-login: {e}")
            else:
                Logger.info("Auto-login disabled. Waiting for manual login...")
                # Wait indefinitely (or until closed) for the user to log in and reach the chat page
                try:
                    await self.page.wait_for_selector("textarea", timeout=0)
                    Logger.success("Manual login detected.")
                except Exception as e:
                    Logger.error(f"Error waiting for manual login: {e}")
        else:
            Logger.info("DeepSeek chat UI detected (or sign-in UI not found). Continuing...")
            self._mark_active_ece_pair_used()

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
            Logger.debug(f"Failed to read DeepSeek document language: {e}")
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
        """
        Detect the current DeepSeek UI language via <html lang="...">.

        Some IntenseRP automation uses English UI text (placeholders/toggle labels),
        so a non-English DeepSeek interface can break interactions.
        """
        lang = await self._get_document_lang()
        self.last_document_lang = lang or None

        ok = self._is_english_lang(lang)
        self.ui_language_ok = ok

        if ok:
            self._non_english_ui_warned = False
            self._non_english_ui_warned_lang = None
            return True

        # Warn only once per detected language value to avoid log spam.
        if (not self._non_english_ui_warned) or (self._non_english_ui_warned_lang != lang):
            self._non_english_ui_warned = True
            self._non_english_ui_warned_lang = lang

            detected = lang or "<unset>"
            Logger.warning(
                f"DeepSeek UI language detected as '{detected}'. "
                "IntenseRP currently expects English UI (en-US). "
                "Please change DeepSeek language to English in the browser window, then refresh/reload."
            )
            if status_callback:
                status_callback("DeepSeek UI language is not English. Please change it to English (en-US).")

        return False

    async def require_english_ui(self) -> None:
        ok = await self.check_ui_language()
        if ok:
            return

        detected = self.last_document_lang or "<unset>"
        raise RuntimeError(
            f"DeepSeek UI language is not English (detected: {detected}). "
            "IntenseRP currently requires DeepSeek UI language to be English (en-US). "
            "Please change DeepSeek language to English and reload the page."
        )

    def _resolve_deepthink_flags(self, model: str) -> tuple[bool, bool]:
        enable_deepthink = bool(self.config_manager.get_setting("deepseek_behavior", "enable_deepthink"))
        send_deepthink = bool(self.config_manager.get_setting("deepseek_behavior", "send_deepthink"))

        mode = resolve_behavior_mode(model, self.provider)
        if mode == MODE_CHAT:
            return False, False
        if mode == MODE_REASONER:
            return True, send_deepthink

        return enable_deepthink, send_deepthink

    def _resolve_deepseek_request_settings(self, model: str, overrides: Optional[Dict[str, bool]] = None) -> Dict[str, bool]:
        resolved_model = (model or "").strip() or "deepseek-auto"
        deepthink_enabled, send_deepthink = self._resolve_deepthink_flags(resolved_model)
        search_enabled = bool(self.config_manager.get_setting("deepseek_behavior", "enable_search"))
        send_as_text_file = bool(self.config_manager.get_setting("deepseek_behavior", "send_as_text_file"))

        settings = {
            "deepthink_enabled": bool(deepthink_enabled),
            "send_deepthink": bool(send_deepthink),
            "search_enabled": bool(search_enabled),
            "send_as_text_file": bool(send_as_text_file),
        }

        if overrides:
            for key in ("deepthink_enabled", "send_deepthink", "search_enabled", "send_as_text_file"):
                if key in overrides:
                    settings[key] = bool(overrides[key])

        return settings

    def _get_first_chunk_timeout_s(self) -> float:
        try:
            value = float(
                self.config_manager.get_setting("deepseek_behavior", "first_chunk_timeout")
                or self.INTERCEPT_FIRST_CHUNK_TIMEOUT_S
            )
        except Exception:
            value = self.INTERCEPT_FIRST_CHUNK_TIMEOUT_S
        return max(value, 5.0)

    def _extract_deepseek_macros_from_text(self, text: str) -> tuple[str, Dict[str, bool]]:
        return extract_macro_overrides(text, macro_actions=COMMON_REQUEST_MACRO_ACTIONS)

    def _strip_deepseek_macros_from_messages(self, messages: List[Any]) -> tuple[List[Any], Dict[str, bool]]:
        return strip_macros_from_messages(messages, macro_actions=COMMON_REQUEST_MACRO_ACTIONS)

    def _read_clean_regeneration_state(self) -> Optional[Dict[str, bool]]:
        return read_clean_regeneration_state(
            self.cache_manager,
            self.clean_regen_state_cache_key,
            log_label="Clean Regeneration",
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
    ) -> Dict[str, bool]:
        return {
            "deepthink_enabled": bool(effective_deepthink),
            "search_enabled": bool(enable_search),
            "send_as_text_file": bool(send_as_text_file),
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
            "conversation_url": f"https://chat.deepseek.com/a/chat/s/{conversation_id}",
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
            method="POST",
            url="https://chat.deepseek.com/api/v0/chat_session/delete",
            body={"chat_session_id": normalized_id},
            use_xhr=True,
            referrer="https://chat.deepseek.com/",
        )
        if bool(result.get("ok")):
            return True

        detail = str(result.get("error") or result.get("text") or "").strip()
        status = int(result.get("status") or 0)
        suffix = f" ({detail[:180]})" if detail else ""
        Logger.warning(
            f"DeepSeek: failed to auto-delete chat {normalized_id} (status={status}){suffix}"
        )
        return False

    async def _auto_delete_current_chat(self) -> bool:
        current_info = await self._get_current_conversation_info()
        if current_info is None:
            Logger.debug("DeepSeek: auto-delete skipped because the current chat ID was not available.")
            return False

        conversation_id = str(current_info.get("conversation_id") or "").strip()
        if not conversation_id:
            Logger.debug("DeepSeek: auto-delete skipped because the current chat ID was empty.")
            return False

        try:
            await self._click_new_chat()
            await asyncio.sleep(0.5)
        except Exception as e:
            Logger.warning(
                f"DeepSeek: auto-delete skipped because a replacement chat could not be prepared: {e}"
            )
            return False

        if await self._delete_conversation_by_id(conversation_id):
            Logger.info("DeepSeek: auto-deleted the completed chat.")
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
            Logger.warning(f"Multi-Slot Cache (DeepSeek): failed to open cached chat URL: {e}")
            return False

        try:
            shell_state = await self._wait_for_deepseek_shell_state(timeout_ms=60000)
        except Exception as e:
            Logger.warning(f"Multi-Slot Cache (DeepSeek): chat shell did not become ready: {e}")
            return False

        return shell_state == "chat"

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
            log_label="Multi-Slot Cache (DeepSeek)",
        )
        entry = find_multi_slot_cache_entry(payload, account_key, formatted_message, multi_slot_state)
        if entry is None:
            return False

        current_info = await self._get_current_conversation_info()
        if current_info is None or current_info["conversation_id"] != entry["conversation_id"]:
            Logger.info("Multi-Slot Cache (DeepSeek): opening cached conversation for regeneration...")
            opened = await self._open_cached_conversation(entry["conversation_url"])
            if not opened:
                return False
            current_info = await self._get_current_conversation_info()
            if current_info is None or current_info["conversation_id"] != entry["conversation_id"]:
                Logger.warning(
                    "Multi-Slot Cache (DeepSeek): cached conversation URL opened, but the expected "
                    "chat ID was not available. Falling back to a new chat."
                )
                return False

        try:
            await self.set_deepthink_state(bool(multi_slot_state.get("deepthink_enabled")))
            await self.set_search_state(bool(multi_slot_state.get("search_enabled")))
            await asyncio.sleep(0.25)
        except Exception:
            pass

        Logger.info("Multi-Slot Cache (DeepSeek): cached prompt match found. Attempting to regenerate...")
        completion_armed.set()
        if not await self._click_regenerate():
            completion_armed.clear()
            Logger.warning(
                "Multi-Slot Cache (DeepSeek): regenerate button unavailable. Removing cached entry."
            )
            remove_multi_slot_cache_entry(
                self.cache_manager,
                self.multi_slot_cache_key,
                account_key,
                entry["conversation_id"],
                log_label="Multi-Slot Cache (DeepSeek)",
            )
            return False

        try:
            await asyncio.wait_for(completion_started.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            completion_armed.clear()
            Logger.warning(
                "Multi-Slot Cache (DeepSeek): completion request not observed after clicking "
                "Regenerate. Removing cached entry."
            )
            remove_multi_slot_cache_entry(
                self.cache_manager,
                self.multi_slot_cache_key,
                account_key,
                entry["conversation_id"],
                log_label="Multi-Slot Cache (DeepSeek)",
            )
            return False

        return True

    async def generate_response(self, message: Union[str, List[Any]], model: str = "deepseek-auto", stream: bool = False, temperature: float = None, top_p: float = None, max_tokens: int | None = None, abort_event: asyncio.Event = None):
        """
        Generates a response from DeepSeek.
        This function intercepts the network request to support streaming.
        """
        _ = max_tokens
        response_queue = asyncio.Queue()
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
                    Logger.debug(f"DeepSeek: failed to close intercepted response: {e}")
            try:
                await self._click_stop_button()
            except Exception as e:
                Logger.debug(f"DeepSeek: failed to click Stop during timeout handling: {e}")

        # Some selectors rely on English UI text; fail fast with a clear error instead of hanging.
        await self.require_english_ui()
        
        # Reset state for new generation
        self.fragment_types_list = []
        self.thinking_active = False
        self.abort_requested = False
        self.current_abort_event = abort_event
        self._reset_stream_parser()
        self._last_generation_censored = False
        resolved_model = (model or "").strip() or "deepseek-auto"
        self.current_model = resolved_model

        macros_overrides: Dict[str, bool] = {}
        message_for_formatting = message
        if isinstance(message, list):
            message_for_formatting, macros_overrides = self._strip_deepseek_macros_from_messages(message)
        elif isinstance(message, str):
            message_for_formatting, macros_overrides = self._extract_deepseek_macros_from_text(message)

        if macros_overrides:
            Logger.debug(f"DeepSeek macros applied: {macros_overrides}")

        effective_settings = self._resolve_deepseek_request_settings(resolved_model, overrides=macros_overrides)
        effective_deepthink = effective_settings["deepthink_enabled"]
        effective_send_deepthink = effective_settings["send_deepthink"]
        enable_search = effective_settings["search_enabled"]
        send_as_text_file = effective_settings["send_as_text_file"]
        self.current_send_deepthink = effective_send_deepthink
        
        async def handle_route(route):
            nonlocal completion_claimed, intercepted_activity_count, intercepted_response
            request = route.request
            if not completion_armed.is_set():
                await route.continue_()
                return

            async with completion_claim_lock:
                if completion_claimed:
                    await route.continue_()
                    return
                completion_claimed = True
                completion_started.set()

            Logger.info("Intercepting DeepSeek API request...")
            Logger.debug(f"Intercepted request to: {request.url}")
            
            # Prepare headers and cookies
            headers = await request.all_headers()
            # Remove headers auto-generated by httpx
            headers.pop("content-length", None)
            headers.pop("host", None)
            
            # Get cookies from the context
            cookies = await self.context.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}
            
            # Get the original post data
            post_data = request.post_data_json
            
            # Don't touch the original post data, as the ui needs what it sent
            # But we could modify it here if needed
            full_response_body = bytearray()
            response_headers = {}
            aborted = False
            
            try:
                async with httpx.AsyncClient() as client:
                    try:
                        Logger.info("Streaming response from DeepSeek...")
                        async with client.stream("POST", request.url, headers=headers, cookies=cookie_dict, json=post_data, timeout=60.0) as response:
                            intercepted_response = response
                            # Capture headers to forward them later
                            # We specifically need Content-Type so the frontend knows it's an SSE stream
                            for k, v in response.headers.items():
                                response_headers[k] = v
                            
                            async for chunk in response.aiter_bytes():
                                intercepted_activity_count += 1
                                # Check if abort was requested
                                if (
                                    intercepted_request_abort.is_set()
                                    or self.abort_requested
                                    or (abort_event and abort_event.is_set())
                                ):
                                    Logger.debug("Abort detected during streaming, stopping...")
                                    aborted = True
                                    break
                                
                                full_response_body.extend(chunk)
                                # Process chunk for streaming
                                await self._process_chunk(chunk, response_queue)

                            if (
                                not aborted
                                and (not intercepted_request_abort.is_set())
                                and not self.abort_requested
                            ):
                                await self._process_chunk(b"", response_queue, final=True)
                                
                    except httpx.ReadError as e:
                        if (
                            not aborted
                            and (not intercepted_request_abort.is_set())
                            and not self.abort_requested
                        ):
                            Logger.error(f"Read error during intercepted request: {e}")
                            await response_queue.put({"error": str(e)})
                    except Exception as e:
                        if (
                            not aborted
                            and (not intercepted_request_abort.is_set())
                            and not self.abort_requested
                        ):
                            Logger.error(f"Error during intercepted request: {e}")
                            await response_queue.put({"error": str(e)})
            except RuntimeError as e:
                # Ignore RuntimeError from async generator cleanup during abort
                if "async generator" in str(e) or "cancel scope" in str(e):
                    Logger.debug(f"Ignored expected error during abort: {e}")
                else:
                    raise
            finally:
                intercepted_response = None
            
            # Log the aborted state; the timeout/abort path already attempted a UI stop click.
            if aborted or intercepted_request_abort.is_set() or self.abort_requested:
                Logger.warning("DeepSeek generation was aborted before completion.")
            
            # Fulfill the original request so the UI updates
            try:
                if aborted or intercepted_request_abort.is_set() or self.abort_requested:
                    await route.abort()
                else:
                    # Forward the captured headers, especially Content-Type
                    await route.fulfill(body=bytes(full_response_body), status=200, headers=response_headers)
            except Exception as e:
                Logger.error(f"Error finalizing route: {e}")
            
            # Signal end of stream
            await response_queue.put(None)
            intercepted_request_finished.set()
            if (
                not aborted
                and (not intercepted_request_abort.is_set())
                and not self.abort_requested
            ):
                Logger.success("Response streaming completed.")

        # Set up interception
        await self.page.route("**/api/v0/chat/completion", handle_route)
        await self.page.route("**/api/v0/chat/regenerate", handle_route)
        
        try:
            # Apply formatting
            formatted_message = self._format_messages(message_for_formatting)
            
            # Check for Clean Regeneration
            clean_regeneration = bool(
                self.config_manager.get_setting("deepseek_behavior", "clean_regeneration")
            )
            multi_slot_cache_enabled = bool(
                clean_regeneration
                and self.config_manager.get_setting("deepseek_behavior", "multi_slot_cache")
            )
            try:
                auto_delete_requested = bool(
                    self.config_manager.get_setting("deepseek_behavior", "auto_delete_chats")
                )
            except Exception:
                auto_delete_requested = False
            auto_delete_enabled = bool(auto_delete_requested and (not clean_regeneration))
            if auto_delete_requested and clean_regeneration:
                Logger.warning(
                    "DeepSeek: Delete Chat After Reply is skipped for this request because "
                    "Reuse Matching Chat is enabled."
                )
            regenerated = False
            current_cache_matched = False
            should_record_multi_slot = False
            clean_regen_state = None
            multi_slot_state = None
            
            if clean_regeneration:
                clean_regen_state = self._build_multi_slot_cache_state(
                    effective_deepthink=bool(effective_deepthink),
                    enable_search=bool(enable_search),
                    send_as_text_file=bool(send_as_text_file),
                )
                multi_slot_state = dict(clean_regen_state)

                last_message = self.cache_manager.read_cache(self.clean_regen_message_cache_key)
                last_state = self._read_clean_regeneration_state()

                message_matches = last_message == formatted_message
                state_matches = last_state == clean_regen_state

                if message_matches and state_matches:
                    current_cache_matched = True
                    Logger.info("Clean Regeneration: Message and settings match cache. Attempting to regenerate...")
                    completion_armed.set()
                    if await self._click_regenerate():
                        Logger.info("Clean Regeneration: Button clicked. Regenerating...")
                        try:
                            await asyncio.wait_for(completion_started.wait(), timeout=20.0)
                        except asyncio.TimeoutError:
                            Logger.warning(
                                "Clean Regeneration: completion request not observed after clicking "
                                "Regenerate. Falling back to new chat."
                            )
                        else:
                            regenerated = True
                            self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                            self._write_clean_regeneration_state(clean_regen_state)
                    else:
                        Logger.warning("Clean Regeneration: Button not found or disabled. Falling back to new chat.")
                elif message_matches and not state_matches:
                    Logger.info("Clean Regeneration: Message matches cache but settings changed. Creating new chat.")
                else:
                    Logger.debug("Clean Regeneration: Message differs from cache. Creating new chat.")

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
                # Trigger UI interaction
                # Clear previous chat by clicking New Chat
                Logger.info("Preparing new chat session...")
                await self._click_new_chat()
                # Small wait for the UI to update
                await asyncio.sleep(0.5)
                
                # Apply settings before sending
                await self.set_deepthink_state(effective_deepthink)
                await self.set_search_state(enable_search)
                
                # Small delay for the toggles to take effect
                await asyncio.sleep(0.5)
                
                # Check if we should send as text file
                if send_as_text_file:
                    Logger.info("Sending message as text file...")
                    file_payload = {
                        "name": "prompt.txt",
                        "mimeType": "text/plain",
                        "buffer": formatted_message.encode("utf-8"),
                    }
                    await self._upload_file(file_payload)
                    
                    # Get timeout from settings
                    upload_timeout = self.config_manager.get_setting("deepseek_behavior", "file_upload_timeout")
                    Logger.info("Sending request to DeepSeek...")
                    completion_armed.set()
                    await self._send_message(timeout=upload_timeout)
                else:
                    await self._enter_message(formatted_message)
                    Logger.info("Sending request to DeepSeek...")
                    completion_armed.set()
                    await self._send_message()
                
                # Update cache
                if clean_regeneration:
                    self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                    self._write_clean_regeneration_state(clean_regen_state)
                    should_record_multi_slot = bool(multi_slot_cache_enabled and multi_slot_state)

            if not completion_started.is_set():
                try:
                    await asyncio.wait_for(completion_started.wait(), timeout=20.0)
                except asyncio.TimeoutError:
                    Logger.error(
                        "DeepSeek: completion request was not observed. "
                        "The UI may have swallowed the click or the endpoint changed."
                    )
                    yield f"data: {json.dumps({'error': 'DeepSeek: completion request not observed'})}\n\n"
                    return
            
            # Yield responses from queue
            stream_had_error = False
            async for item in self._iterate_response_queue(
                response_queue,
                abort_event=abort_event,
                first_chunk_timeout_s=self._get_first_chunk_timeout_s(),
                idle_timeout_s=self.INTERCEPT_IDLE_TIMEOUT_S,
                on_timeout=abort_intercepted_request,
                activity_counter=get_intercepted_activity_count,
            ):
                if item is None:
                    break
                if isinstance(item, dict) and "error" in item:
                    stream_had_error = True
                    yield f"data: {json.dumps(item)}\n\n"
                    break
                
                yield item

            if should_record_multi_slot and (not stream_had_error) and (not self.abort_requested):
                if self._last_generation_censored:
                    Logger.info(
                        "Multi-Slot Cache (DeepSeek): skipping cache save because the conversation "
                        "was censored."
                    )
                else:
                    conversation_info = await self._wait_for_current_conversation_info(timeout_ms=6000)
                    if conversation_info is None:
                        Logger.debug(
                            "Multi-Slot Cache (DeepSeek): could not resolve conversation URL after "
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
                            log_label="Multi-Slot Cache (DeepSeek)",
                        )

            if (
                auto_delete_enabled
                and (not stream_had_error)
                and (not self.abort_requested)
                and not (abort_event and abort_event.is_set())
            ):
                await self._auto_delete_current_chat()
                
        finally:
            if completion_started.is_set() and not intercepted_request_finished.is_set():
                try:
                    await asyncio.wait_for(intercepted_request_finished.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    Logger.debug("DeepSeek: timed out waiting for intercepted request cleanup.")
            # Cleanup interception
            self.current_abort_event = None
            self.abort_requested = False
            self.current_model = None
            self.current_send_deepthink = None
            self._last_generation_censored = False
            self._reset_stream_parser()
            try:
                await self.page.unroute("**/api/v0/chat/completion")
            except Exception:
                pass
            try:
                await self.page.unroute("**/api/v0/chat/regenerate")
            except Exception:
                pass

    async def abort_generation(self):
        """
        Aborts the current generation request.
        Called by the API when client disconnects.
        """
        Logger.info("Abort generation requested...")
        self.abort_requested = True
        if self.current_abort_event:
            self.current_abort_event.set()
        # Click the stop button in DeepSeek UI
        await self._click_stop_button()

    def _deepseek_signature_looks_like_stop(self, signature: str | None) -> bool:
        if not signature:
            return False
        lowered = signature.lower()
        return any(token in lowered for token in ("stop", "cancel", "abort", "pause", "square"))

    async def _click_stop_button(self):
        """
        Clicks the Stop button in DeepSeek UI to cancel the ongoing generation.
        The Stop button appears in place of the Send button during generation.
        """
        try:
            stop_button = self.page.locator("div.ds-icon-button._7436101")
            if await stop_button.count() == 0:
                Logger.debug("Stop button not found.")

                return False

            is_disabled = await stop_button.get_attribute("aria-disabled")
            if is_disabled == "true":
                Logger.debug("Stop button is disabled (generation may have already stopped).")
                return False

            current_signature = await self._read_control_signature(stop_button)
            cached_send_signature = getattr(self, "_send_control_signature", None)
            if cached_send_signature and current_signature == cached_send_signature:
                Logger.debug("Composer control matches send mode. Skipping stop click.")
                return False
            if (not cached_send_signature) and (not self._deepseek_signature_looks_like_stop(current_signature)):
                Logger.debug("Composer control could not be verified as stop mode.")
                return False

            Logger.debug("Clicking Stop button...")
            await stop_button.click()
            Logger.debug("Stop button clicked successfully.")
            return True
        except Exception as e:
            Logger.error(f"Error clicking stop button: {e}")
            return False

    def _format_messages(self, messages: Union[str, List[Any]]) -> str:
        return format_request_messages(self.config_manager, messages)

    async def _process_sse_line(self, line: str, queue: asyncio.Queue) -> None:
        if not line.startswith("data:"):
            return

        data_str = line[len("data:") :].strip()
        if data_str == "[DONE]":
            return

        try:
            # Cache settings once per chunk processing
            anti_censorship = self.config_manager.get_setting("deepseek_behavior", "anti_censorship")
            send_deepthink = (
                self.current_send_deepthink
                if self.current_send_deepthink is not None
                else self.config_manager.get_setting("deepseek_behavior", "send_deepthink")
            )
            data = json.loads(data_str)
            content = ""
            finish_reason = None
            
            # Normalize updates to a list of operations
            ops = []
            
            if "v" in data:
                v = data["v"]
                p = data.get("p")
                o = data.get("o")
                
                # Case 1: Batch update (v is list of ops)

                # ---------------- RYAN!! ----------------
                    # TO RYAN: STOP REMOVING COMMENTS
                    # I KNOW YOU HATE THEIR COLOR BUT THEY'RE FOR CONTRIBUTORS
                    # YOU CAN JUST USE A DARK THEME IF IT BOTHERS YOU
                # ---------------- RYAN!! ----------------

                if p is None or (p == "response" and o == "BATCH"):
                    if isinstance(v, list):
                        ops = v
                    elif isinstance(v, str):
                        # Direct content update (inconsistent here - once I caught this happening but it seems like a bug on their side)
                        if getattr(self, "thinking_active", False):
                            if send_deepthink:
                                content = v
                        else:
                            content = v
                    elif isinstance(v, dict):
                        # Initial response payload: {"response": {"fragments": [...]}}
                        # DeepSeek now sends the first fragment inline in the
                        # opening payload rather than as a separate APPEND event
                        response_obj = v.get("response", v)
                        if isinstance(response_obj, dict):
                            fragments = response_obj.get("fragments")
                            if isinstance(fragments, list) and fragments:
                                ops = [{"p": "response/fragments", "o": "APPEND", "v": fragments}]
            
                # Case 2: Single Path-based update
                else:
                    ops = [{"p": p, "o": o, "v": v}]

            # Process all operations
            should_stop_processing = False
            
            for item in ops:
                if not isinstance(item, dict):
                    continue
                    
                item_p = item.get("p")
                item_o = item.get("o")
                item_v = item.get("v")
                

                
                # Check for Anti-Censorship (CONTENT_FILTER)
                if item_p in ("status", "response/status") and item_v == "CONTENT_FILTER":
                    self._last_generation_censored = True

                if anti_censorship:
                    if item_p in ("status", "response/status") and item_v == "CONTENT_FILTER":
                        Logger.info("Anti-Censorship triggered: Suppressing refusal message.")
                        finish_reason = "stop"
                        if getattr(self, "thinking_active", False):
                            if send_deepthink:
                                content += "</think>"
                            self.thinking_active = False
                        should_stop_processing = True
                        break

                # Status update
                if item_p in ("status", "response/status"):
                    if item_v == "FINISHED":
                        finish_reason = "stop"
                        # Close think tag if open
                        if getattr(self, "thinking_active", False):
                            if send_deepthink:
                                content += "</think>"
                            self.thinking_active = False
                
                # Fragments append (New Fragment)
                # Handle both 'fragments' and 'response/fragments'
                elif (item_p == "fragments" or item_p == "response/fragments") and item_o == "APPEND":
                    fragments = item_v
                    if isinstance(fragments, list):
                        for frag in fragments:
                            if isinstance(frag, dict):
                                frag_type = frag.get("type")
                                # Store type by index (len of list before append)
                                if not hasattr(self, "fragment_types_list"):
                                    self.fragment_types_list = []
                                self.fragment_types_list.append(frag_type)
                                

                                
                                # Handle THINK start
                                if frag_type == "THINK":
                                    if send_deepthink:
                                        content += "<think>"
                                    self.thinking_active = True
                                
                                # Handle RESPONSE start (end of THINK if active)
                                if frag_type == "RESPONSE" and getattr(self, "thinking_active", False):
                                    if send_deepthink:
                                        content += "</think>"
                                    self.thinking_active = False
                                
                                # Initial content
                                if "content" in frag:
                                    if frag_type == "THINK":
                                        if send_deepthink:
                                            content += frag["content"]
                                    elif frag_type == "SEARCH":
                                        pass
                                    else:
                                        content += frag["content"]

                # Content update: response/fragments/0/content OR fragments/0/content
                elif item_p and (item_p.startswith("response/fragments/") or item_p.startswith("fragments/")) and item_p.endswith("/content"):
                    try:
                        parts = item_p.split("/")
                        # Index is 2 if response/fragments/0/content, or 1 if fragments/0/content
                        if parts[0] == "response":
                            index = int(parts[2])
                        else:
                            index = int(parts[1])
                        
                        if hasattr(self, "fragment_types_list") and index < len(self.fragment_types_list):
                            frag_type = self.fragment_types_list[index]
                            
                            if frag_type == "THINK":
                                if send_deepthink:
                                    content += str(item_v)
                            elif frag_type == "SEARCH":
                                pass
                            else:
                                content += str(item_v)
                        else:
                            pass
                    except (ValueError, IndexError):
                        pass
                        
                # Status update: response/fragments/0/status
                elif item_p and (item_p.startswith("response/fragments/") or item_p.startswith("fragments/")) and item_p.endswith("/status"):
                    if item_v == "FINISHED":
                        pass

            if should_stop_processing:
                pass

            if content or finish_reason:
                model_name = self.current_model or "deepseek-auto"
                openai_chunk = {
                    "id": "chatcmpl-custom",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content} if content else {},
                            "finish_reason": finish_reason
                        }
                    ]
                }
                await queue.put(f"data: {json.dumps(openai_chunk)}\n\n")
                
        except json.JSONDecodeError:
            pass
        except Exception as e:
            Logger.error(f"Error processing stream line: {e}")

    async def _process_chunk(self, chunk: bytes, queue: asyncio.Queue, *, final: bool = False):
        try:
            self._stream_text_buffer += self._stream_text_decoder.decode(chunk, final=final)

            while True:
                newline_idx = self._stream_text_buffer.find("\n")
                if newline_idx == -1:
                    break

                line = self._stream_text_buffer[:newline_idx].rstrip("\r")
                self._stream_text_buffer = self._stream_text_buffer[newline_idx + 1 :]
                await self._process_sse_line(line, queue)

            if final and self._stream_text_buffer.strip():
                line = self._stream_text_buffer.rstrip("\r")
                self._stream_text_buffer = ""
                await self._process_sse_line(line, queue)
        except Exception as e:
            Logger.error(f"Error processing chunk: {e}")

    async def set_deepthink_state(self, state: bool):
        """
        Toggles the DeepThink mode to the desired state.
        """
        # this toggle used to be a <button>, but is now often a <div role="button">.
        button = self.page.locator(".ds-toggle-button", has_text="DeepThink")
        if await button.count() == 0:
            button = self.page.locator("[role='button']", has_text="DeepThink")
        
        if await button.count() == 0:
            Logger.warning("DeepThink button not found.")
            return

        class_attr = await button.first.get_attribute("class") or ""
        is_selected = "ds-toggle-button--selected" in class_attr
        
        if is_selected != state:
            Logger.debug(f"Toggling DeepThink to {state}...")
            await button.first.click()
        else:
            Logger.debug(f"DeepThink is already {state}.")

    async def set_search_state(self, state: bool):
        """
        Toggles the Search mode to the desired state.
        """
        # this toggle used to be a <button>, but is now often a <div role="button">.
        button = self.page.locator(".ds-toggle-button", has_text="Search")
        if await button.count() == 0:
            button = self.page.locator("[role='button']", has_text="Search")
        
        if await button.count() == 0:
            Logger.warning("Search button not found.")
            return

        class_attr = await button.first.get_attribute("class") or ""
        is_selected = "ds-toggle-button--selected" in class_attr
        
        if is_selected != state:
            Logger.debug(f"Toggling Search to {state}...")
            await button.first.click()
        else:
            Logger.debug(f"Search is already {state}.")

    async def set_sidebar_status(self, open: bool):
        """
        Sets the sidebar status to open or closed.
        """
        # Sidebar visibility is controlled via hashed classes that DeepSeek changes frequently.
        # when hidden, the sidebar container gains "a02af2e6" (removed when visible).

        sidebar_wrapper_selector = "div.dc04ec1d"
        sidebar_hidden_class = "a02af2e6"
        close_button_selector = "div.ds-icon-button._7d1f5e2"
        open_button_selector = "div.e5bf614e >> div.ds-icon-button._4f3769f >> nth=0"

        async def _is_sidebar_hidden() -> Optional[bool]:
            wrapper = self.page.locator(sidebar_wrapper_selector)
            if await wrapper.count() > 0:
                class_attr = await wrapper.first.get_attribute("class") or ""
                return sidebar_hidden_class in class_attr

            # Fallback heuristics if wrapper selector changes.
            close_btn = self.page.locator(close_button_selector)
            if await close_btn.count() > 0 and await close_btn.first.is_visible():
                return False

            open_btn = self.page.locator(open_button_selector)
            if await open_btn.count() > 0 and await open_btn.first.is_visible():
                return True

            return None

        is_hidden = await _is_sidebar_hidden()

        if open:
            if is_hidden is False:
                Logger.debug("Sidebar is already open.")
                return

            Logger.debug("Opening sidebar...")
            open_btn = self.page.locator(open_button_selector)
            if await open_btn.count() == 0:
                Logger.warning("Open sidebar button not found.")
                return

            try:
                await open_btn.click(timeout=2000)
            except Exception as e:
                Logger.warning(f"Failed to click open sidebar button: {e}")
                return

        else:
            if is_hidden is True:
                Logger.debug("Sidebar is already closed.")
                return

            Logger.debug("Closing sidebar...")
            close_btn = self.page.locator(close_button_selector)
            if await close_btn.count() == 0:
                Logger.warning("Close sidebar button not found.")
                return

            try:
                await close_btn.click(timeout=2000)
            except Exception as e:
                Logger.warning(f"Failed to click close sidebar button: {e}")
                return

    async def click_new_chat(self, source: str = "auto"):
        """
        Clicks the New Chat button.
        """
        # DeepSeek changes their UI classes often; still relying on hashes because the structure is messed up.
        # Sidebar open: "New chat" is a text button.
        # Sidebar closed: quick actions show 2 icon buttons.
        # Note: quick actions are removed from DOM when sidebar is open. The sidebar is NOT removed when closed, it just gets a new class.

        sidebar_wrapper_selector = "div.dc04ec1d"
        sidebar_hidden_class = "a02af2e6"
        quick_action_container_selector = "div.e5bf614e"
        quick_action_button_class = "_4f3769f"
        sidebar_new_chat_selector = "div._5a8ac7a.a084f19e"

        quick_new_chat_selector = (
            f"{quick_action_container_selector} >> div.ds-icon-button.{quick_action_button_class} >> nth=1"
        )

        async def _is_sidebar_hidden() -> Optional[bool]:
            wrapper = self.page.locator(sidebar_wrapper_selector)
            if await wrapper.count() > 0:
                class_attr = await wrapper.first.get_attribute("class") or ""
                return sidebar_hidden_class in class_attr

            # Fallback heuristics if wrapper selector changes.
            close_btn = self.page.locator("div.ds-icon-button._7d1f5e2")
            if await close_btn.count() > 0 and await close_btn.first.is_visible():
                return False

            quick_actions = self.page.locator(quick_action_container_selector)
            if await quick_actions.count() > 0 and await quick_actions.first.is_visible():
                return True

            return None

        async def _click_sidebar_new_chat() -> bool:
            btn = self.page.locator(sidebar_new_chat_selector)
            if await btn.count() > 0 and await btn.first.is_visible():
                is_disabled = (await btn.first.get_attribute("aria-disabled")) == "true"
                if not is_disabled:
                    Logger.debug("Clicking New Chat (Sidebar)...")
                    await btn.first.click(timeout=2000)
                    return True

            # Fallback: locate by visible text
            btn = self.page.locator("div[tabindex='0']", has_text="New chat")
            if await btn.count() > 0 and await btn.first.is_visible():
                Logger.debug("Clicking New Chat (Sidebar text)...")
                await btn.first.click(timeout=2000)
                return True

            return False

        async def _click_quick_new_chat() -> bool:
            btn = self.page.locator(quick_new_chat_selector)
            if await btn.count() > 0 and await btn.first.is_visible():
                is_disabled = (await btn.first.get_attribute("aria-disabled")) == "true"
                if not is_disabled:
                    Logger.debug("Clicking New Chat (Quick action)...")
                    await btn.first.click(timeout=2000)
                    return True
            return False

        try:
            if source == "sidebar":
                if not await _click_sidebar_new_chat():
                    Logger.warning("New Chat (Sidebar) button not found.")
                return

            if source == "simple":
                if not await _click_quick_new_chat():
                    Logger.warning("New Chat (Quick action) button not found.")
                return

            if source != "auto":
                Logger.warning(f"Unknown source: {source}")
                return

            Logger.debug("Attempting to click New Chat (Auto)...")
            is_hidden = await _is_sidebar_hidden()

            # If sidebar is open, quick actions are removed; prefer the sidebar button.
            if is_hidden is False:
                if await _click_sidebar_new_chat():
                    return
                # If our state detection is wrong or UI changed, try quick action as a fallback.
                if await _click_quick_new_chat():
                    return
                Logger.warning("Sidebar appears open, but New Chat button was not found.")
                return

            # If sidebar is hidden, quick actions should exist; prefer quick action.
            if is_hidden is True:
                if await _click_quick_new_chat():
                    return
                # Fallback: open sidebar and try the sidebar button.
                await self.set_sidebar_status(open=True)
                if await _click_sidebar_new_chat():
                    return
                Logger.warning("Sidebar appears hidden, but New Chat button was not found.")
                return

            # Unknown state: try both, then try opening sidebar as a last resort.
            if await _click_quick_new_chat():
                return
            if await _click_sidebar_new_chat():
                return

            await self.set_sidebar_status(open=True)
            if await _click_sidebar_new_chat():
                return

            Logger.warning("Could not find New Chat button in either mode.")
        except Exception as e:
            Logger.error(f"Error clicking New Chat: {e}")

    async def enter_message(self, message: str):
        """
        Public wrapper for entering a message.
        """
        await self._enter_message(message)

    async def send_message(self, timeout: int = None):
        """
        Public wrapper for sending a message.
        """
        await self._send_message(timeout=timeout)

    async def _enter_message(self, message: str):
        """
        Enters the message into the chat input textarea.
        """
        # The textarea has placeholder "Message DeepSeek"
        textarea = self.page.locator("textarea[placeholder='Message DeepSeek']")
        if await textarea.count() == 0:
            textarea = self.page.locator("textarea")
            if await textarea.count() == 0:
                Logger.warning("Message textarea not found.")
                return
        Logger.debug(f"Entering message: {message[:50]}..." if len(message) > 50 else f"Entering message: {message}")
        await textarea.first.fill(message)

    async def _send_message(self, timeout: int = None):
        """
        Clicks the send button if it is enabled.
        Waits up to timeout seconds for the button to become enabled.
        """
        # The send button is a div with role="button" and class "ds-icon-button"
        # The send button has a specific hashed class "_7436101"
        send_button = self.page.locator("div.ds-icon-button._7436101")
        
        if await send_button.count() > 0:
            await self._remember_send_control_signature(send_button)
            # If timeout is provided, wait for the button to be enabled
            if timeout and timeout > 0:
                Logger.debug(f"Waiting up to {timeout} seconds for send button to be enabled...")
                start_time = time.time()
                while time.time() - start_time < timeout:
                    is_disabled = await send_button.get_attribute("aria-disabled") == "true"
                    if not is_disabled:
                        break
                    await asyncio.sleep(0.5)
            
            is_disabled = await send_button.get_attribute("aria-disabled") == "true"
            if not is_disabled:
                Logger.debug("Clicking send button...")
                await send_button.click()
            else:
                Logger.warning("Send button is disabled. Cannot send message.")
        else:
            Logger.warning("Send button could not be located.")

    async def _click_new_chat(self):
        """
        Clicks the New Chat button.
        """
        await self.click_new_chat(source="auto")

    async def _click_regenerate(self) -> bool:
        """
        Clicks the regenerate button.
        Returns True if successful, False otherwise.
        """
        # DeepSeek changes their UI classes often; hence we avoid relying on hashed class names.
        # In the current UI, regenerate is the 2nd "control" icon-button (nth=1) in the control bar
        # that appears right after the last assistant message.
        try:
            assistant_messages = self.page.locator("div.ds-message:has(.ds-markdown)")
            assistant_count = await assistant_messages.count()

            candidate_containers = []

            if assistant_count > 0:
                last_assistant = assistant_messages.nth(assistant_count - 1)
                # The control bar is typically the first ds-flex sibling after the message that contains icon buttons.
                candidate_containers.append(
                    last_assistant.locator(
                        "xpath=following-sibling::*[self::div[contains(@class,'ds-flex')] and .//div[contains(@class,'ds-icon-button')]][1]"
                    )
                )

            # Fallback: scan for the last visible ds-flex that has at least 2 icon buttons (excluding the input area).
            candidate_containers.append(self.page.locator("div.ds-flex:has(.ds-icon-button)"))

            for container in candidate_containers:
                container_count = await container.count()
                for i in range(container_count - 1, -1, -1):
                    bar = container.nth(i)
                    # Skip the composer/input area.
                    if await bar.locator("textarea").count() > 0:
                        continue

                    buttons = bar.locator(".ds-icon-button")
                    if await buttons.count() < 2:
                        continue

                    regen_button = buttons.nth(1)
                    if not await regen_button.is_visible():
                        continue

                    is_disabled = (await regen_button.get_attribute("aria-disabled")) == "true"
                    if is_disabled:
                        Logger.warning("Regenerate button is disabled (likely due to censorship).")
                        return False

                    Logger.debug("Clicking regenerate button...")
                    await regen_button.click()
                    return True

            Logger.warning("Regenerate button not found.")
            return False
        except Exception as e:
            Logger.error(f"Error clicking regenerate button: {e}")
            return False

    async def upload_file(self, file_spec: Any) -> None:
        """
        Public wrapper for uploading a file.
        """
        await self._upload_file(file_spec)

    async def _upload_file(self, file_spec: Any):
        """
        Uploads a file to the chat.

        file_spec can be a path (str/Path) or a file payload dict supported by Playwright
        (e.g. {"name": "...", "mimeType": "...", "buffer": b"..."}).
        """
        try:
            if isinstance(file_spec, dict):
                name = file_spec.get("name", "<payload>")
                buffer = file_spec.get("buffer")
                size = len(buffer) if isinstance(buffer, (bytes, bytearray)) else None
                size_info = f" ({size} bytes)" if size is not None else ""
                Logger.debug(f"Uploading file payload: {name}{size_info}")
            else:
                Logger.debug(f"Uploading file: {file_spec}")
        except Exception:
            Logger.debug("Uploading file (details unavailable).")
        
        # The file input is hidden or styled, but we can target it by type="file"
        file_input = self.page.locator("input[type='file']")
        
        if await file_input.count() > 0:
            await file_input.set_input_files(file_spec)
            Logger.debug("File set to input.")
            
            # Wait a bit for the upload to be processed by the UI
            # You might need to wait for a specific indicator that the file is ready
            await asyncio.sleep(1.0) 
        else:
            Logger.warning("File input not found.")
