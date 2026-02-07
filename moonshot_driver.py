import asyncio
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Union

import httpx
from dotenv import load_dotenv

from deepseek_driver import DeepSeekDriver
from drivers.providers import DriverProvider
from utils.logger import Logger

load_dotenv()


class MoonshotDriver(DeepSeekDriver):
    CHAT_ROUTE_GLOB = "**/apiv2/kimi.gateway.chat.v1.ChatService/Chat*"
    REGEN_ROUTE_GLOB = "**/apiv2/kimi.gateway.chat.v1.ChatService/RegenerateMessage*"
    CONNECT_MAX_FRAME_BYTES = 8 * 1024 * 1024
    MODEL_INSTANT = "K2.5 Instant"
    MODEL_THINKING = "K2.5 Thinking"
    MODEL_CHAT_API = "moonshot-chat"
    MODEL_REASONER_API = "moonshot-reasoner"
    INTERCEPT_FIRST_CHUNK_TIMEOUT_S = 45.0
    INTERCEPT_IDLE_TIMEOUT_S = 75.0

    def __init__(self, config_manager):
        super().__init__(config_manager)
        self.provider = DriverProvider.MOONSHOT_KIMI

        self.current_model = None
        self.current_send_deepthink = None

        self.clean_regen_message_cache_key = "moonshot_last_message.txt"
        self.clean_regen_state_cache_key = "moonshot_last_message_state.json"

        self._connect_buffer = bytearray()
        self._search_and_think_warned = False
        self._degrade_notice_logged = False

    def get_start_url(self) -> str:
        return "https://www.kimi.com/"

    def _ece_requires_auto_login(self) -> bool:
        # Moonshot/Kimi login is manual Google flow; ECE still helps pick account/profile identity.
        return False

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().lower()

    def _mark_active_ece_pair_used(self) -> None:
        pair = self.ece_active_pair()
        email = getattr(pair, "email", None) if pair else None
        if isinstance(email, str) and email.strip():
            self.ece_mark_used(email)

    async def _read_user_name(self) -> str:
        if not self.page:
            return ""

        selectors = [
            "aside.sidebar span.user-name",
            "div.user-info-container span.user-name",
            "span.user-name",
        ]

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                if await locator.count() == 0:
                    continue
                text = (await locator.first.inner_text() or "").strip()
                if text:
                    return text
            except Exception:
                continue

        return ""

    async def _is_logged_in(self) -> bool:
        user_name = await self._read_user_name()
        if not user_name:
            return False
        return self._normalize_text(user_name) != "log in"

    async def _wait_until_logged_in(self, timeout_ms: int = 0) -> bool:
        start = time.time()
        timeout_s = 0.0 if timeout_ms <= 0 else (timeout_ms / 1000.0)

        while True:
            if await self._is_logged_in():
                return True
            if timeout_s > 0.0 and (time.time() - start) >= timeout_s:
                return False
            await asyncio.sleep(0.5)

    async def _click_google_login_and_get_popup(self):
        if not self.page:
            return None

        google_button = await self._find_first_visible(
            [
                "div.login-modal-content div.google-login-btn",
                "div.google-login-btn",
            ],
            timeout_ms=8000,
        )
        if google_button is None:
            Logger.warning("Moonshot / Kimi: Google login button not found.")
            return None

        popup_task = None
        popup = None
        if self.context:
            try:
                popup_task = asyncio.create_task(self.context.wait_for_event("page", timeout=10000))
            except Exception:
                popup_task = None

        try:
            await google_button.click()
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: failed to click Google login button: {e}")
            if popup_task and (not popup_task.done()):
                popup_task.cancel()
            return None

        if popup_task:
            try:
                popup = await popup_task
            except Exception:
                popup = None

        return popup

    async def login(self):
        if not self.page:
            return

        await self.set_sidebar_status(open=True)

        if await self._is_logged_in():
            Logger.info("Moonshot / Kimi: already signed in.")
            self._mark_active_ece_pair_used()
            return

        auto_login = bool(self.config_manager.get_setting("providers_credentials", "auto_login"))
        if auto_login:
            Logger.info(
                "Moonshot / Kimi: credential-based auto-login is intentionally disabled; "
                "manual Google sign-in is required."
            )

        user_info_container = await self._find_first_visible(
            [
                "aside.sidebar div.user-info-container",
                "div.user-info-container",
            ],
            timeout_ms=15000,
        )
        if user_info_container is None:
            Logger.warning("Moonshot / Kimi: user-info container not found. Waiting for manual login...")
            await self._wait_until_logged_in(timeout_ms=0)
            return

        try:
            await user_info_container.click()
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: failed to open login modal: {e}")
            await self._wait_until_logged_in(timeout_ms=0)
            return

        try:
            await self.page.wait_for_selector("div.login-modal-content, div.google-login-btn", timeout=8000)
        except Exception:
            if await self._is_logged_in():
                Logger.info("Moonshot / Kimi: login already completed.")
                return
            Logger.warning("Moonshot / Kimi: login modal did not appear in time.")

        await self._click_google_login_and_get_popup()
        Logger.info("Moonshot / Kimi: waiting for manual Google login...")

        self.notify_user(
            "Moonshot / Kimi Login",
            "Complete the Google login flow in the browser tab/window, then return to IntenseRP.",
            level="warning",
        )

        await self._wait_until_logged_in(timeout_ms=0)
        Logger.success("Moonshot / Kimi: login detected.")
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
            Logger.debug(f"Failed to read Moonshot / Kimi document language: {e}")
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

        if (not self._non_english_ui_warned) or (self._non_english_ui_warned_lang != lang):
            self._non_english_ui_warned = True
            self._non_english_ui_warned_lang = lang

            detected = lang or "<unset>"
            Logger.warning(
                f"Moonshot / Kimi UI language detected as '{detected}'. "
                "IntenseRP currently expects English UI (en-US). "
                "Please change Kimi language to English in the browser window, then refresh/reload."
            )
            if status_callback:
                status_callback("Moonshot / Kimi UI language is not English. Please change it to English (en-US).")

        return False

    async def require_english_ui(self) -> None:
        ok = await self.check_ui_language()
        if ok:
            return

        detected = self.last_document_lang or "<unset>"
        raise RuntimeError(
            f"Moonshot / Kimi UI language is not English (detected: {detected}). "
            "IntenseRP currently requires Moonshot / Kimi UI language to be English (en-US). "
            "Please change Kimi language to English and reload the page."
        )

    def _resolve_deepthink_flags(self, model: str) -> tuple[bool, bool]:
        enable_deepthink = bool(self.config_manager.get_setting("moonshot_behavior", "enable_deepthink"))
        send_deepthink = bool(self.config_manager.get_setting("moonshot_behavior", "send_deepthink"))
        normalized = (model or "").strip().lower()

        if normalized == self.MODEL_CHAT_API:
            return False, False
        if normalized == self.MODEL_REASONER_API:
            return True, send_deepthink

        return enable_deepthink, send_deepthink

    def _resolve_moonshot_request_settings(self, model: str, overrides: Optional[Dict[str, bool]] = None) -> Dict[str, bool]:
        _ = (model or "").strip() or "moonshot-auto"
        deepthink_enabled, send_deepthink = self._resolve_deepthink_flags(model)
        search_enabled = bool(self.config_manager.get_setting("moonshot_behavior", "enable_search"))
        send_as_text_file = bool(self.config_manager.get_setting("moonshot_behavior", "send_as_text_file"))

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

        if settings["deepthink_enabled"] and settings["search_enabled"] and (not self._search_and_think_warned):
            self._search_and_think_warned = True
            Logger.warning(
                "Moonshot / Kimi: Search and Thinking are both enabled. "
                "This can produce multi-stage reasoning streams that some clients (including SillyTavern) may not parse cleanly."
            )

        return settings

    def _extract_moonshot_macros_from_text(self, text: str) -> tuple[str, Dict[str, bool]]:
        if not text:
            return text, {}

        macro_actions: Dict[str, tuple[str, bool]] = {
            "think": ("deepthink_enabled", True),
            "r1": ("deepthink_enabled", True),
            "nothink": ("deepthink_enabled", False),
            "no_think": ("deepthink_enabled", False),
            "r0": ("deepthink_enabled", False),
            "search": ("search_enabled", True),
            "nosearch": ("search_enabled", False),
            "no_search": ("search_enabled", False),
            "no-search": ("search_enabled", False),
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

    def _strip_moonshot_macros_from_messages(self, messages: List[Any]) -> tuple[List[Any], Dict[str, bool]]:
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

        cleaned_content, overrides = self._extract_moonshot_macros_from_text(content)
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

    @staticmethod
    def _coerce_request_body_bytes(value: Any) -> bytes | None:
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if isinstance(value, str):
            return value.encode("utf-8")
        return None

    def _extract_request_body_bytes(self, request) -> bytes | None:
        for attr_name in ("post_data_buffer", "post_data"):
            try:
                value = getattr(request, attr_name)
            except Exception:
                continue

            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue

            body = self._coerce_request_body_bytes(value)
            if body is not None:
                return body

        try:
            json_payload = request.post_data_json
        except Exception:
            json_payload = None
        if json_payload is not None:
            try:
                return json.dumps(json_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            except Exception:
                return None

        return None

    async def generate_response(
        self,
        message: Union[str, List[Any]],
        model: str = "moonshot-auto",
        stream: bool = False,
        temperature: float = None,
        top_p: float = None,
        abort_event: asyncio.Event = None,
    ):
        _ = (stream, temperature, top_p)
        response_queue = asyncio.Queue()

        await self.require_english_ui()

        self._connect_buffer = bytearray()
        self.thinking_active = False
        self.abort_requested = False
        self.current_abort_event = abort_event
        self._degrade_notice_logged = False

        resolved_model = (model or "").strip() or "moonshot-auto"
        self.current_model = resolved_model

        macros_overrides: Dict[str, bool] = {}
        message_for_formatting = message
        if isinstance(message, list):
            message_for_formatting, macros_overrides = self._strip_moonshot_macros_from_messages(message)
        elif isinstance(message, str):
            message_for_formatting, macros_overrides = self._extract_moonshot_macros_from_text(message)

        if macros_overrides:
            Logger.debug(f"Moonshot / Kimi macros applied: {macros_overrides}")

        effective_settings = self._resolve_moonshot_request_settings(resolved_model, overrides=macros_overrides)
        effective_deepthink = effective_settings["deepthink_enabled"]
        effective_send_deepthink = effective_settings["send_deepthink"]
        enable_search = effective_settings["search_enabled"]
        send_as_text_file = effective_settings["send_as_text_file"]
        self.current_send_deepthink = effective_send_deepthink

        async def handle_route(route):
            request = route.request
            Logger.info("Intercepting Moonshot / Kimi API request...")
            Logger.debug(f"Intercepted request to: {request.url}")

            headers = await request.all_headers()
            headers.pop("content-length", None)
            headers.pop("host", None)

            cookies = await self.context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}
            request_body = self._extract_request_body_bytes(request)

            full_response_body = bytearray()
            response_headers: Dict[str, str] = {}
            response_status = 200
            aborted = False

            try:
                async with httpx.AsyncClient() as client:
                    request_kwargs: Dict[str, Any] = {
                        "headers": headers,
                        "cookies": cookie_dict,
                        "timeout": 90.0,
                    }
                    if request_body is not None:
                        request_kwargs["content"] = request_body

                    async with client.stream(request.method, request.url, **request_kwargs) as response:
                        response_status = int(response.status_code)
                        for k, v in response.headers.items():
                            response_headers[k] = v

                        async for chunk in response.aiter_bytes():
                            if self.abort_requested or (abort_event and abort_event.is_set()):
                                Logger.debug("Abort detected during Moonshot streaming, stopping...")
                                aborted = True
                                break

                            full_response_body.extend(chunk)
                            await self._process_connect_chunk(
                                chunk,
                                response_queue,
                                anti_censorship=bool(
                                    self.config_manager.get_setting("moonshot_behavior", "anti_censorship")
                                ),
                                send_deepthink=bool(effective_send_deepthink),
                            )
            except httpx.ReadError as e:
                if not aborted and not self.abort_requested:
                    Logger.error(f"Read error during Moonshot intercepted request: {e}")
                    await response_queue.put({"error": str(e)})
            except Exception as e:
                if not aborted and not self.abort_requested:
                    Logger.error(f"Error during Moonshot intercepted request: {e}")
                    await response_queue.put({"error": str(e)})

            if aborted or self.abort_requested:
                Logger.warning("Moonshot / Kimi generation aborted by user.")
                await self._click_stop_button()

            try:
                await route.fulfill(body=bytes(full_response_body), status=response_status, headers=response_headers)
            except Exception as e:
                Logger.error(f"Moonshot / Kimi: error fulfilling route: {e}")

            await response_queue.put(None)
            if not aborted and not self.abort_requested:
                Logger.success("Moonshot / Kimi response streaming completed.")

        await self.page.route(self.CHAT_ROUTE_GLOB, handle_route)
        await self.page.route(self.REGEN_ROUTE_GLOB, handle_route)

        try:
            formatted_message = self._format_messages(message_for_formatting)
            # Kimi's composer controls are flaky while the sidebar is open.
            await self.set_sidebar_status(open=False)

            clean_regeneration = bool(self.config_manager.get_setting("moonshot_behavior", "clean_regeneration"))
            regenerated = False

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
                    Logger.info("Clean Regeneration (Moonshot): Message and settings match cache. Attempting to regenerate...")
                    if await self._click_regenerate():
                        Logger.info("Clean Regeneration (Moonshot): Button clicked. Regenerating...")
                        regenerated = True
                        self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                        self._write_clean_regeneration_state(clean_regen_state)
                    else:
                        Logger.warning("Clean Regeneration (Moonshot): Button not found. Falling back to new chat.")

            if not regenerated:
                Logger.info("Moonshot / Kimi: preparing new chat session...")
                await self._click_new_chat()
                await asyncio.sleep(0.4)
                await self.set_sidebar_status(open=False)

                await self.set_deepthink_state(effective_deepthink)
                await self.set_search_state(enable_search)
                await asyncio.sleep(0.2)

                if send_as_text_file:
                    Logger.info("Moonshot / Kimi: sending message as text file...")
                    file_payload = {
                        "name": "prompt.txt",
                        "mimeType": "text/plain",
                        "buffer": formatted_message.encode("utf-8"),
                    }
                    await self._upload_file(file_payload)
                    await self._enter_message(".")
                    upload_timeout = int(self.config_manager.get_setting("moonshot_behavior", "file_upload_timeout") or 15)
                    Logger.info("Moonshot / Kimi: sending request...")
                    await self._send_message(timeout=upload_timeout)
                else:
                    await self._enter_message(formatted_message)
                    Logger.info("Moonshot / Kimi: sending request...")
                    await self._send_message()

                if clean_regeneration:
                    clean_regen_state = {
                        "deepthink_enabled": bool(effective_deepthink),
                        "search_enabled": bool(enable_search),
                        "send_as_text_file": bool(send_as_text_file),
                    }
                    self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                    self._write_clean_regeneration_state(clean_regen_state)

            received_stream_item = False
            while True:
                if self.abort_requested or (abort_event and abort_event.is_set()):
                    Logger.debug("Abort detected in Moonshot response loop, breaking...")
                    break

                wait_timeout_s = (
                    self.INTERCEPT_IDLE_TIMEOUT_S
                    if received_stream_item
                    else self.INTERCEPT_FIRST_CHUNK_TIMEOUT_S
                )
                try:
                    item = await asyncio.wait_for(response_queue.get(), timeout=wait_timeout_s)
                except asyncio.TimeoutError:
                    wait_phase = "intercepted first chunk" if not received_stream_item else "next stream chunk"
                    Logger.error(
                        f"Moonshot / Kimi: timed out waiting for {wait_phase} "
                        f"({wait_timeout_s:.0f}s)."
                    )
                    self.abort_requested = True
                    await self._click_stop_button()
                    timeout_err = {
                        "error": (
                            f"Moonshot / Kimi timeout: no {wait_phase} within "
                            f"{wait_timeout_s:.0f}s."
                        )
                    }
                    yield f"data: {json.dumps(timeout_err)}\n\n"
                    break

                if item is None:
                    break
                if isinstance(item, dict) and "error" in item:
                    yield f"data: {json.dumps(item)}\n\n"
                    break

                received_stream_item = True
                yield item

        finally:
            self.current_abort_event = None
            self.abort_requested = False
            self.current_model = None
            self.current_send_deepthink = None
            self.thinking_active = False
            self._connect_buffer = bytearray()
            try:
                await self.page.unroute(self.CHAT_ROUTE_GLOB)
            except Exception:
                pass
            try:
                await self.page.unroute(self.REGEN_ROUTE_GLOB)
            except Exception:
                pass

    async def abort_generation(self):
        Logger.info("Moonshot / Kimi: abort generation requested...")
        self.abort_requested = True
        if self.current_abort_event:
            self.current_abort_event.set()
        await self._click_stop_button()

    async def _click_stop_button(self):
        try:
            send_button = self.page.locator("div.send-button-container")
            if await send_button.count() == 0:
                return False
            if await send_button.first.is_visible():
                await send_button.first.click(timeout=2000)
                return True
            return False
        except Exception as e:
            Logger.debug(f"Moonshot / Kimi: stop button click failed: {e}")
            return False

    def _iter_connect_payloads(self, chunk: bytes) -> List[bytes]:
        payloads: List[bytes] = []
        if not chunk:
            return payloads

        self._connect_buffer.extend(chunk)

        while True:
            # Kimi Connect envelope appears to be:
            #   1 byte flags/type + 4 bytes big-endian payload length + payload bytes
            if len(self._connect_buffer) < 5:
                break

            frame_len = int.from_bytes(self._connect_buffer[1:5], byteorder="big", signed=False)
            if frame_len == 0:
                del self._connect_buffer[:5]
                continue

            if frame_len > self.CONNECT_MAX_FRAME_BYTES:
                # Best-effort re-sync when frame boundaries are misaligned
                del self._connect_buffer[:1]
                continue

            total_size = 5 + frame_len
            if len(self._connect_buffer) < total_size:
                break

            payload = bytes(self._connect_buffer[5:total_size])
            del self._connect_buffer[:total_size]
            payloads.append(payload)

        return payloads

    @staticmethod
    def _decode_connect_payload(payload: bytes) -> Optional[Dict[str, Any]]:
        if not payload:
            return None

        text = payload.decode("utf-8", errors="ignore").strip()
        if not text:
            return None

        if (not text.startswith("{")) or (not text.endswith("}")):
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end <= start:
                return None
            text = text[start : end + 1]

        try:
            data = json.loads(text)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None
        return data

    @staticmethod
    def _read_block_content(block: Dict[str, Any], key: str) -> str:
        sub = block.get(key)
        if not isinstance(sub, dict):
            return ""
        content = sub.get("content")
        if isinstance(content, str):
            return content
        return ""

    async def _process_connect_chunk(
        self,
        chunk: bytes,
        queue: asyncio.Queue,
        *,
        anti_censorship: bool,
        send_deepthink: bool,
    ) -> None:
        for payload in self._iter_connect_payloads(chunk):
            data = self._decode_connect_payload(payload)
            if not data:
                continue

            content_parts: List[str] = []
            finish_reason: Optional[str] = None

            notification = data.get("notification")
            if isinstance(notification, dict):
                note_type = str(notification.get("type") or "")
                note_msg = str(notification.get("message") or "")

                if note_type == "TYPE_MODEL_DEGRADE" and note_msg and (not self._degrade_notice_logged):
                    self._degrade_notice_logged = True
                    Logger.warning(f"Moonshot / Kimi model degrade notice: {note_msg}")

                if anti_censorship:
                    lowered_type = note_type.strip().lower()
                    lowered_msg = note_msg.strip().lower()
                    is_filter_like = (
                        ("content" in lowered_type and "filter" in lowered_type)
                        or ("beyond my current scope" in lowered_msg)
                    )
                    if is_filter_like:
                        if self.thinking_active:
                            if send_deepthink:
                                content_parts.append("</think>")
                            self.thinking_active = False
                        finish_reason = "stop"

            op = str(data.get("op") or "")
            mask = str(data.get("mask") or "")
            block = data.get("block")
            message = data.get("message")

            if not isinstance(block, dict):
                block = {}
            if not isinstance(message, dict):
                message = {}

            if mask in {"block.think", "block.think.content"}:
                think_text = self._read_block_content(block, "think")
                if not self.thinking_active:
                    if send_deepthink:
                        content_parts.append("<think>")
                    self.thinking_active = True
                if think_text and send_deepthink:
                    content_parts.append(think_text)

            elif mask in {"block.text", "block.text.content"}:
                text_piece = self._read_block_content(block, "text")
                if self.thinking_active:
                    if send_deepthink:
                        content_parts.append("</think>")
                    self.thinking_active = False
                if text_piece:
                    content_parts.append(text_piece)

            elif mask == "message.status":
                status = str(message.get("status") or "")
                if status == "MESSAGE_STATUS_COMPLETED":
                    if self.thinking_active:
                        if send_deepthink:
                            content_parts.append("</think>")
                        self.thinking_active = False
                    finish_reason = "stop"

            if "done" in data:
                if self.thinking_active:
                    if send_deepthink:
                        content_parts.append("</think>")
                    self.thinking_active = False
                finish_reason = "stop"

            if op == "append" and (mask in {"block.think.content", "block.text.content"}):
                pass

            content = "".join(content_parts)
            if content or finish_reason:
                model_name = self.current_model or "moonshot-auto"
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
                await queue.put(f"data: {json.dumps(openai_chunk)}\n\n")

    async def _read_current_model_name(self) -> str:
        selectors = [
            "div.current-model span.name",
            "div.current-model div.model-name span.name",
            "div.current-model .name",
        ]

        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                if await locator.count() == 0:
                    continue
                text = (await locator.first.inner_text() or "").strip()
                if text:
                    return text
            except Exception:
                continue

        return ""

    async def _select_kimi_model(self, target_model: str) -> bool:
        trigger = await self._find_first_visible(["div.current-model"], timeout_ms=8000)
        if trigger is None:
            Logger.warning("Moonshot / Kimi: model selector trigger not found.")
            return False

        try:
            await trigger.click()
            await self.page.wait_for_selector("div.models-container", timeout=5000, state="visible")
            await self.page.wait_for_selector("div.models-container div.model-item", timeout=5000, state="attached")
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: model picker did not open: {e}")
            return False

        target_norm = self._normalize_text(target_model)
        items = self.page.locator("div.models-container div.model-item")
        count = await items.count()
        if count == 0:
            Logger.warning("Moonshot / Kimi: no model items found in picker.")
            return False

        for idx in range(min(count, 30)):
            item = items.nth(idx)
            name_locator = item.locator("div.model-item-content div.header div.model-name span.name")
            if await name_locator.count() == 0:
                name_locator = item.locator("span.name")
            if await name_locator.count() == 0:
                continue

            name_text = (await name_locator.first.inner_text() or "").strip()
            if self._normalize_text(name_text) != target_norm:
                continue

            try:
                await item.click()
            except Exception as e:
                Logger.warning(f"Moonshot / Kimi: failed to click model '{target_model}': {e}")
                return False

            deadline = time.time() + 5.0
            while time.time() < deadline:
                current = await self._read_current_model_name()
                if self._normalize_text(current) == target_norm:
                    return True
                await asyncio.sleep(0.1)

            current_after = await self._read_current_model_name()
            Logger.warning(
                "Moonshot / Kimi: model selection click finished but "
                f"did not confirm '{target_model}' (current: '{current_after or '<unknown>'}')."
            )
            return False

        Logger.warning(f"Moonshot / Kimi: target model '{target_model}' not found in picker.")
        return False

    async def set_deepthink_state(self, state: bool):
        current = await self._read_current_model_name()
        current_norm = self._normalize_text(current)
        instant_norm = self._normalize_text(self.MODEL_INSTANT)
        thinking_norm = self._normalize_text(self.MODEL_THINKING)

        target_model = self.MODEL_THINKING if state else self.MODEL_INSTANT
        target_norm = self._normalize_text(target_model)

        if current_norm == target_norm:
            return

        if (current_norm not in {instant_norm, thinking_norm}) and (not state):
            target_model = self.MODEL_INSTANT

        switched = await self._select_kimi_model(target_model)
        if not switched:
            Logger.warning(
                f"Moonshot / Kimi: failed to set Thinking mode target model '{target_model}'."
            )

    async def _is_search_enabled(self) -> bool:
        indicator = self.page.locator(
            "div.chat-editor div.tool-switch.open.showClose",
            has_text="Internet off",
        )
        try:
            count = await indicator.count()
            if count == 0:
                return True
            for idx in range(min(count, 3)):
                item = indicator.nth(idx)
                if await item.is_visible():
                    return False
        except Exception:
            return True
        return True

    async def _wait_for_connect_menu_open(self, timeout_ms: int = 1200) -> bool:
        if not self.page:
            return False

        try:
            await self.page.wait_for_selector("div.connect-container", timeout=int(timeout_ms), state="visible")
        except Exception:
            return False

        connect_items = self.page.locator("div.connect-container div.connect-item")
        return await self._wait_for_locator_count(connect_items, minimum_count=2, timeout_ms=max(500, int(timeout_ms)))

    async def _dispatch_connect_trigger_events(self, tool_item) -> None:
        try:
            await tool_item.evaluate(
                """(el) => {
                    if (!el) return;
                    const rect = el.getBoundingClientRect();
                    const cx = rect.left + rect.width / 2;
                    const cy = rect.top + rect.height / 2;

                    const mouseEvents = ['mousemove', 'mouseover', 'mouseenter'];
                    for (const type of mouseEvents) {
                        try {
                            el.dispatchEvent(new MouseEvent(type, {
                                bubbles: true,
                                cancelable: true,
                                clientX: cx,
                                clientY: cy,
                                view: window
                            }));
                        } catch (_) {}
                    }

                    const pointerEvents = ['pointerover', 'pointerenter', 'pointermove'];
                    for (const type of pointerEvents) {
                        try {
                            el.dispatchEvent(new PointerEvent(type, {
                                bubbles: true,
                                cancelable: true,
                                pointerType: 'mouse',
                                clientX: cx,
                                clientY: cy
                            }));
                        } catch (_) {}
                    }

                    try { el.focus(); } catch (_) {}
                }"""
            )
        except Exception:
            pass

    async def _open_search_connect_menu(self, tool_item) -> bool:
        if not self.page:
            return False

        if await self._wait_for_connect_menu_open(timeout_ms=400):
            return True

        try:
            await tool_item.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            await tool_item.hover()
        except Exception:
            pass
        if await self._wait_for_connect_menu_open(timeout_ms=1200):
            return True

        try:
            box = await tool_item.bounding_box()
            if box:
                cx = box["x"] + (box["width"] / 2.0)
                cy = box["y"] + (box["height"] / 2.0)
                await self.page.mouse.move(cx, cy)
                await asyncio.sleep(0.08)
                await self.page.mouse.move(cx + 1, cy + 1)
        except Exception:
            pass
        if await self._wait_for_connect_menu_open(timeout_ms=1000):
            return True

        await self._dispatch_connect_trigger_events(tool_item)
        if await self._wait_for_connect_menu_open(timeout_ms=1000):
            return True

        # Sometimes this submenu opens on click rather than hover
        try:
            await tool_item.click(timeout=1500)
        except Exception:
            pass
        if await self._wait_for_connect_menu_open(timeout_ms=1000):
            return True

        try:
            await tool_item.click(timeout=1500, force=True)
        except Exception:
            pass
        return await self._wait_for_connect_menu_open(timeout_ms=1000)

    async def _set_search_state_via_toolkit(self, state: bool) -> bool:
        toolkit_button = await self._find_first_visible(["div.toolkit-trigger-btn"], timeout_ms=8000)
        if toolkit_button is None:
            Logger.warning("Moonshot / Kimi: toolkit trigger button not found.")
            return False

        try:
            await toolkit_button.click()
            await self.page.wait_for_selector("div.toolkit-container", timeout=3000, state="visible")
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: toolkit menu did not open: {e}")
            return False

        parent_tool = await self._find_nth_visible(
            [
                # Preferred selector: toolkit entries (first can be <label>, next are usually <div>)
                "div.toolkit-container > .toolkit-item",
                "div.toolkit-container .toolkit-item",
                # Fallback in case class names change
                "div.toolkit-container > *",
            ],
            visible_index=2,
            timeout_ms=3000,
        )
        if parent_tool is None:
            Logger.warning("Moonshot / Kimi: search toolkit entry not found.")
            return False

        opened = await self._open_search_connect_menu(parent_tool)
        if not opened:
            Logger.warning("Moonshot / Kimi: search submenu did not appear after hover/click/event fallbacks.")
            return False

        connect_items = self.page.locator("div.connect-container div.connect-item")
        has_connect_items = await self._wait_for_locator_count(connect_items, minimum_count=2, timeout_ms=3000)
        if not has_connect_items:
            Logger.warning("Moonshot / Kimi: search submenu items not found.")
            return False

        target_index = 0 if state else 1
        try:
            await connect_items.nth(target_index).click()
            return True
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: failed to click search state option: {e}")
            return False

    async def set_search_state(self, state: bool):
        current = await self._is_search_enabled()
        if current == state:
            return

        if state:
            quick_enable = self.page.locator(
                "div.chat-editor div.tool-switch.open.showClose",
                has_text="Internet off",
            )
            if await quick_enable.count() > 0:
                try:
                    await quick_enable.first.click()
                    await asyncio.sleep(0.15)
                    if await self._is_search_enabled():
                        return
                except Exception:
                    pass

        ok = await self._set_search_state_via_toolkit(state)
        if not ok:
            Logger.warning(f"Moonshot / Kimi: could not set Search to {state}.")
            return

        await asyncio.sleep(0.2)
        after = await self._is_search_enabled()
        if after != state:
            Logger.warning(f"Moonshot / Kimi: Search state mismatch after toggle (wanted={state}, actual={after}).")

    async def _is_sidebar_open(self) -> Optional[bool]:
        if not self.page:
            return None

        app = self.page.locator("div.app.has-sidebar")
        app_count = await app.count()
        if app_count > 0:
            for idx in range(min(app_count, 5)):
                candidate = app.nth(idx)
                try:
                    if not await candidate.is_visible():
                        continue
                except Exception:
                    continue

                class_attr = await candidate.get_attribute("class") or ""
                classes = set(class_attr.split())
                return "fold" in classes

            # Fallback to first match even if visibility probing fails
            class_attr = await app.first.get_attribute("class") or ""
            classes = set(class_attr.split())
            return "fold" in classes

        # Fallback heuristics
        close_button = self.page.locator("div.sidebar-header div.expand-btn:not(.icon-button)")
        close_count = await close_button.count()
        for idx in range(min(close_count, 5)):
            try:
                if await close_button.nth(idx).is_visible():
                    return True
            except Exception:
                continue

        open_button = self.page.locator("div.icon-button.expand-btn")
        open_count = await open_button.count()
        for idx in range(min(open_count, 5)):
            try:
                if await open_button.nth(idx).is_visible():
                    return False
            except Exception:
                continue

        return None

    async def _wait_for_locator_count(
        self,
        locator,
        minimum_count: int = 1,
        timeout_ms: int = 8000,
        poll_interval_s: float = 0.1,
    ) -> bool:
        deadline = time.time() + max(0.0, float(timeout_ms) / 1000.0)
        while True:
            try:
                count = await locator.count()
            except Exception:
                count = 0
            if count >= int(minimum_count):
                return True
            if time.time() >= deadline:
                return False
            await asyncio.sleep(max(0.05, float(poll_interval_s)))

    async def _wait_for_first_attached(
        self,
        selectors: List[str],
        timeout_ms: int = 8000,
        poll_interval_s: float = 0.15,
    ):
        if not self.page:
            return None

        deadline = time.time() + max(0.0, float(timeout_ms) / 1000.0)
        while True:
            for selector in selectors:
                locator = self.page.locator(selector)
                try:
                    count = await locator.count()
                except Exception:
                    count = 0
                if count > 0:
                    return locator.first

            if time.time() >= deadline:
                return None
            await asyncio.sleep(max(0.05, float(poll_interval_s)))

    async def _find_first_visible(
        self,
        selectors: List[str],
        timeout_ms: int = 0,
        poll_interval_s: float = 0.15,
    ):
        if not self.page:
            return None

        deadline = time.time() + max(0.0, float(timeout_ms) / 1000.0)
        while True:
            for selector in selectors:
                locator = self.page.locator(selector)
                try:
                    count = await locator.count()
                except Exception:
                    count = 0
                for idx in range(min(count, 10)):
                    item = locator.nth(idx)
                    try:
                        if await item.is_visible():
                            return item
                    except Exception:
                        continue

            if timeout_ms <= 0 or time.time() >= deadline:
                return None

            await asyncio.sleep(max(0.05, float(poll_interval_s)))

    async def _find_nth_visible(
        self,
        selectors: List[str],
        visible_index: int,
        timeout_ms: int = 0,
        poll_interval_s: float = 0.15,
    ):
        if not self.page:
            return None

        target = max(0, int(visible_index))
        deadline = time.time() + max(0.0, float(timeout_ms) / 1000.0)

        while True:
            for selector in selectors:
                locator = self.page.locator(selector)
                try:
                    count = await locator.count()
                except Exception:
                    count = 0

                visible_seen = 0
                for idx in range(min(count, 40)):
                    item = locator.nth(idx)
                    try:
                        if not await item.is_visible():
                            continue
                    except Exception:
                        continue

                    if visible_seen == target:
                        return item
                    visible_seen += 1

            if timeout_ms <= 0 or time.time() >= deadline:
                return None

            await asyncio.sleep(max(0.05, float(poll_interval_s)))

    async def set_sidebar_status(self, open: bool):
        if not self.page:
            return

        target_open = bool(open)

        for _ in range(3):
            is_open = await self._is_sidebar_open()
            if is_open == target_open:
                return

            if target_open:
                button = await self._find_first_visible(
                    [
                        "aside.sidebar div.sidebar-header div.icon-button.expand-btn",
                        "div.icon-button.expand-btn",
                    ],
                    timeout_ms=1500,
                )
                if button is None:
                    Logger.warning("Moonshot / Kimi: open sidebar button not found.")
                    return
            else:
                button = await self._find_first_visible(
                    [
                        "aside.sidebar div.sidebar-header div.expand-btn:not(.icon-button)",
                        "div.sidebar-header div.expand-btn:not(.icon-button)",
                    ],
                    timeout_ms=1500,
                )
                if button is None:
                    # Fallback: Escape often closes slide panels in Kimi
                    try:
                        await self.page.keyboard.press("Escape")
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)
                    continue

            try:
                await button.click(timeout=2000)
            except Exception as e:
                action = "open" if target_open else "close"
                Logger.warning(f"Moonshot / Kimi: failed to {action} sidebar: {e}")
                return

            deadline = time.time() + 2.0
            while time.time() < deadline:
                state_now = await self._is_sidebar_open()
                if state_now == target_open:
                    return
                await asyncio.sleep(0.1)

        final_state = await self._is_sidebar_open()
        if final_state != target_open:
            Logger.warning(
                f"Moonshot / Kimi: sidebar state mismatch after toggle "
                f"(wanted_open={target_open}, is_open={final_state})."
            )

    async def click_new_chat(self, source: str = "auto"):
        _ = source
        await self.set_sidebar_status(open=True)
        new_chat_button = await self._find_first_visible(
            [
                "aside.sidebar div.sidebar-nav button.new-chat-btn",
                "div.sidebar-nav .new-chat-btn",
            ],
            timeout_ms=8000,
        )
        if new_chat_button is None:
            Logger.warning("Moonshot / Kimi: New Chat button not found.")
            await self.set_sidebar_status(open=False)
            return

        try:
            await new_chat_button.click(timeout=2000)
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: failed to click New Chat: {e}")
        finally:
            await asyncio.sleep(0.1)
            await self.set_sidebar_status(open=False)

    async def enter_message(self, message: str):
        await self._enter_message(message)

    async def send_message(self, timeout: int = None):
        await self._send_message(timeout=timeout)

    async def _enter_message(self, message: str):
        await self.set_sidebar_status(open=False)

        editor = await self._find_first_visible(
            [
                "div.chat-input-editor[contenteditable='true']",
                "div.chat-input-editor[contenteditable]",
            ],
            timeout_ms=10000,
        )
        if editor is None:
            Logger.warning("Moonshot / Kimi: message editor not found.")
            return

        try:
            await editor.click()
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            if message:
                pasted = False
                try:
                    await self.page.keyboard.insert_text(message)
                    pasted = True
                except Exception:
                    pasted = False

                if not pasted:
                    try:
                        await editor.fill(message)
                        pasted = True
                    except Exception:
                        pasted = False

                if not pasted:
                    await editor.type(message, delay=0)
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: failed to enter message: {e}")

    async def _send_message(self, timeout: int = None):
        send_button = await self._find_first_visible(["div.send-button-container"], timeout_ms=10000)
        if send_button is None:
            Logger.warning("Moonshot / Kimi: send button not found.")
            return

        if timeout and timeout > 0:
            deadline = time.time() + float(timeout)
            while time.time() < deadline:
                class_attr = await send_button.get_attribute("class") or ""
                if "disabled" not in class_attr.split():
                    break
                await asyncio.sleep(0.2)

        class_attr = await send_button.get_attribute("class") or ""
        if "disabled" in class_attr.split():
            Logger.warning("Moonshot / Kimi: send button is disabled. Cannot send message.")
            return

        try:
            await send_button.click()
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: failed to click send button: {e}")

    async def _click_new_chat(self):
        await self.click_new_chat(source="auto")

    async def _click_regenerate(self) -> bool:
        actions = self.page.locator("div.segment-assistant-actions-content")
        has_actions = await self._wait_for_locator_count(actions, minimum_count=1, timeout_ms=8000)
        if not has_actions:
            Logger.warning("Moonshot / Kimi: regenerate action container not found.")
            return False
        count = await actions.count()

        async def _click_if_enabled(candidate) -> bool:
            try:
                if not await candidate.is_visible():
                    return False
            except Exception:
                return False

            try:
                class_attr = await candidate.get_attribute("class") or ""
            except Exception:
                class_attr = ""
            try:
                aria_disabled = (await candidate.get_attribute("aria-disabled") or "").strip().lower()
            except Exception:
                aria_disabled = ""

            if ("disabled" in class_attr.split()) or (aria_disabled == "true"):
                return False

            try:
                await candidate.click()
                return True
            except Exception:
                return False

        target_bar = None
        for bar_idx in range(count - 1, -1, -1):
            bar = actions.nth(bar_idx)
            try:
                if not await bar.is_visible():
                    continue
            except Exception:
                continue
            target_bar = bar
            break

        if target_bar is None:
            Logger.warning("Moonshot / Kimi: no visible regenerate action bar found.")
            return False

        # This is desperate. Sometimes the actions belt only shows up after a hover, perhaps due to a bug or something
        try:
            await target_bar.scroll_into_view_if_needed()
        except Exception:
            pass
        try:
            await target_bar.hover()
            await asyncio.sleep(0.05)
        except Exception:
            pass

        # regenerate is the Refresh icon
        refresh_btn = target_bar.locator(":scope > div.icon-button:has(svg[name='Refresh'])")
        refresh_count = await refresh_btn.count()
        if refresh_count == 0:
            Logger.warning("Moonshot / Kimi: strict regenerate target (Refresh icon) not found.")
            return False

        for idx in range(min(refresh_count, 3)):
            if await _click_if_enabled(refresh_btn.nth(idx)):
                return True

        Logger.warning("Moonshot / Kimi: strict regenerate target found but unavailable.")
        return False

    async def upload_file(self, file_spec: Any) -> None:
        await self._upload_file(file_spec)

    async def _upload_file(self, file_spec: Any):
        toolkit_button = await self._find_first_visible(["div.toolkit-trigger-btn"], timeout_ms=5000)
        if toolkit_button is not None:
            try:
                await toolkit_button.click()
            except Exception:
                pass

        file_input = await self._wait_for_first_attached(
            [
                "input.hidden-input[type='file']",
                "input[type='file'].hidden-input",
                "input[type='file']",
            ],
            timeout_ms=8000,
        )
        if file_input is None:
            Logger.warning("Moonshot / Kimi: file input not found.")
            return

        try:
            await file_input.set_input_files(file_spec)
            await asyncio.sleep(0.8)
        except Exception as e:
            Logger.warning(f"Moonshot / Kimi: file upload failed: {e}")
