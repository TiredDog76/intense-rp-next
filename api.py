import asyncio
import json
from collections import deque
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from deepseek_driver import DeepSeekDriver
from utils.logger import Logger

class RequestQueue:
    def __init__(self):
        self._items = deque()
        self._condition = asyncio.Condition()

    async def put(self, item) -> None:
        async with self._condition:
            self._items.append(item)
            self._condition.notify(1)

    async def get(self):
        async with self._condition:
            while not self._items:
                await self._condition.wait()
            return self._items.popleft()

    async def remove_by_abort_event(self, abort_event: asyncio.Event) -> bool:
        async with self._condition:
            if not self._items:
                return False

            removed = False
            kept = deque()
            while self._items:
                item = self._items.popleft()
                if (not removed) and item[2] is abort_event:
                    removed = True
                    continue
                kept.append(item)

            self._items = kept
            return removed

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

class API:
    def __init__(self, driver: DeepSeekDriver):
        self.app = FastAPI()
        self.driver = driver
        self.request_queue = RequestQueue()
        self.current_abort_event: asyncio.Event = None  # Track current request's abort event
        self.setup_routes()
        self.start_worker()

    def _authenticate_request(self, raw_request: Request) -> None:
        cfg = getattr(self.driver, "config_manager", None)
        if not cfg or not cfg.get_setting("network_settings", "use_api_keys"):
            return

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

    def setup_routes(self):
        @self.app.get("/v1/models")
        async def list_models(raw_request: Request):
            self._authenticate_request(raw_request)

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
            self._authenticate_request(raw_request)

            if not self.driver.is_running:
                raise HTTPException(status_code=503, detail="DeepSeek Driver is not running")

            # Log incoming request
            msg_count = len(request.messages)
            stream_mode = "streaming" if request.stream else "non-streaming"
            Logger.info(f"Received chat completion request ({msg_count} messages, {stream_mode})")

            # Create a queue for the response chunks
            response_queue = asyncio.Queue()
            
            # Create an abort event for this request
            abort_event = asyncio.Event()
            
            # Put the request, response queue, and abort event into the main request queue
            await self.request_queue.put((request, response_queue, abort_event))
            
            if request.stream:
                return StreamingResponse(
                    self.stream_generator(response_queue, abort_event, raw_request), 
                    media_type="text/event-stream"
                )
            else:
                # Accumulate response for non-streaming
                full_content = ""
                finish_reason = None
                
                while True:
                    chunk_str = await response_queue.get()
                    if chunk_str is None:
                        break
                    
                    if chunk_str.startswith("data: "):
                        data_str = chunk_str[6:].strip()
                        if data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    full_content += delta["content"]
                                finish_reason = data["choices"][0].get("finish_reason")
                        except:
                            pass
                
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
                        # Signal the driver to abort (don't await, just set the flag)
                        self.driver.abort_requested = True
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
                # Just set the flag, don't await anything during cancellation
                self.driver.abort_requested = True
        except GeneratorExit:
            # Client disconnected abruptly
            Logger.warning("Generator exit, aborting...")
            abort_event.set()
            asyncio.create_task(self.request_queue.remove_by_abort_event(abort_event))
            if self.current_abort_event is abort_event:
                self.driver.abort_requested = True

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
                request, response_queue, abort_event = await self.request_queue.get()
                Logger.info("Processing queued request...")
                try:
                    if abort_event.is_set():
                        Logger.info("Queued request was already aborted. Skipping.")
                        continue

                    self.current_abort_event = abort_event
                    # Call the driver with the raw messages list
                    # The driver will handle formatting
                    async for chunk in self.driver.generate_response(
                        message=request.messages,
                        model=request.model,
                        stream=request.stream,
                        temperature=request.temperature,
                        top_p=request.top_p,
                        abort_event=abort_event
                    ):
                        # Check if aborted before putting chunk
                        if abort_event.is_set():
                            Logger.debug("Request aborted, stopping chunk forwarding...")
                            break
                        await response_queue.put(chunk)
                    
                except Exception as e:
                    Logger.error(f"Error in worker: {e}")
                    error_chunk = {
                        "error": {
                            "message": str(e),
                            "type": "internal_error",
                            "param": None,
                            "code": None
                        }
                    }
                    await response_queue.put(f"data: {json.dumps(error_chunk)}\n\n")
                finally:
                    self.current_abort_event = None
                    await response_queue.put(None)
                    Logger.success("Request completed.")
        except asyncio.CancelledError:
            Logger.info("API Worker cancelled")
            raise
