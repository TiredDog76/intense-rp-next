import os
import sys
import time
import json
import asyncio
import re
import httpx
import tempfile
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
        
        # Abort handling
        self.current_abort_event: asyncio.Event = None
        self.abort_requested = False
        self.current_model = None
        self.current_send_deepthink = None

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
        
        self.is_running = True
        
        # Invalidate cache on start
        self.cache_manager.clear_cache("last_message.txt")
        
        Logger.success("DeepSeek Driver started successfully.")
        
        # Start monitoring loop
        self.monitoring_active = True
        asyncio.create_task(self._monitor_browser_loop())

    async def login(self):
        """
        Handles the login process if redirected to the sign-in page.
        """
        # Check if we were redirected to sign in
        if "sign_in" in self.page.url:
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
                        await self.page.wait_for_selector(".ds-sign-up-form__main")
                        
                        # Fill email
                        Logger.debug(f"Entering email: {email}")
                        await self.page.fill("input[type='text']", email)
                        
                        # Fill password
                        Logger.debug("Entering password...")
                        await self.page.fill("input[type='password']", password)
                        
                        # Click login button
                        Logger.debug("Clicking login button...")
                        await self.page.click(".ds-sign-up-form__register-button")
                        
                        # Wait for navigation back to the chat page
                        await self.page.wait_for_url("https://chat.deepseek.com/")
                        Logger.success("Login successful.")
                        
                    except Exception as e:
                        Logger.error(f"Error during auto-login: {e}")
            else:
                Logger.info("Auto-login disabled. Waiting for manual login...")
                # Wait indefinitely (or until closed) for the user to log in and reach the chat page
                try:
                    await self.page.wait_for_url("https://chat.deepseek.com/", timeout=0)
                    Logger.success("Manual login detected.")
                except Exception as e:
                    Logger.error(f"Error waiting for manual login: {e}")
        else:
            Logger.info("Not redirected to sign in. Continuing...")

    async def close(self):
        """
        Closes the browser and playwright.
        """
        Logger.info("Closing DeepSeek Driver...")
        self.monitoring_active = False
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                Logger.debug(f"Error closing browser context: {e}")
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                Logger.debug(f"Error closing browser: {e}")
        if self.playwright:
            try:
                await self.playwright.stop()
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

    async def generate_response(self, message: Union[str, List[Any]], model: str = "deepseek-auto", stream: bool = False, temperature: float = None, top_p: float = None, abort_event: asyncio.Event = None):
        """
        Generates a response from DeepSeek.
        This function intercepts the network request to support streaming.
        """
        response_queue = asyncio.Queue()
        
        # Reset state for new generation
        self.fragment_types_list = []
        self.thinking_active = False
        self.abort_requested = False
        self.current_abort_event = abort_event
        resolved_model = (model or "").strip() or "deepseek-auto"
        self.current_model = resolved_model
        effective_deepthink, effective_send_deepthink = self._resolve_deepthink_flags(resolved_model)
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
            formatted_message = self._format_messages(message)
            
            # Check for Clean Regeneration
            clean_regeneration = self.config_manager.get_setting("deepseek_behavior", "clean_regeneration")
            regenerated = False
            
            if clean_regeneration:
                last_message = self.cache_manager.read_cache("last_message.txt")
                if last_message == formatted_message:
                    Logger.info("Clean Regeneration: Message matches cache. Attempting to regenerate...")
                    if await self._click_regenerate():
                        Logger.info("Clean Regeneration: Button clicked. Regenerating...")
                        regenerated = True
                    else:
                        Logger.warning("Clean Regeneration: Button not found or disabled. Falling back to new chat.")
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
                enable_search = self.config_manager.get_setting("deepseek_behavior", "enable_search")
                
                await self.set_deepthink_state(effective_deepthink)
                await self.set_search_state(enable_search)
                
                # Small delay for the toggles to take effect
                await asyncio.sleep(0.5)
                
                # Check if we should send as text file
                send_as_text_file = self.config_manager.get_setting("deepseek_behavior", "send_as_text_file")
                
                if send_as_text_file:
                    Logger.info("Sending message as text file...")
                    # Create a temporary file
                    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
                        temp_file.write(formatted_message)
                        temp_file_path = temp_file.name
                    
                    try:
                        await self._upload_file(temp_file_path)
                    finally:
                        # Clean up the temporary file
                        try:
                            os.remove(temp_file_path)
                        except OSError:
                            pass
                    
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
                    self.cache_manager.write_cache("last_message.txt", formatted_message)
            
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
        button = self.page.locator("button.ds-toggle-button", has_text="DeepThink")
        
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
        button = self.page.locator("button.ds-toggle-button", has_text="Search")
        
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
        sidebar_inner_selector = "div.b8812f16.a2f3d50e"
        sidebar_closed_class = "_70b689f"
        close_button_selector = "div.ds-icon-button._7d1f5e2"
        open_button_selector = "div.e5bf614e >> div.ds-icon-button._4f3769f >> nth=0"

        sidebar_inner = self.page.locator(sidebar_inner_selector)
        if await sidebar_inner.count() == 0:
            Logger.warning("Sidebar inner container not found.")
            return

        class_attr = await sidebar_inner.first.get_attribute("class") or ""
        is_closed = sidebar_closed_class in class_attr
        is_open = not is_closed

        if open:
            if is_open:
                Logger.debug("Sidebar is already open.")
                return

            Logger.debug("Opening sidebar...")
            open_btn = self.page.locator(open_button_selector)
            if await open_btn.is_visible():
                await open_btn.click()
            else:
                Logger.warning("Open sidebar button not visible.")
                
        else:
            if is_closed:
                Logger.debug("Sidebar is already closed.")
                return
            
            Logger.debug("Closing sidebar...")
            close_btn = self.page.locator(close_button_selector)
            if await close_btn.is_visible():
                await close_btn.click()
            else:
                Logger.warning("Close sidebar button not visible.")

    async def click_new_chat(self, source: str = "auto"):
        """
        Clicks the New Chat button.
        """
        simple_new_chat_selector = "div.e5bf614e >> div.ds-icon-button._4f3769f >> nth=1"
        sidebar_new_chat_selector = "div._5a8ac7a.a084f19e"

        if source == "simple":
            Logger.debug("Clicking New Chat (Simple)...")
            btn = self.page.locator(simple_new_chat_selector)
            if await btn.count() > 0:
                await btn.click()
            else:
                Logger.warning("New Chat (Simple) button not found.")
                
        elif source == "sidebar":
            Logger.debug("Clicking New Chat (Sidebar)...")
            btn = self.page.locator(sidebar_new_chat_selector)
            if await btn.count() > 0:
                await btn.click()
            else:
                Logger.warning("New Chat (Sidebar) button not found.")
                
        elif source == "auto":
            Logger.debug("Attempting to click New Chat (Auto)...")
            simple_btn = self.page.locator(simple_new_chat_selector)
            if await simple_btn.count() > 0:
                Logger.debug("Found Simple New Chat button. Clicking...")
                await simple_btn.click()
                return
                
            sidebar_btn = self.page.locator(sidebar_new_chat_selector)
            if await sidebar_btn.count() > 0:
                Logger.debug("Found Sidebar New Chat button. Clicking...")
                await sidebar_btn.click()
                return
                
            Logger.warning("Could not find New Chat button in either mode.")
        else:
            Logger.warning(f"Unknown source: {source}")

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
            Logger.warning("Message textarea not found.")
            return
        Logger.debug(f"Entering message: {message[:50]}..." if len(message) > 50 else f"Entering message: {message}")
        await textarea.fill(message)

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
        # Selector based on my investigation: within ds-flex _965abe9 _54866f7, it's the second button
        # The container has classes _965abe9 and _54866f7
        container_selector = "div.ds-flex._965abe9._54866f7"
        
        # We need the second button inside this container
        # The buttons are div.ds-icon-button
        button_selector = f"{container_selector} >> div.ds-icon-button >> nth=1"
        
        button = self.page.locator(button_selector)
        
        if await button.count() > 0:
            # Check if disabled
            is_disabled = await button.get_attribute("aria-disabled") == "true"
            if is_disabled:
                Logger.warning("Regenerate button is disabled (likely due to censorship).")
                return False
            
            Logger.debug("Clicking regenerate button...")
            await button.click()
            return True
        else:
            Logger.warning("Regenerate button not found.")
            return False

    async def _upload_file(self, file_path: str):
        """
        Uploads a file to the chat.
        """
        Logger.debug(f"Uploading file: {file_path}")
        
        # The file input is hidden or styled, but we can target it by type="file"
        file_input = self.page.locator("input[type='file']")
        
        if await file_input.count() > 0:
            await file_input.set_input_files(file_path)
            Logger.debug("File set to input.")
            
            # Wait a bit for the upload to be processed by the UI
            # You might need to wait for a specific indicator that the file is ready
            await asyncio.sleep(1.0) 
        else:
            Logger.warning("File input not found.")
