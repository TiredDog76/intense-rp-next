import asyncio
import json
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from drivers.base_driver import BaseDriver
from drivers.providers import DriverProvider
from utils.logger import Logger

_RATE_LIMIT_LIKE_RE = re.compile(
    r"(rate\s*limit|too\s*many\s*requests|\b429\b|quota|limit\s*reached)",
    flags=re.IGNORECASE,
)


def _parse_sse_json(chunk: Any) -> dict | None:
    if not isinstance(chunk, str):
        return None
    if not chunk.startswith("data:"):
        return None

    data_str = chunk[len("data:") :]
    if data_str.startswith(" "):
        data_str = data_str[1:]
    data_str = data_str.strip()

    if not data_str or data_str == "[DONE]":
        return None

    try:
        parsed = json.loads(data_str)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_error_message(payload: dict) -> str:
    err = payload.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        return str(msg or "")
    return str(err or "")


def _payload_has_meaningful_content(payload: dict) -> bool:
    try:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return False

        choice0 = choices[0]
        if not isinstance(choice0, dict):
            return False

        delta = choice0.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str) and content.strip():
                return True

        # Non-streaming responses can carry content in 'message'
        message = choice0.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return True
    except Exception:
        return False

    return False


def _is_rate_limit_like_error(message: str) -> bool:
    return bool(_RATE_LIMIT_LIKE_RE.search(str(message or "")))


def _make_openai_error_sse_chunk(message: str) -> str:
    error_chunk = {
        "error": {
            "message": str(message or ""),
            "type": "internal_error",
            "param": None,
            "code": None,
        }
    }
    return f"data: {json.dumps(error_chunk)}\n\n"

class Message(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    model: str = "deepseek-auto"
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None

@dataclass
class QueueEntry:
    id: str
    queued_at: float
    request: ChatCompletionRequest
    response_queue: asyncio.Queue
    abort_event: asyncio.Event
    api_key_name: Optional[str] = None

class RequestQueue:
    def __init__(self):
        self._items = deque()
        self._condition = asyncio.Condition()

    async def put(self, item: QueueEntry) -> None:
        async with self._condition:
            self._items.append(item)
            self._condition.notify(1)

    async def get(self) -> QueueEntry:
        async with self._condition:
            while not self._items:
                await self._condition.wait()
            return self._items.popleft()

    async def snapshot(self) -> list[QueueEntry]:
        async with self._condition:
            return list(self._items)

    async def drain(self) -> list[QueueEntry]:
        async with self._condition:
            drained = list(self._items)
            self._items.clear()
            return drained

    async def remove_by_abort_event(self, abort_event: asyncio.Event) -> bool:
        async with self._condition:
            if not self._items:
                return False

            removed = False
            kept = deque()
            while self._items:
                item = self._items.popleft()
                if (not removed) and item.abort_event is abort_event:
                    removed = True
                    continue
                kept.append(item)

            self._items = kept
            return removed

class API:
    def __init__(self, driver: BaseDriver):
        self.app = FastAPI()
        self.driver = driver
        self.request_queue = RequestQueue()
        self.current_entry: Optional[QueueEntry] = None
        self.current_abort_event: asyncio.Event = None  # Track current request's abort event
        self.setup_routes()
        self.start_worker()

    async def abort_current_request(self, reason: str | None = None) -> bool:
        entry = getattr(self, "current_entry", None)
        abort_event = getattr(self, "current_abort_event", None)
        if not entry or not abort_event:
            return False

        message = (reason or "Request aborted.").strip() or "Request aborted."

        try:
            abort_event.set()
        except Exception:
            pass

        try:
            self.driver.request_abort()
        except Exception:
            pass

        try:
            await entry.response_queue.put(_make_openai_error_sse_chunk(message))
        except Exception:
            pass

        try:
            await entry.response_queue.put(None)
        except Exception:
            pass

        return True

    async def cancel_queued_requests(self, reason: str | None = None) -> int:
        message = (reason or "Request cancelled.").strip() or "Request cancelled."

        try:
            entries = await self.request_queue.drain()
        except Exception:
            entries = []

        cancelled = 0
        for entry in entries:
            abort_event = getattr(entry, "abort_event", None)
            if abort_event is not None:
                try:
                    abort_event.set()
                except Exception:
                    pass

            try:
                await entry.response_queue.put(_make_openai_error_sse_chunk(message))
            except Exception:
                pass

            try:
                await entry.response_queue.put(None)
            except Exception:
                pass

            cancelled += 1

        return cancelled

    def _authenticate_request(self, raw_request: Request) -> Optional[str]:
        cfg = getattr(self.driver, "config_manager", None)
        if not cfg or not cfg.get_setting("network_settings", "use_api_keys"):
            return None

        auth_header = raw_request.headers.get("Authorization") or ""
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing API key")

        token = auth_header.split(" ", 1)[1].strip()
        pairs = cfg.get_setting("network_settings", "api_keys") or []

        matched_name = None
        for p in pairs:
            name = ""
            key_val = ""
            if isinstance(p, dict):
                name = str(p.get("name", ""))
                key_val = str(p.get("key", ""))
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                name = str(p[0])
                key_val = str(p[1])

            if key_val and token == key_val:
                matched_name = name or "Unnamed"
                break

        if not matched_name:
            raise HTTPException(status_code=401, detail="Invalid API key")

        Logger.info(f"Authenticated request using API key: {matched_name}")
        return matched_name

    def setup_routes(self):
        @self.app.get("/v1/models")
        async def list_models(raw_request: Request):
            self._authenticate_request(raw_request)

            provider = getattr(self.driver, "provider", None)
            if provider == DriverProvider.GLM_CHAT:
                return {
                    "object": "list",
                    "data": [
                        {"id": "glm-auto", "object": "model", "created": 0, "owned_by": "glm"},
                        {"id": "glm-chat", "object": "model", "created": 0, "owned_by": "glm"},
                        {"id": "glm-reasoner", "object": "model", "created": 0, "owned_by": "glm"},
                    ],
                }
            if provider == DriverProvider.MOONSHOT:
                return {
                    "object": "list",
                    "data": [
                        {
                            "id": "moonshot-auto",
                            "object": "model",
                            "created": 0,
                            "owned_by": "moonshot",
                        },
                        {
                            "id": "moonshot-chat",
                            "object": "model",
                            "created": 0,
                            "owned_by": "moonshot",
                        },
                        {
                            "id": "moonshot-reasoner",
                            "object": "model",
                            "created": 0,
                            "owned_by": "moonshot",
                        },
                    ],
                }

            return {
                "object": "list",
                "data": [
                    {"id": "deepseek-auto", "object": "model", "created": 0, "owned_by": "deepseek"},
                    {"id": "deepseek-chat", "object": "model", "created": 0, "owned_by": "deepseek"},
                    {"id": "deepseek-reasoner", "object": "model", "created": 0, "owned_by": "deepseek"},
                ],
            }

        @self.app.post("/v1/chat/completions")
        async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
            # Optional API key authentication (Bearer token)
            api_key_name = self._authenticate_request(raw_request)

            if not self.driver.is_running:
                raise HTTPException(status_code=503, detail="Driver is not running")

            # Log incoming request
            msg_count = len(request.messages)
            stream_mode = "streaming" if request.stream else "non-streaming"
            Logger.info(f"Received chat completion request ({msg_count} messages, {stream_mode})")

            # Create a queue for the response chunks
            response_queue = asyncio.Queue()
            
            # Create an abort event for this request
            abort_event = asyncio.Event()
            
            # Put the request, response queue, and abort event into the main request queue
            entry = QueueEntry(
                id=secrets.token_hex(4),
                queued_at=time.time(),
                request=request,
                response_queue=response_queue,
                abort_event=abort_event,
                api_key_name=api_key_name,
            )
            await self.request_queue.put(entry)
            
            if request.stream:
                return StreamingResponse(
                    self.stream_generator(response_queue, abort_event, raw_request), 
                    media_type="text/event-stream"
                )
            else:
                # Accumulate response for non-streaming
                content_parts: list[str] = []
                finish_reason = None
                error_message: str | None = None
                
                while True:
                    chunk_str = await response_queue.get()
                    if chunk_str is None:
                        break

                    parsed = _parse_sse_json(chunk_str)
                    if not parsed:
                        continue

                    if "error" in parsed:
                        error_message = (_extract_error_message(parsed) or "request failed").strip()
                        if not error_message:
                            error_message = "request failed"
                        break

                    choices = parsed.get("choices")
                    if isinstance(choices, list) and choices:
                        choice0 = choices[0] if isinstance(choices[0], dict) else {}
                        delta = choice0.get("delta") if isinstance(choice0, dict) else {}
                        if isinstance(delta, dict):
                            content = delta.get("content")
                            if isinstance(content, str) and content:
                                content_parts.append(content)
                        if isinstance(choice0, dict):
                            finish_reason = choice0.get("finish_reason")

                full_content = "".join(content_parts)
                
                if error_message:
                    abort_event.set()
                    if self.current_abort_event is abort_event:
                        self.driver.request_abort()

                    # Prefer returning partial content for non-streaming clients if we already have
                    # meaningful output (i.e., avoid losing all progress)
                    if content_parts:
                        Logger.warning(
                            "Non-streaming request returned partial content due to error: "
                            + str(error_message)
                        )
                    else:
                        raise HTTPException(status_code=500, detail=error_message)

                return {
                    "id": "chatcmpl-custom",
                    "object": "chat.completion",
                    "created": 0,
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": full_content
                            },
                            "finish_reason": finish_reason or "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                }

    async def stream_generator(self, response_queue: asyncio.Queue, abort_event: asyncio.Event, raw_request: Request):
        try:
            while True:
                # Check if client disconnected
                if await raw_request.is_disconnected():
                    Logger.warning("Client disconnected, aborting request...")
                    abort_event.set()
                    removed = await self.request_queue.remove_by_abort_event(abort_event)
                    if not removed and self.current_abort_event is abort_event:
                        # Signal the driver to abort (non-blocking)
                        self.driver.request_abort()
                    break
                
                try:
                    # Use a timeout so we can periodically check for disconnection
                    chunk = await asyncio.wait_for(response_queue.get(), timeout=0.5)
                    if chunk is None:
                        yield "data: [DONE]\n\n"
                        break
                    yield chunk
                except asyncio.TimeoutError:
                    # No chunk available, continue to check for disconnection
                    continue
        except asyncio.CancelledError:
            Logger.warning("Stream generator cancelled, aborting...")
            abort_event.set()
            asyncio.create_task(self.request_queue.remove_by_abort_event(abort_event))
            if self.current_abort_event is abort_event:
                self.driver.request_abort()
        except GeneratorExit:
            # Client disconnected abruptly
            Logger.warning("Generator exit, aborting...")
            abort_event.set()
            asyncio.create_task(self.request_queue.remove_by_abort_event(abort_event))
            if self.current_abort_event is abort_event:
                self.driver.request_abort()

    def start_worker(self):
        self.worker_task = asyncio.create_task(self.worker())

    async def stop(self):
        Logger.info("Stopping API worker...")
        if hasattr(self, 'worker_task'):
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        Logger.info("API worker stopped.")

    async def worker(self):
        Logger.info("API Worker started")
        try:
            while True:
                entry = await self.request_queue.get()
                request = entry.request
                response_queue = entry.response_queue
                abort_event = entry.abort_event
                Logger.info("Processing queued request...")
                try:
                    if abort_event.is_set():
                        Logger.info("Queued request was already aborted. Skipping.")
                        continue

                    self.current_entry = entry
                    self.current_abort_event = abort_event

                    try:
                        ece_reauth_enabled = bool(self.driver.ece_reauth_enabled())
                    except Exception:
                        ece_reauth_enabled = False

                    max_attempts = 2 if ece_reauth_enabled else 1
                    attempt = 0
                    forwarded_any = False

                    while attempt < max_attempts and (not abort_event.is_set()):
                        attempt += 1

                        # Track usage for Select Least Used
                        try:
                            pair_getter = getattr(self.driver, "ece_active_pair", None)
                            mark_used = getattr(self.driver, "ece_mark_used", None)
                            if callable(pair_getter) and callable(mark_used):
                                pair = pair_getter()
                                email = getattr(pair, "email", None) if pair else None
                                if isinstance(email, str) and email.strip():
                                    mark_used(email)
                        except Exception:
                            pass

                        # Optional provider hook: apply configured *real* model selection (UI model picker),
                        # if the active provider supports it
                        try:
                            await self.driver.apply_configured_model()
                        except Exception as e:
                            provider_label = getattr(self.driver, "provider_label", None) or "Provider"
                            Logger.warning(f"{provider_label}: Failed to apply configured model selection: {e}")

                        meaningful_seen = False
                        buffered: list[str] = []
                        early_error_message: str | None = None

                        try:
                            async for chunk in self.driver.generate_response(
                                message=request.messages,
                                model=request.model,
                                stream=request.stream,
                                temperature=request.temperature,
                                top_p=request.top_p,
                                abort_event=abort_event,
                            ):
                                if abort_event.is_set():
                                    Logger.debug("Request aborted, stopping chunk forwarding...")
                                    break

                                if not meaningful_seen:
                                    parsed = _parse_sse_json(chunk)
                                    if parsed and ("error" in parsed):
                                        early_error_message = _extract_error_message(parsed)
                                        # Don't forward the error yet; we may retry after rotating
                                        break

                                    if parsed and _payload_has_meaningful_content(parsed):
                                        meaningful_seen = True
                                        for b in buffered:
                                            await response_queue.put(b)
                                            forwarded_any = True
                                        buffered.clear()

                                if meaningful_seen:
                                    await response_queue.put(chunk)
                                    forwarded_any = True
                                else:
                                    buffered.append(chunk)
                        except Exception as e:
                            early_error_message = str(e)

                        if abort_event.is_set():
                            break

                        if early_error_message and meaningful_seen:
                            await response_queue.put(_make_openai_error_sse_chunk(early_error_message))
                            forwarded_any = True
                            break

                        # If we saw meaningful content, keep the existing behavior
                        if meaningful_seen:
                            break

                        # No meaningful chunks were produced
                        is_final_attempt = attempt >= max_attempts
                        if (not is_final_attempt) and (not forwarded_any):
                            reason = early_error_message or "no meaningful output"
                            if early_error_message and _is_rate_limit_like_error(early_error_message):
                                reason = f"rate-limit-like failure: {early_error_message}"

                            restarted = False
                            if not abort_event.is_set():
                                restart = getattr(self.driver, "ece_restart_with_rotation", None)
                                if callable(restart):
                                    try:
                                        restarted = bool(await restart(reason, status_callback=None))
                                    except Exception:
                                        restarted = False
                            if restarted:
                                continue

                        # Can't / won't retry. Prefer surfacing the early error (if any)
                        if early_error_message:
                            await response_queue.put(_make_openai_error_sse_chunk(early_error_message))
                            forwarded_any = True
                        else:
                            for b in buffered:
                                await response_queue.put(b)
                                forwarded_any = True

                        break
                
                except Exception as e:
                    Logger.error(f"Error in worker: {e}")
                    await response_queue.put(_make_openai_error_sse_chunk(str(e)))
                finally:
                    self.current_entry = None
                    self.current_abort_event = None
                    await response_queue.put(None)
                    Logger.success("Request completed.")
        except asyncio.CancelledError:
            Logger.info("API Worker cancelled")
            raise
