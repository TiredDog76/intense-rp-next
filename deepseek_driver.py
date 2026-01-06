import os
import sys
import time
import json
import asyncio
import re
import httpx
import subprocess
from pathlib import Path
from typing import List, Union, Any, Dict, Callable, Optional
from patchright.async_api import async_playwright, Page, Browser, BrowserContext
from dotenv import load_dotenv
from utils.cache_manager import CacheManager
from utils.logger import Logger

load_dotenv()

class DeepSeekDriver:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.page: Page = None
        self.is_running = False
        self.cache_manager = CacheManager()
        self.on_crash_callback = None
        self.monitoring_active = False
        self._monitor_task: Optional[asyncio.Task] = None

        # DeepSeek UI language detection (some selectors rely on English UI text)
        self.last_document_lang: Optional[str] = None
        self.ui_language_ok: Optional[bool] = None
        self._non_english_ui_warned = False
        self._non_english_ui_warned_lang: Optional[str] = None
        
        # Abort handling
        self.current_abort_event: asyncio.Event = None
        self.abort_requested = False
        self.current_model = None
        self.current_send_deepthink = None
        self.clean_regen_message_cache_key = "last_message.txt"
        self.clean_regen_state_cache_key = "last_message_state.json"

    def _get_persistent_profile_dir(self) -> str:
        config_dir = getattr(self.config_manager, "config_dir", None)
        base_dir = Path(config_dir) if config_dir is not None else Path("config_data")
        return str((base_dir / "playwright_profiles" / "deepseek").resolve())

    async def ensure_browser_installed(self, status_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Ensures the patchright chromium browser is installed.
        Returns True if installation was performed/verified, False if failed.
        """
        # Directly run the install/verify command to avoid issues where the dry-run check returns false negatives.
        return await self._install_browser_via_cli(status_callback)

    async def _install_browser_via_cli(self, status_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Run the browser installation using the patchright CLI (async).
        """
        Logger.info("Verifying/Installing Chromium browser...")
        if status_callback:
            status_callback("Verifying Browser...")
        
        try:
            # Use sys.executable to run the patchright module (async)
            # This runs 'patchright install chromium' which downloads if missing, or validates if present.
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "patchright", "install", "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            
            if process.returncode == 0:
                Logger.success("Chromium browser verified/installed.")
                return True
            else:
                error_msg = (stderr.decode() if stderr else "") or (stdout.decode() if stdout else "") or "Unknown error"
                Logger.error(f"Failed to install Chromium browser: {error_msg}")
                raise RuntimeError(f"Failed to install Chromium browser: {error_msg}")
                
        except asyncio.TimeoutError:
            Logger.error("Browser installation timed out.")
            raise RuntimeError("Browser installation timed out after 5 minutes.")
        except Exception as e:
            Logger.error(f"Browser installation failed: {e}")
            raise RuntimeError(f"Browser installation failed: {e}")

    async def start(self, status_callback: Optional[Callable[[str], None]] = None):
        """
        Starts the browser and navigates to DeepSeek.
        
        Args:
            status_callback: Optional callback to report status updates (e.g., for UI updates)
        """
        Logger.info("Starting DeepSeek Driver...")
        
        # Ensure browser is installed before starting
        await self.ensure_browser_installed(status_callback)
        
        if status_callback:
            status_callback("Launching Browser...")
        
        self.playwright = await async_playwright().start()
        persistent_sessions = bool(self.config_manager.get_setting("system_settings", "persistent_sessions"))

        if persistent_sessions:
            user_data_dir = self._get_persistent_profile_dir()
            Logger.info("Launching Chromium (Persistent Sessions enabled)...")
            Logger.debug(f"Persistent profile dir: {user_data_dir}")

            try:
                os.makedirs(user_data_dir, exist_ok=True)
                self.context = await self.playwright.chromium.launch_persistent_context(user_data_dir, headless=False)
                context_browser = getattr(self.context, "browser", None)
                self.browser = context_browser() if callable(context_browser) else context_browser
            except Exception as e:
                Logger.error(f"Failed to launch persistent context: {e}")
                Logger.warning("Falling back to non-persistent session...")
                self.browser = await self.playwright.chromium.launch(headless=False)
                self.context = await self.browser.new_context()
        else:
            # Launch Chromium
            # headless=False to see the browser
            Logger.info("Launching Chromium...")
            self.browser = await self.playwright.chromium.launch(headless=False)
            self.context = await self.browser.new_context()

        # Create or reuse a page
        try:
            pages = getattr(self.context, "pages", [])
            self.page = pages[0] if pages else await self.context.new_page()
        except Exception:
            self.page = await self.context.new_page()
        
        Logger.info("Navigating to https://chat.deepseek.com/ ...")
        await self.page.goto("https://chat.deepseek.com/")
        
        # Handle Login
        await self.login()

        # Detect DeepSeek UI language early (warn only; hard-requirement is enforced per-request)
        await self.check_ui_language(status_callback=status_callback)
        
        self.is_running = True
        
        # Invalidate cache on start
        self.cache_manager.clear_cache(self.clean_regen_message_cache_key)
        self.cache_manager.clear_cache(self.clean_regen_state_cache_key)
        
        Logger.success("DeepSeek Driver started successfully.")
        
        # Start monitoring loop
        self.monitoring_active = True
        self._monitor_task = asyncio.create_task(self._monitor_browser_loop())

    async def login(self):
        """
        Handles the login process if redirected to the sign-in page.
        """
        # DeepSeek changes the auth flow/UI fairly often.
        url_lower = (self.page.url or "").lower()
        is_sign_in_page = any(token in url_lower for token in ("sign_in", "signin", "sign-in"))

        # Check if we were redirected to sign in
        if is_sign_in_page:
            Logger.info("Redirected to sign in page.")
            
            auto_login = self.config_manager.get_setting("providers_credentials", "auto_login")
            
            if auto_login:
                Logger.info("Auto-login enabled. Attempting to log in...")
                
                # Get credentials from settings
                email = self.config_manager.get_setting("providers_credentials", "deepseek_email")
                password = self.config_manager.get_setting("providers_credentials", "deepseek_password")
                
                if not email or not password:
                    Logger.error("DeepSeek email or password not found in settings.")
                    return
                else:
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
            Logger.info("Not redirected to sign in. Continuing...")

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

    async def close(self):
        """
        Closes the browser and playwright.
        """
        Logger.info("Closing DeepSeek Driver...")
        self.monitoring_active = False
        monitor_task = getattr(self, "_monitor_task", None)
        if monitor_task and (not monitor_task.done()):
            try:
                monitor_task.cancel()
                await monitor_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                Logger.debug(f"Error stopping monitor task: {e}")
        self._monitor_task = None

        async def _await_with_timeout(coro, timeout_s: float, label: str) -> None:
            try:
                await asyncio.wait_for(coro, timeout=timeout_s)
            except asyncio.TimeoutError:
                Logger.warning(f"Timeout while {label}.")
            except Exception as e:
                Logger.debug(f"Error while {label}: {e}")

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
        self.is_running = False
        Logger.info("DeepSeek Driver closed.")

    def _resolve_deepthink_flags(self, model: str) -> tuple[bool, bool]:
        enable_deepthink = bool(self.config_manager.get_setting("deepseek_behavior", "enable_deepthink"))
        send_deepthink = bool(self.config_manager.get_setting("deepseek_behavior", "send_deepthink"))
        normalized = (model or "").strip().lower()

        if normalized == "deepseek-chat":
            return False, False
        if normalized == "deepseek-reasoner":
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

    def _extract_deepseek_macros_from_text(self, text: str) -> tuple[str, Dict[str, bool]]:
        if not text:
            return text, {}

        macro_actions: Dict[str, tuple[str, bool]] = {
            # DeepThink
            "think": ("deepthink_enabled", True),
            "r1": ("deepthink_enabled", True),
            "nothink": ("deepthink_enabled", False),
            "no_think": ("deepthink_enabled", False),
            "r0": ("deepthink_enabled", False),

            # Search
            "search": ("search_enabled", True),
            "nosearch": ("search_enabled", False),
            "no_search": ("search_enabled", False),

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

    def _strip_deepseek_macros_from_messages(self, messages: List[Any]) -> tuple[List[Any], Dict[str, bool]]:
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

        cleaned_content, overrides = self._extract_deepseek_macros_from_text(content)
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
            Logger.warning("Clean Regeneration: Cached state is invalid JSON, ignoring.")
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

    async def generate_response(self, message: Union[str, List[Any]], model: str = "deepseek-auto", stream: bool = False, temperature: float = None, top_p: float = None, abort_event: asyncio.Event = None):
        """
        Generates a response from DeepSeek.
        This function intercepts the network request to support streaming.
        """
        response_queue = asyncio.Queue()

        # Some selectors rely on English UI text; fail fast with a clear error instead of hanging.
        await self.require_english_ui()
        
        # Reset state for new generation
        self.fragment_types_list = []
        self.thinking_active = False
        self.abort_requested = False
        self.current_abort_event = abort_event
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
            request = route.request
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
            full_response_body = b""
            response_headers = {}
            aborted = False
            
            try:
                async with httpx.AsyncClient() as client:
                    try:
                        Logger.info("Streaming response from DeepSeek...")
                        async with client.stream("POST", request.url, headers=headers, cookies=cookie_dict, json=post_data, timeout=60.0) as response:
                            # Capture headers to forward them later
                            # We specifically need Content-Type so the frontend knows it's an SSE stream
                            for k, v in response.headers.items():
                                response_headers[k] = v
                            
                            async for chunk in response.aiter_bytes():
                                # Check if abort was requested
                                if self.abort_requested or (abort_event and abort_event.is_set()):
                                    Logger.debug("Abort detected during streaming, stopping...")
                                    aborted = True
                                    break
                                
                                full_response_body += chunk
                                # Process chunk for streaming
                                await self._process_chunk(chunk, response_queue)
                                
                    except httpx.ReadError as e:
                        if not aborted and not self.abort_requested:
                            Logger.error(f"Read error during intercepted request: {e}")
                            await response_queue.put({"error": str(e)})
                    except Exception as e:
                        if not aborted and not self.abort_requested:
                            Logger.error(f"Error during intercepted request: {e}")
                            await response_queue.put({"error": str(e)})
            except RuntimeError as e:
                # Ignore RuntimeError from async generator cleanup during abort
                if "async generator" in str(e) or "cancel scope" in str(e):
                    Logger.debug(f"Ignored expected error during abort: {e}")
                else:
                    raise
            
            # If aborted, click the stop button in DeepSeek UI
            if aborted or self.abort_requested:
                Logger.warning("Generation aborted by user.")
                Logger.debug("Request was aborted, clicking Stop button...")
                await self._click_stop_button()
            
            # Fulfill the original request so the UI updates
            try:
                # Forward the captured headers, especially Content-Type
                await route.fulfill(body=full_response_body, status=200, headers=response_headers)
            except Exception as e:
                Logger.error(f"Error fulfilling route: {e}")
            
            # Signal end of stream
            await response_queue.put(None)
            if not aborted and not self.abort_requested:
                Logger.success("Response streaming completed.")

        # Set up interception
        await self.page.route("**/api/v0/chat/completion", handle_route)
        await self.page.route("**/api/v0/chat/regenerate", handle_route)
        
        try:
            # Apply formatting
            formatted_message = self._format_messages(message_for_formatting)
            
            # Check for Clean Regeneration
            clean_regeneration = self.config_manager.get_setting("deepseek_behavior", "clean_regeneration")
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
                    Logger.info("Clean Regeneration: Message and settings match cache. Attempting to regenerate...")
                    if await self._click_regenerate():
                        Logger.info("Clean Regeneration: Button clicked. Regenerating...")
                        regenerated = True
                        self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                        self._write_clean_regeneration_state(clean_regen_state)
                    else:
                        Logger.warning("Clean Regeneration: Button not found or disabled. Falling back to new chat.")
                elif message_matches and not state_matches:
                    Logger.info("Clean Regeneration: Message matches cache but settings changed. Creating new chat.")
                else:
                    Logger.debug("Clean Regeneration: Message differs from cache. Creating new chat.")
            
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
                    await self._send_message(timeout=upload_timeout)
                else:
                    await self._enter_message(formatted_message)
                    Logger.info("Sending request to DeepSeek...")
                    await self._send_message()
                
                # Update cache
                if clean_regeneration:
                    clean_regen_state = {
                        "deepthink_enabled": bool(effective_deepthink),
                        "search_enabled": bool(enable_search),
                        "send_as_text_file": bool(send_as_text_file),
                    }
                    self.cache_manager.write_cache(self.clean_regen_message_cache_key, formatted_message)
                    self._write_clean_regeneration_state(clean_regen_state)
            
            # Yield responses from queue
            while True:
                # Check for abort before waiting for next item
                if self.abort_requested or (abort_event and abort_event.is_set()):
                    Logger.debug("Abort detected in response loop, breaking...")
                    break
                    
                item = await response_queue.get()
                if item is None:
                    break
                if isinstance(item, dict) and "error" in item:
                    yield f"data: {json.dumps(item)}\n\n"
                    break
                
                yield item
                
        finally:
            # Cleanup interception
            self.current_abort_event = None
            self.abort_requested = False
            self.current_model = None
            self.current_send_deepthink = None
            await self.page.unroute("**/api/v0/chat/completion")
            await self.page.unroute("**/api/v0/chat/regenerate")

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

    async def _click_stop_button(self):
        """
        Clicks the Stop button in DeepSeek UI to cancel the ongoing generation.
        The Stop button appears in place of the Send button during generation.
        """
        try:
            # The send button doesn't have a specific class when it's in "stop" mode
            # It's the same location as the send button but with different styling
            
            # First, try the specific stop button selector
            stop_button = self.page.locator("div.ds-icon-button._7436101")
            
            if await stop_button.count() > 0:
                # Check if the button is in "stop" mode (enabled and clickable)
                is_disabled = await stop_button.get_attribute("aria-disabled")
                if is_disabled != "true":
                    Logger.debug("Clicking Stop button...")
                    await stop_button.click()
                    Logger.debug("Stop button clicked successfully.")
                    return True
                else:
                    Logger.debug("Stop button is disabled (generation may have already stopped).")
            else:
                Logger.debug("Stop button not found.")
                
            return False
        except Exception as e:
            Logger.error(f"Error clicking stop button: {e}")
            return False

    async def _monitor_browser_loop(self):
        """
        Periodically checks if the browser is still open.
        """
        Logger.debug("Starting browser monitoring loop...")
        while self.monitoring_active:
            try:
                if not self.browser or not self.browser.is_connected():
                    Logger.warning("Browser disconnected!")
                    await self._handle_crash()
                    break
                
                if not self.page or self.page.is_closed():
                    Logger.warning("Page closed!")
                    await self._handle_crash()
                    break
                    
                # Also check if context is closed
                if not self.context or len(self.context.pages) == 0:
                     # Sometimes page.is_closed() isn't enough if the whole context is gone
                    Logger.warning("Context has no pages or is closed!")
                    await self._handle_crash()
                    break

            except Exception as e:
                Logger.debug(f"Error in monitoring loop: {e}")
                # If we can't check, assume it's gone or something is wrong
                pass
            
            await asyncio.sleep(2.0)
            
    async def _handle_crash(self):
        """
        Handles the crash event.
        """
        if not self.monitoring_active:
            return

        Logger.warning("Browser crash detected!")
        self.is_running = False
        self.monitoring_active = False
        
        if self.on_crash_callback:
            if asyncio.iscoroutinefunction(self.on_crash_callback):
                await self.on_crash_callback()
            else:
                self.on_crash_callback()

    def _format_messages(self, messages: Union[str, List[Any]]) -> str:
        """
        Applies formatting rules to the messages.
        """
        apply_formatting = self.config_manager.get_setting("formatting", "apply_formatting")
        
        # If formatting is disabled, we still need to convert list to string if it's a list
        if not apply_formatting:
            if isinstance(messages, list):
                # Mimic the previous behavior: role: content if custom formatting is off
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
            return _get_msg_field(msg, "irp-next") # For patcher compat
        
        # Try Message Objects
        if self.config_manager.get_setting("formatting", "enable_msg_objects"):
            for msg in msgs_to_scan:
                role = getattr(msg, "role", msg.get("role") if isinstance(msg, dict) else "")
                name = _get_msg_name(msg)
                if name:
                    if role == "user":
                        user_name = name
                    elif role == "assistant":
                        char_name = name

        # Try IR2 and Classic (Scan system messages)
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
                        classic_match = re.search(r'DATA1: "(.*?)"\s*DATA2: "(.*?)"', content)
                        if classic_match:
                            char_name = classic_match.group(1)
                            user_name = classic_match.group(2)

        # 2. Format Messages
        template = self.config_manager.get_setting("formatting", "formatting_template") or ""
        divider = self.config_manager.get_setting("formatting", "formatting_divider") or ""

        # Unescape newlines in both the template and divider.
        # We want users to be able to enter \n in the settings UI.
        template = str(template).replace("\\n", "\n")
        divider = str(divider).replace("\\n", "\n")
        
        formatted_parts = []
        
        if isinstance(messages, list):
            for msg in messages:
                role_raw = getattr(msg, "role", msg.get("role") if isinstance(msg, dict) else "")
                content = getattr(msg, "content", msg.get("content") if isinstance(msg, dict) else "")
                
                # Get per-message name if available and enabled
                msg_name = None
                if self.config_manager.get_setting("formatting", "enable_msg_objects"):
                    msg_name = _get_msg_name(msg)
                
                # Map role
                display_role = "System"
                display_name = "System"
                
                if role_raw == "user":
                    display_role = "User"
                    display_name = msg_name if msg_name else user_name
                elif role_raw == "assistant":
                    display_role = "Character"
                    display_name = msg_name if msg_name else char_name
                
                # Apply template
                part = template.replace("{{name}}", display_name)\
                               .replace("{{role}}", display_role)\
                               .replace("{{content}}", content)
                formatted_parts.append(part)
        else:
            # Single string message - treat as User
            part = template.replace("{{name}}", user_name)\
                           .replace("{{role}}", "User")\
                           .replace("{{content}}", messages)
            formatted_parts.append(part)
            
        final_message = divider.join(formatted_parts)
        
        # 3. Injection
        injection_pos = self.config_manager.get_setting("formatting", "injection_position")
        injection_content = self.config_manager.get_setting("formatting", "injection_content")

        def _render_injection(text: str) -> str:
            rendered = "" if text is None else str(text)

            # v2 placeholders (recommended)
            rendered = rendered.replace("{{user}}", user_name)
            rendered = rendered.replace("{{char}}", char_name)

            # Compatibility: common v1-style placeholders in injections
            rendered = rendered.replace("{username}", user_name)
            rendered = rendered.replace("{asstname}", char_name)

            # Convenience aliases
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

    async def _process_chunk(self, chunk: bytes, queue: asyncio.Queue):
        try:
            text = chunk.decode("utf-8")
            lines = text.split("\n")
            
            # Cache settings once per chunk processing
            anti_censorship = self.config_manager.get_setting("deepseek_behavior", "anti_censorship")
            send_deepthink = (
                self.current_send_deepthink
                if self.current_send_deepthink is not None
                else self.config_manager.get_setting("deepseek_behavior", "send_deepthink")
            )
            

            
            for line in lines:
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]": 
                        continue
                    
                    try:
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
                            if anti_censorship:
                                if item_p == "status" and item_v == "CONTENT_FILTER":
                                    Logger.info("Anti-Censorship triggered: Suppressing refusal message.")
                                    finish_reason = "stop"
                                    if getattr(self, "thinking_active", False):
                                        if send_deepthink:
                                            content += "</think>"
                                        self.thinking_active = False
                                    should_stop_processing = True
                                    break

                            # Status update
                            if item_p == "status":
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
