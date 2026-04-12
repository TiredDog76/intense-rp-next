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
from typing import List, Optional, Dict, Any, Callable, Literal, Union

from drivers.base_driver import BaseDriver
from drivers.parallel_manager import ParallelDriversManager
from drivers.providers import DriverProvider
from remote_control import RemoteControlActions, RemoteControlWeb
from utils.ip_utils import is_ip_address_allowed
from utils.logger import Logger
from utils.model_ids import (
    build_openai_model_list,
    get_model_ids_for_provider,
    get_model_ids_for_providers,
    get_owned_by_for_provider,
    is_umm_enabled,
    is_supported_model_id,
    resolve_provider_from_model_id,
)

_RATE_LIMIT_LIKE_RE = re.compile(
    r"(rate\s*limit|too\s*many\s*requests|\b429\b|quota|limit\s*reached)",
    flags=re.IGNORECASE,
)
_NON_RETRYABLE_PROVIDER_ERROR_RE = re.compile(
    r"(peak\s*hours|at\s*capacity|model\s*concurrency\s*limit|concurrency\s*limit)",
    flags=re.IGNORECASE,
)

DEFAULT_MAX_REQUEST_QUEUE_SIZE = 128
QueueStateListener = Callable[[], None]


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


def _is_non_retryable_provider_error(message: str) -> bool:
    return bool(_NON_RETRYABLE_PROVIDER_ERROR_RE.search(str(message or "")))


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
    max_tokens: Optional[int] = None


CompletionPromptInput = Union[str, List[str]]
RequestType = Literal["chat", "text"]


class TextCompletionRequest(BaseModel):
    prompt: CompletionPromptInput
    model: str = "deepseek-auto"
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None


QueuedRequest = Union[ChatCompletionRequest, TextCompletionRequest]


def _normalize_text_completion_prompt(prompt: CompletionPromptInput) -> str:
    if isinstance(prompt, str):
        return prompt

    if not isinstance(prompt, list):
        raise HTTPException(status_code=422, detail="`prompt` must be a string or a list of strings.")

    if not prompt:
        raise HTTPException(status_code=422, detail="`prompt` must not be empty.")

    for item in prompt:
        if not isinstance(item, str):
            raise HTTPException(
                status_code=422,
                detail="Only string prompts are currently supported for `/v1/completions`.",
            )

    if len(prompt) > 1:
        raise HTTPException(
            status_code=400,
            detail="Only a single prompt is currently supported for `/v1/completions`.",
        )

    return prompt[0]


def _normalize_usage_object(usage: Any) -> dict[str, Any]:
    if isinstance(usage, dict):
        usage_obj = dict(usage)
        try:
            usage_obj["prompt_tokens"] = int(usage_obj.get("prompt_tokens") or 0)
        except Exception:
            usage_obj["prompt_tokens"] = 0
        try:
            usage_obj["completion_tokens"] = int(usage_obj.get("completion_tokens") or 0)
        except Exception:
            usage_obj["completion_tokens"] = 0
        try:
            usage_obj["total_tokens"] = int(usage_obj.get("total_tokens") or 0)
        except Exception:
            usage_obj["total_tokens"] = usage_obj["prompt_tokens"] + usage_obj["completion_tokens"]
        return usage_obj

    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def _make_text_completion_sse_chunk(parsed: dict, *, default_model: str) -> str | None:
    if "error" in parsed:
        return f"data: {json.dumps(parsed)}\n\n"

    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    choice0 = choices[0] if isinstance(choices[0], dict) else {}
    try:
        index = int(choice0.get("index") or 0)
    except Exception:
        index = 0

    text = ""
    delta = choice0.get("delta")
    if isinstance(delta, dict):
        delta_content = delta.get("content")
        if isinstance(delta_content, str):
            text = delta_content

    if not text:
        message = choice0.get("message")
        if isinstance(message, dict):
            message_content = message.get("content")
            if isinstance(message_content, str):
                text = message_content

    finish_reason = choice0.get("finish_reason")
    created = parsed.get("created")
    try:
        created = int(created or 0)
    except Exception:
        created = 0
    if created <= 0:
        created = int(time.time())

    completion_chunk = {
        "id": "cmpl-custom",
        "object": "text_completion",
        "created": created,
        "model": str(parsed.get("model") or default_model or ""),
        "choices": [
            {
                "text": text,
                "index": index,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(completion_chunk)}\n\n"

@dataclass
class QueueEntry:
    id: str
    queued_at: float
    request: QueuedRequest
    request_type: RequestType
    target_provider: DriverProvider
    response_queue: asyncio.Queue
    abort_event: asyncio.Event
    api_key_name: Optional[str] = None

class RequestQueueFullError(Exception):
    def __init__(self, *, max_size: int, current_size: int):
        super().__init__(f"Request queue is full ({current_size}/{max_size})")
        self.max_size = max_size
        self.current_size = current_size

class RequestQueue:
    def __init__(self, max_size: int = DEFAULT_MAX_REQUEST_QUEUE_SIZE):
        self._items = deque()
        self._condition = asyncio.Condition()
        self._max_size = max(1, int(max_size))
        self._listeners: list[QueueStateListener] = []

    def add_listener(self, listener: QueueStateListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: QueueStateListener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception as exc:
                Logger.debug(f"RequestQueue listener failed: {exc}")

    @property
    def max_size(self) -> int:
        return self._max_size

    async def put(self, item: QueueEntry) -> None:
        async with self._condition:
            current_size = len(self._items)
            if current_size >= self._max_size:
                raise RequestQueueFullError(
                    max_size=self._max_size,
                    current_size=current_size,
                )
            self._items.append(item)
            self._condition.notify(1)
        self._notify_listeners()

    async def get(self) -> QueueEntry:
        async with self._condition:
            while not self._items:
                await self._condition.wait()
            item = self._items.popleft()
        self._notify_listeners()
        return item

    async def snapshot(self) -> list[QueueEntry]:
        async with self._condition:
            return list(self._items)

    async def drain(self) -> list[QueueEntry]:
        async with self._condition:
            drained = list(self._items)
            self._items.clear()
        if drained:
            self._notify_listeners()
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
        if removed:
            self._notify_listeners()
        return removed

class API:
    def __init__(
        self,
        driver: BaseDriver | ParallelDriversManager,
        *,
        remote_actions: RemoteControlActions | None = None,
    ):
        self.app = FastAPI()
        self.driver = driver
        self._queue_state_listeners: list[QueueStateListener] = []
        self._request_queue_listener = self._notify_queue_state_changed
        self._drivers_by_provider: dict[DriverProvider, BaseDriver] = self._build_runtime_drivers_map()
        self._request_queues_by_provider: dict[DriverProvider, RequestQueue] = {
            provider: RequestQueue() for provider in self._drivers_by_provider
        }
        for queue in self._request_queues_by_provider.values():
            queue.add_listener(self._request_queue_listener)

        self.request_queue = next(iter(self._request_queues_by_provider.values()), RequestQueue())
        self.current_entry: Optional[QueueEntry] = None
        self.current_abort_event: asyncio.Event = None
        self.current_entries_by_provider: dict[DriverProvider, QueueEntry] = {}
        self.current_abort_events_by_provider: dict[DriverProvider, asyncio.Event] = {}
        self.remote_control: RemoteControlWeb | None = None
        if remote_actions is not None:
            self.remote_control = RemoteControlWeb(
                getattr(self.driver, "config_manager", None),
                enforce_ip_whitelist=self._enforce_ip_whitelist,
                actions=remote_actions,
            )
        self.setup_routes()
        if self.remote_control is not None:
            self.remote_control.register_routes(self.app)
        self.start_worker()

    def _build_runtime_drivers_map(self) -> dict[DriverProvider, BaseDriver]:
        if isinstance(self.driver, ParallelDriversManager):
            return {
                provider: driver
                for provider, driver in self.driver.iter_drivers()
                if driver is not None
            }

        provider = getattr(self.driver, "provider", None)
        effective_provider = provider if isinstance(provider, DriverProvider) else DriverProvider.DEEPSEEK
        return {effective_provider: self.driver}

    def _is_multi_provider_runtime(self) -> bool:
        return len(self._drivers_by_provider) >= 2

    def _get_driver_for_provider(self, provider: DriverProvider) -> BaseDriver:
        driver = self._drivers_by_provider.get(provider)
        if driver is None:
            raise KeyError(f"No runtime driver is registered for provider: {provider.value}")
        return driver

    def _get_request_queue_for_provider(self, provider: DriverProvider) -> RequestQueue:
        queue = self._request_queues_by_provider.get(provider)
        if queue is None:
            raise KeyError(f"No request queue is registered for provider: {provider.value}")
        return queue

    def _get_active_loadout_name_for_provider(self, provider: DriverProvider) -> str | None:
        try:
            driver = self._get_driver_for_provider(provider)
        except Exception:
            driver = None

        config_view = getattr(driver, "config_manager", None)
        getter = getattr(config_view, "get_active_loadout_name", None)
        if callable(getter):
            try:
                return getter(runtime=True)
            except Exception:
                pass

        shared_config = getattr(self.driver, "config_manager", None)
        fallback = getattr(shared_config, "get_runtime_active_loadout_name", None)
        if callable(fallback):
            try:
                return fallback(provider)
            except Exception:
                pass

        return None

    def _get_default_provider(self) -> DriverProvider:
        if self._drivers_by_provider:
            return next(iter(self._drivers_by_provider.keys()))
        return DriverProvider.DEEPSEEK

    def _resolve_request_provider(self, model: Any) -> DriverProvider:
        if not self._is_multi_provider_runtime():
            return self._get_default_provider()

        provider = resolve_provider_from_model_id(model)
        if provider is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Providers in Parallel only accepts provider-prefixed model IDs "
                    "(for example `deepseek-auto` or `glm-chat`). "
                    "Universal model names like `intenserp-auto` are not valid here."
                ),
            )

        if provider not in self._drivers_by_provider:
            raise HTTPException(
                status_code=400,
                detail=f"Provider `{provider.value}` is not enabled in Providers in Parallel.",
            )

        return provider

    def _ensure_supported_model_id(self, model: Any, provider: DriverProvider) -> None:
        normalized = str(model or "").strip()
        cfg = getattr(self.driver, "config_manager", None)
        if is_supported_model_id(provider, normalized, cfg):
            return

        supported_ids = get_model_ids_for_provider(
            provider,
            cfg,
            force_legacy=self._is_multi_provider_runtime(),
        )
        detail = (
            f"Unsupported model `{normalized or '<empty>'}` for provider `{provider.value}`. "
            f"Supported IDs: {', '.join(f'`{model_id}`' for model_id in supported_ids)}."
        )
        if (not self._is_multi_provider_runtime()) and is_umm_enabled(cfg):
            detail += " Provider-prefixed IDs are also still accepted."
        if provider == DriverProvider.AI_STUDIO:
            detail += (
                " Google AI Studio also accepts legacy IDs with Thinking Level suffixes like "
                "`aistudio-auto-high` or `aistudio-auto-r4`."
            )

        raise HTTPException(status_code=400, detail=detail)

    def _find_processing_provider_for_abort_event(
        self, abort_event: asyncio.Event | None
    ) -> DriverProvider | None:
        if abort_event is None:
            return None

        for provider, current_abort_event in self.current_abort_events_by_provider.items():
            if current_abort_event is abort_event:
                return provider

        return None

    def _request_abort_for_abort_event(self, abort_event: asyncio.Event | None) -> None:
        provider = self._find_processing_provider_for_abort_event(abort_event)
        if provider is None:
            return

        try:
            self._get_driver_for_provider(provider).request_abort()
        except Exception:
            pass

    async def _remove_queued_request_by_abort_event(self, abort_event: asyncio.Event) -> bool:
        for queue in self._request_queues_by_provider.values():
            try:
                removed = await queue.remove_by_abort_event(abort_event)
            except Exception:
                removed = False
            if removed:
                return True

        return False

    async def snapshot_requests(self) -> list[tuple[str, QueueEntry]]:
        entries: list[tuple[str, QueueEntry]] = []

        for provider in self._drivers_by_provider:
            current = self.current_entries_by_provider.get(provider)
            if current is not None:
                current_status = "cancelled" if current.abort_event.is_set() else "processing"
                entries.append((current_status, current))

        for provider, queue in self._request_queues_by_provider.items():
            queued = await queue.snapshot()
            for entry in queued:
                status = "cancelled" if entry.abort_event.is_set() else "pending"
                entries.append((status, entry))

        def _sort_key(item: tuple[str, QueueEntry]) -> tuple[int, float, str]:
            status, entry = item
            status_order = 0 if status == "processing" else 1
            queued_at = float(getattr(entry, "queued_at", 0.0) or 0.0)
            entry_id = str(getattr(entry, "id", "") or "")
            return (status_order, queued_at, entry_id)

        return sorted(entries, key=_sort_key)

    def add_queue_state_listener(self, listener: QueueStateListener) -> None:
        if listener not in self._queue_state_listeners:
            self._queue_state_listeners.append(listener)

    def remove_queue_state_listener(self, listener: QueueStateListener) -> None:
        try:
            self._queue_state_listeners.remove(listener)
        except ValueError:
            pass

    def _notify_queue_state_changed(self) -> None:
        for listener in list(self._queue_state_listeners):
            try:
                listener()
            except Exception as exc:
                Logger.debug(f"Queue state listener failed: {exc}")

    async def abort_current_request(self, reason: str | None = None) -> bool:
        current_entries = list(self.current_entries_by_provider.items())
        if not current_entries:
            return False

        message = (reason or "Request aborted.").strip() or "Request aborted."
        aborted_any = False

        for provider, entry in current_entries:
            aborted = await self.abort_current_request_for_provider(provider, reason=message)
            aborted_any = aborted_any or aborted

        return aborted_any

    async def abort_current_request_for_provider(
        self,
        provider: DriverProvider,
        reason: str | None = None,
    ) -> bool:
        entry = self.current_entries_by_provider.get(provider)
        if entry is None:
            return False

        message = (reason or "Request aborted.").strip() or "Request aborted."
        abort_event = getattr(entry, "abort_event", None)
        if abort_event is not None:
            try:
                abort_event.set()
            except Exception:
                pass

        try:
            self._get_driver_for_provider(provider).request_abort()
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

        self._notify_queue_state_changed()
        return True

    async def cancel_queued_requests(self, reason: str | None = None) -> int:
        message = (reason or "Request cancelled.").strip() or "Request cancelled."

        cancelled = 0
        for queue in self._request_queues_by_provider.values():
            try:
                entries = await queue.drain()
            except Exception:
                entries = []

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

    def _enforce_ip_whitelist(self, raw_request: Request) -> Optional[str]:
        cfg = getattr(self.driver, "config_manager", None)
        if not cfg or not cfg.get_setting("network_settings", "use_ip_whitelist"):
            return None

        client = getattr(raw_request, "client", None)
        client_host = str(getattr(client, "host", "") or "").strip()
        if not client_host:
            Logger.warning("Blocked request: could not determine client IP while IP whitelist is enabled.")
            raise HTTPException(status_code=403, detail="Client IP not allowed")

        allowed_ips = cfg.get_setting("network_settings", "ip_whitelist") or []
        if not is_ip_address_allowed(client_host, allowed_ips):
            Logger.warning(f"Blocked request from IP {client_host}: not in whitelist.")
            raise HTTPException(status_code=403, detail="Client IP not allowed")

        return client_host

    def _authorize_request(self, raw_request: Request) -> Optional[str]:
        self._enforce_ip_whitelist(raw_request)
        return self._authenticate_request(raw_request)

    def setup_routes(self):
        @self.app.get("/v1/models")
        async def list_models(raw_request: Request):
            self._authorize_request(raw_request)

            cfg = getattr(self.driver, "config_manager", None)
            runtime_providers = list(self._drivers_by_provider.keys()) or [DriverProvider.DEEPSEEK]

            if self._is_multi_provider_runtime():
                model_data = []
                for provider, model_id in get_model_ids_for_providers(
                    runtime_providers,
                    cfg,
                    force_legacy=True,
                ):
                    model_data.extend(
                        build_openai_model_list(
                            [model_id],
                            owned_by=get_owned_by_for_provider(provider),
                        )
                    )
                return {
                    "object": "list",
                    "data": model_data,
                }

            effective_provider = runtime_providers[0]
            model_ids = get_model_ids_for_provider(effective_provider, cfg)

            return {
                "object": "list",
                "data": build_openai_model_list(
                    model_ids,
                    owned_by=get_owned_by_for_provider(effective_provider),
                ),
            }

        @self.app.post("/v1/chat/completions")
        async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
            # Optional API key authentication (Bearer token)
            api_key_name = self._authorize_request(raw_request)

            if not self.driver.is_running:
                raise HTTPException(status_code=503, detail="Driver is not running")

            target_provider = self._resolve_request_provider(request.model)
            self._ensure_supported_model_id(request.model, target_provider)

            # Log incoming request
            msg_count = len(request.messages)
            stream_mode = "streaming" if request.stream else "non-streaming"
            loadout_name = self._get_active_loadout_name_for_provider(target_provider)
            Logger.info(
                f"Received chat completion request for {target_provider.value} "
                f"({msg_count} messages, {stream_mode})"
                + (f" using loadout '{loadout_name}'" if loadout_name else "")
            )

            # Create a queue for the response chunks
            response_queue = asyncio.Queue()
            
            # Create an abort event for this request
            abort_event = asyncio.Event()
            
            # Put the request, response queue, and abort event into the main request queue
            entry = QueueEntry(
                id=secrets.token_hex(4),
                queued_at=time.time(),
                request=request,
                request_type="chat",
                target_provider=target_provider,
                response_queue=response_queue,
                abort_event=abort_event,
                api_key_name=api_key_name,
            )
            try:
                await self._get_request_queue_for_provider(target_provider).put(entry)
            except RequestQueueFullError as exc:
                Logger.warning(
                    "Rejecting chat completion request because the request queue is full "
                    f"({exc.current_size}/{exc.max_size} pending requests)."
                )
                raise HTTPException(
                    status_code=429,
                    detail="Request queue is full. Please retry shortly.",
                    headers={"Retry-After": "1"},
                ) from exc
            
            if request.stream:
                return StreamingResponse(
                    self.stream_generator(response_queue, abort_event, raw_request),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            else:
                # Accumulate response for non-streaming
                content_parts: list[str] = []
                finish_reason = None
                error_message: str | None = None
                usage: dict | None = None
                
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

                    if isinstance(parsed.get("usage"), dict):
                        usage = parsed.get("usage")

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
                    self._request_abort_for_abort_event(abort_event)

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
                    "usage": _normalize_usage_object(usage),
                }

        @self.app.post("/v1/completions")
        async def text_completions(request: TextCompletionRequest, raw_request: Request):
            api_key_name = self._authorize_request(raw_request)

            if not self.driver.is_running:
                raise HTTPException(status_code=503, detail="Driver is not running")

            target_provider = self._resolve_request_provider(request.model)
            self._ensure_supported_model_id(request.model, target_provider)

            normalized_prompt = _normalize_text_completion_prompt(request.prompt)
            normalized_request = request.model_copy(update={"prompt": normalized_prompt})

            prompt_length = len(normalized_prompt)
            stream_mode = "streaming" if normalized_request.stream else "non-streaming"
            loadout_name = self._get_active_loadout_name_for_provider(target_provider)
            Logger.info(
                f"Received text completion request for {target_provider.value} "
                f"({prompt_length} chars, {stream_mode})"
                + (f" using loadout '{loadout_name}'" if loadout_name else "")
            )

            response_queue = asyncio.Queue()
            abort_event = asyncio.Event()

            entry = QueueEntry(
                id=secrets.token_hex(4),
                queued_at=time.time(),
                request=normalized_request,
                request_type="text",
                target_provider=target_provider,
                response_queue=response_queue,
                abort_event=abort_event,
                api_key_name=api_key_name,
            )
            try:
                await self._get_request_queue_for_provider(target_provider).put(entry)
            except RequestQueueFullError as exc:
                Logger.warning(
                    "Rejecting text completion request because the request queue is full "
                    f"({exc.current_size}/{exc.max_size} pending requests)."
                )
                raise HTTPException(
                    status_code=429,
                    detail="Request queue is full. Please retry shortly.",
                    headers={"Retry-After": "1"},
                ) from exc

            if normalized_request.stream:
                return StreamingResponse(
                    self.stream_generator(
                        response_queue,
                        abort_event,
                        raw_request,
                        chunk_transform=lambda chunk: _make_text_completion_sse_chunk(
                            chunk,
                            default_model=normalized_request.model,
                        ),
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )

            content_parts: list[str] = []
            finish_reason = None
            error_message: str | None = None
            usage: dict | None = None

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

                if isinstance(parsed.get("usage"), dict):
                    usage = parsed.get("usage")

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
                self._request_abort_for_abort_event(abort_event)

                if content_parts:
                    Logger.warning(
                        "Non-streaming text completion returned partial content due to error: "
                        + str(error_message)
                    )
                else:
                    raise HTTPException(status_code=500, detail=error_message)

            return {
                "id": "cmpl-custom",
                "object": "text_completion",
                "created": 0,
                "model": normalized_request.model,
                "choices": [
                    {
                        "text": full_content,
                        "index": 0,
                        "logprobs": None,
                        "finish_reason": finish_reason or "stop",
                    }
                ],
                "usage": _normalize_usage_object(usage),
            }

    async def stream_generator(
        self,
        response_queue: asyncio.Queue,
        abort_event: asyncio.Event,
        raw_request: Request,
        chunk_transform: Callable[[dict], str | None] | None = None,
    ):
        try:
            while True:
                # Check if client disconnected
                if await raw_request.is_disconnected():
                    Logger.warning("Client disconnected, aborting request...")
                    abort_event.set()
                    self._notify_queue_state_changed()
                    removed = await self._remove_queued_request_by_abort_event(abort_event)
                    if not removed:
                        self._request_abort_for_abort_event(abort_event)
                    break
                
                try:
                    # Use a timeout so we can periodically check for disconnection
                    chunk = await asyncio.wait_for(response_queue.get(), timeout=0.5)
                    if chunk is None:
                        yield "data: [DONE]\n\n"
                        break
                    if chunk_transform is not None:
                        parsed = _parse_sse_json(chunk)
                        if parsed is None:
                            continue
                        chunk = chunk_transform(parsed)
                        if chunk is None:
                            continue
                    yield chunk
                except asyncio.TimeoutError:
                    # No chunk available, continue to check for disconnection
                    continue
        except asyncio.CancelledError:
            Logger.warning("Stream generator cancelled, aborting...")
            abort_event.set()
            self._notify_queue_state_changed()
            asyncio.create_task(self._remove_queued_request_by_abort_event(abort_event))
            self._request_abort_for_abort_event(abort_event)
        except GeneratorExit:
            # Client disconnected abruptly
            Logger.warning("Generator exit, aborting...")
            abort_event.set()
            self._notify_queue_state_changed()
            asyncio.create_task(self._remove_queued_request_by_abort_event(abort_event))
            self._request_abort_for_abort_event(abort_event)

    def start_worker(self):
        self.worker_tasks = {
            provider: asyncio.create_task(self.worker(provider))
            for provider in self._drivers_by_provider
        }

    def _sync_current_entry_aliases(self) -> None:
        active_entries = list(self.current_entries_by_provider.values())
        active_abort_events = list(self.current_abort_events_by_provider.values())
        self.current_entry = active_entries[0] if len(active_entries) == 1 else None
        self.current_abort_event = active_abort_events[0] if len(active_abort_events) == 1 else None

    async def stop(self):
        Logger.info("Stopping API worker...")
        for queue in self._request_queues_by_provider.values():
            try:
                queue.remove_listener(self._request_queue_listener)
            except Exception:
                pass

        remote_control = getattr(self, "remote_control", None)
        if remote_control is not None:
            try:
                remote_control.stop()
            except Exception as exc:
                Logger.warning(f"Failed to stop Remote Control worker cleanly: {exc}")
            finally:
                self.remote_control = None

        worker_tasks = dict(getattr(self, "worker_tasks", {}) or {})
        for task in worker_tasks.values():
            task.cancel()

        for provider, task in worker_tasks.items():
            try:
                await task
            except asyncio.CancelledError:
                Logger.debug(f"API Worker cancelled for {provider.value}")

        self.worker_tasks = {}
        Logger.info("API worker stopped.")

    async def worker(self, provider: DriverProvider):
        driver = self._get_driver_for_provider(provider)
        request_queue = self._get_request_queue_for_provider(provider)
        Logger.info(f"API Worker started for {provider.value}")
        try:
            while True:
                entry = await request_queue.get()
                request = entry.request
                request_type = getattr(entry, "request_type", "chat")
                response_queue = entry.response_queue
                abort_event = entry.abort_event
                loadout_name = self._get_active_loadout_name_for_provider(provider)
                Logger.info(
                    f"Processing queued {request_type} request for {provider.value}..."
                    + (f" (loadout: {loadout_name})" if loadout_name else "")
                )
                try:
                    if abort_event.is_set():
                        Logger.info("Queued request was already aborted. Skipping.")
                        continue

                    self.current_entries_by_provider[provider] = entry
                    self.current_abort_events_by_provider[provider] = abort_event
                    self._sync_current_entry_aliases()
                    self._notify_queue_state_changed()

                    try:
                        ece_reauth_enabled = bool(driver.ece_reauth_enabled())
                    except Exception:
                        ece_reauth_enabled = False

                    max_attempts = 2 if ece_reauth_enabled else 1
                    attempt = 0
                    forwarded_any = False

                    while attempt < max_attempts and (not abort_event.is_set()):
                        attempt += 1

                        # Track usage for Select Least Used
                        try:
                            pair_getter = getattr(driver, "ece_active_pair", None)
                            mark_used = getattr(driver, "ece_mark_used", None)
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
                            await driver.apply_configured_model()
                        except Exception as e:
                            provider_label = getattr(driver, "provider_label", None) or provider.value
                            Logger.warning(f"{provider_label}: Failed to apply configured model selection: {e}")

                        meaningful_seen = False
                        buffered: list[str] = []
                        early_error_message: str | None = None

                        try:
                            driver_message = (
                                request.messages
                                if request_type == "chat"
                                else _normalize_text_completion_prompt(request.prompt)
                            )
                            async for chunk in driver.generate_response(
                                message=driver_message,
                                model=request.model,
                                stream=request.stream,
                                temperature=request.temperature,
                                top_p=request.top_p,
                                max_tokens=request.max_tokens,
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
                                        for buffered_chunk in buffered:
                                            await response_queue.put(buffered_chunk)
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
                        if (
                            (not is_final_attempt)
                            and (not forwarded_any)
                            and (not _is_non_retryable_provider_error(early_error_message))
                        ):
                            reason = early_error_message or "no meaningful output"
                            if early_error_message and _is_rate_limit_like_error(early_error_message):
                                reason = f"rate-limit-like failure: {early_error_message}"

                            restarted = False
                            if not abort_event.is_set():
                                restart = getattr(driver, "ece_restart_with_rotation", None)
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
                            for buffered_chunk in buffered:
                                await response_queue.put(buffered_chunk)
                                forwarded_any = True

                        break

                except Exception as e:
                    Logger.error(f"Error in {provider.value} worker: {e}")
                    await response_queue.put(_make_openai_error_sse_chunk(str(e)))
                finally:
                    self.current_entries_by_provider.pop(provider, None)
                    self.current_abort_events_by_provider.pop(provider, None)
                    self._sync_current_entry_aliases()
                    self._notify_queue_state_changed()
                    await response_queue.put(None)
                    Logger.success(f"Request completed for {provider.value}.")
        except asyncio.CancelledError:
            Logger.info(f"API Worker cancelled for {provider.value}")
            raise
