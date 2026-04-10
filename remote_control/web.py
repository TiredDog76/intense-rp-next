from __future__ import annotations

import asyncio
import json
import secrets
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from drivers.providers import DriverProvider, provider_options
from utils.logger import LogLevel, Logger
from utils.resource_path import resolve_resource_path

from .sessions import REMOTE_SESSION_TTL_SECONDS, RemoteControlSessionStore


PROVIDER_ICON_MAP: dict[str, str] = {
    DriverProvider.DEEPSEEK.value: "providers/deepseek.svg",
    DriverProvider.GLM_CHAT.value: "providers/zai.svg",
    DriverProvider.MOONSHOT.value: "providers/moonshot.svg",
    DriverProvider.QWEN_LM.value: "providers/qwen.svg",
    DriverProvider.AI_STUDIO.value: "providers/aistudio.svg",
}


@dataclass
class RemoteControlActions:
    stop: Callable[[], Awaitable[None]]
    restart: Callable[[], Awaitable[None]]
    switch_account: Callable[[], Awaitable[None]]
    hotswap: Callable[[str], Awaitable[None]]
    switch_model: Callable[[str], Awaitable[None]]
    get_state: Callable[[], dict[str, Any]]


class RemoteLoginRequest(BaseModel):
    password: str = ""


class RemoteActionRequest(BaseModel):
    provider: str | None = None
    model: str | None = None


class RemoteControlWeb:
    BASE_PATH = "/remote"
    LOG_BACKLOG_LIMIT = 300

    def __init__(
        self,
        config_manager: Any,
        *,
        enforce_ip_whitelist: Callable[[Request], Any],
        actions: RemoteControlActions,
    ) -> None:
        self.config_manager = config_manager
        self._enforce_ip_whitelist = enforce_ip_whitelist
        self._actions = actions
        self._loop = asyncio.get_running_loop()
        self._session_store = RemoteControlSessionStore(self.config_manager.config_dir)
        self._log_history: deque[dict[str, Any]] = deque(maxlen=self.LOG_BACKLOG_LIMIT)
        self._log_subscribers: set[asyncio.Queue] = set()
        self._template_env = Environment(
            loader=FileSystemLoader(
                str(resolve_resource_path("remote_control", "templates"))
            ),
            autoescape=select_autoescape(("html", "xml")),
        )
        self._asset_map = self._build_asset_map()
        Logger.add_listener(self._handle_log_message)

    def _build_asset_map(self) -> dict[str, Path]:
        assets: dict[str, Path] = {
            "brand/newlogo-nobg.png": resolve_resource_path(
                "ui", "assets", "brand", "newlogo-nobg.png"
            ),
            "styles/shell.css": resolve_resource_path(
                "remote_control", "assets", "shell.css"
            ),
            "scripts/shell.js": resolve_resource_path(
                "remote_control", "assets", "shell.js"
            ),
            "icons/check.svg": resolve_resource_path("ui", "assets", "icons", "check.svg"),
            "icons/chevron-down.svg": resolve_resource_path(
                "ui", "assets", "icons", "chevron-down.svg"
            ),
            "icons/chevron-right.svg": resolve_resource_path(
                "ui", "assets", "icons", "chevron-right.svg"
            ),
            "icons/square.svg": resolve_resource_path("ui", "assets", "icons", "square.svg"),
            "icons/terminal.svg": resolve_resource_path(
                "ui", "assets", "icons", "terminal.svg"
            ),
            "icons/brain.svg": resolve_resource_path(
                "ui", "assets", "icons", "sidebar", "brain.svg"
            ),
            "fonts/Blinker-Regular.ttf": resolve_resource_path(
                "ui", "fonts", "Blinker-Regular.ttf"
            ),
            "fonts/Blinker-SemiBold.ttf": resolve_resource_path(
                "ui", "fonts", "Blinker-SemiBold.ttf"
            ),
            "fonts/Blinker-Bold.ttf": resolve_resource_path(
                "ui", "fonts", "Blinker-Bold.ttf"
            ),
            "fonts/Blinker-ExtraBold.ttf": resolve_resource_path(
                "ui", "fonts", "Blinker-ExtraBold.ttf"
            ),
        }

        for provider_name, icon_name in PROVIDER_ICON_MAP.items():
            provider = DriverProvider.from_setting(provider_name)
            provider_key = provider.key if provider is not None else provider_name.lower().replace(" ", "_")
            assets[f"providers/{provider_name}.svg"] = resolve_resource_path(
                "ui", "assets", "icons", icon_name
            )
            assets[f"providers/{provider_key}.svg"] = resolve_resource_path(
                "ui", "assets", "icons", icon_name
            )

        return assets

    def stop(self) -> None:
        Logger.remove_listener(self._handle_log_message)
        for queue in list(self._log_subscribers):
            try:
                queue.put_nowait(None)
            except Exception:
                pass
        self._log_subscribers.clear()

    def register_routes(self, app) -> None:
        @app.get(f"{self.BASE_PATH}")
        async def remote_home(raw_request: Request):
            return self._render_shell(raw_request, initial_view="home")

        @app.get(f"{self.BASE_PATH}/logs")
        async def remote_logs(raw_request: Request):
            return self._render_shell(raw_request, initial_view="logs")

        @app.get(f"{self.BASE_PATH}/hotswap")
        async def remote_hotswap(raw_request: Request):
            return self._render_shell(raw_request, initial_view="hotswap")

        @app.get(f"{self.BASE_PATH}/models")
        async def remote_models(raw_request: Request):
            return self._render_shell(raw_request, initial_view="model-switch")

        @app.get(f"{self.BASE_PATH}/disconnected")
        async def remote_disconnected(raw_request: Request):
            return self._render_shell(raw_request, initial_view="disconnected")

        @app.get(f"{self.BASE_PATH}/assets/{{asset_path:path}}")
        async def remote_asset(asset_path: str, raw_request: Request):
            self._ensure_route_available(raw_request)
            asset = self._asset_map.get(str(asset_path or "").strip())
            if asset is None or not asset.is_file():
                raise HTTPException(status_code=404, detail="Asset not found")
            return FileResponse(asset)

        @app.post(f"{self.BASE_PATH}/api/login")
        async def remote_login(payload: RemoteLoginRequest, raw_request: Request):
            self._ensure_route_available(raw_request)
            if not self._needs_auth():
                return {
                    "authenticated": True,
                    "needs_auth": False,
                    "token": None,
                    "expires_at": None,
                }

            current_password = self._get_password()
            provided_password = str(payload.password or "")
            if not secrets.compare_digest(current_password, provided_password):
                raise HTTPException(status_code=401, detail="Invalid password")

            session = self._session_store.issue_session(current_password)
            return self._build_session_response(session)

        @app.get(f"{self.BASE_PATH}/api/session")
        async def remote_session(raw_request: Request):
            session = self._authenticate_remote_request(raw_request)
            return self._build_session_response(session)

        @app.get(f"{self.BASE_PATH}/api/state")
        async def remote_state(raw_request: Request):
            self._authenticate_remote_request(raw_request)
            return self._build_remote_state()

        @app.post(f"{self.BASE_PATH}/api/action/{{action_name}}")
        async def remote_action(
            action_name: str,
            payload: RemoteActionRequest,
            raw_request: Request,
        ):
            self._authenticate_remote_request(raw_request)
            action = str(action_name or "").strip().lower()
            state = self._build_remote_state()
            if not state.get("running"):
                raise HTTPException(status_code=409, detail="Services are not running")
            if state.get("busy"):
                raise HTTPException(status_code=409, detail="Services are busy")

            action_coro: Callable[[], Awaitable[None]]
            if action == "stop":
                action_coro = self._actions.stop
            elif action == "restart":
                action_coro = self._actions.restart
            elif action == "switch-account":
                if not state.get("can_switch_account"):
                    raise HTTPException(
                        status_code=409,
                        detail="Switch Account is not currently available",
                    )
                action_coro = self._actions.switch_account
            elif action == "hotswap":
                provider = DriverProvider.from_setting(payload.provider)
                if provider is None:
                    raise HTTPException(status_code=400, detail="Invalid provider")

                allowed_targets = {
                    str(item.get("name") or "")
                    for item in (state.get("hotswap_targets") or [])
                    if isinstance(item, dict)
                }
                if provider.value not in allowed_targets:
                    raise HTTPException(status_code=400, detail="Provider is unavailable")

                action_coro = lambda provider_name=provider.value: self._actions.hotswap(
                    provider_name
                )
            elif action == "switch-model":
                desired_model = str(payload.model or "").strip()
                if not desired_model:
                    raise HTTPException(status_code=400, detail="Invalid model")

                model_switch = state.get("model_switch") or {}
                if not bool(model_switch.get("supported")):
                    raise HTTPException(
                        status_code=409,
                        detail="Switch Models is not available for the current provider",
                    )

                allowed_models = {
                    str(item.get("name") or "")
                    for item in (model_switch.get("options") or [])
                    if isinstance(item, dict)
                }
                if desired_model not in allowed_models:
                    raise HTTPException(status_code=400, detail="Model is unavailable")

                try:
                    await self._actions.switch_model(desired_model)
                except Exception as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc

                return {
                    "ok": True,
                    "disconnect": False,
                    "action": action,
                    "remote_state": self._build_remote_state(),
                }
            else:
                raise HTTPException(status_code=404, detail="Unknown action")

            asyncio.create_task(self._run_deferred_action(action, action_coro))
            return {
                "ok": True,
                "disconnect": True,
                "action": action,
            }

        @app.get(f"{self.BASE_PATH}/api/logs/stream")
        async def remote_logs_stream(raw_request: Request):
            self._authenticate_remote_request(raw_request)
            queue: asyncio.Queue = asyncio.Queue()
            history = list(self._log_history)
            self._log_subscribers.add(queue)
            return StreamingResponse(
                self._log_stream(queue, history, raw_request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-store",
                    "Connection": "keep-alive",
                },
            )

    def _render_shell(self, raw_request: Request, *, initial_view: str) -> HTMLResponse:
        self._ensure_route_available(raw_request)
        template = self._template_env.get_template("shell.html")
        asset_urls = self._build_template_assets()
        initial_state = {
            "needs_auth": self._needs_auth(),
            "initial_view": str(initial_view or "home"),
            "remote_state": self._build_remote_state(),
        }
        html = template.render(
            base_path=self.BASE_PATH,
            base_path_json=json.dumps(self.BASE_PATH, ensure_ascii=True),
            initial_state_json=json.dumps(
                initial_state,
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            asset_urls=asset_urls,
            asset_urls_json=json.dumps(
                asset_urls,
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        )
        response = HTMLResponse(html)
        response.headers["Cache-Control"] = "no-store"
        return response

    def _build_template_assets(self) -> dict[str, Any]:
        provider_assets: dict[str, str] = {}
        for provider_name in provider_options():
            provider = DriverProvider.from_setting(provider_name)
            provider_key = provider.key if provider is not None else provider_name.lower().replace(" ", "_")
            provider_assets[provider_name] = self.asset_url(f"providers/{provider_key}.svg")
        return {
            "logo_url": self.asset_url("brand/newlogo-nobg.png"),
            "styles": {
                "shell": self.asset_url("styles/shell.css"),
            },
            "scripts": {
                "shell": self.asset_url("scripts/shell.js"),
            },
            "fonts": {
                "regular": self.asset_url("fonts/Blinker-Regular.ttf"),
                "semibold": self.asset_url("fonts/Blinker-SemiBold.ttf"),
                "bold": self.asset_url("fonts/Blinker-Bold.ttf"),
                "extrabold": self.asset_url("fonts/Blinker-ExtraBold.ttf"),
            },
            "icons": {
                "check": self.asset_url("icons/check.svg"),
                "chevron_down": self.asset_url("icons/chevron-down.svg"),
                "chevron_right": self.asset_url("icons/chevron-right.svg"),
                "stop": self.asset_url("icons/square.svg"),
                "terminal": self.asset_url("icons/terminal.svg"),
                "brain": self.asset_url("icons/brain.svg"),
            },
            "providers": provider_assets,
        }

    def asset_url(self, asset_path: str) -> str:
        return f"{self.BASE_PATH}/assets/{asset_path}"

    def _ensure_route_available(self, raw_request: Request) -> None:
        if not self.is_enabled():
            raise HTTPException(status_code=404, detail="Remote Control is disabled")
        self._enforce_ip_whitelist(raw_request)

    def _authenticate_remote_request(self, raw_request: Request) -> dict[str, Any] | None:
        self._ensure_route_available(raw_request)
        if not self._needs_auth():
            self._session_store.sync_password(self._get_password())
            return None

        token = self._read_bearer_token(raw_request)
        if not token:
            raise HTTPException(status_code=401, detail="Missing remote-control token")

        session = self._session_store.validate_token(token, self._get_password())
        if session is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        return session

    @staticmethod
    def _read_bearer_token(raw_request: Request) -> str:
        auth_header = str(raw_request.headers.get("Authorization") or "")
        if not auth_header.lower().startswith("bearer "):
            return ""
        return auth_header.split(" ", 1)[1].strip()

    def is_enabled(self) -> bool:
        return bool(self.config_manager.get_setting("experimental", "enable_remote_control"))

    def _get_password(self) -> str:
        value = self.config_manager.get_setting(
            "experimental", "remote_control_password"
        )
        return str(value or "")

    def _needs_auth(self) -> bool:
        return self._get_password() != ""

    def _build_session_response(
        self,
        session: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self._needs_auth():
            return {
                "authenticated": True,
                "needs_auth": False,
                "token": None,
                "expires_at": None,
                "ttl_seconds": None,
            }

        if session is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        return {
            "authenticated": True,
            "needs_auth": True,
            "token": session.get("token"),
            "expires_at": session.get("expires_at"),
            "ttl_seconds": REMOTE_SESSION_TTL_SECONDS,
        }

    def _build_remote_state(self) -> dict[str, Any]:
        raw_state = self._actions.get_state() or {}
        current_provider = DriverProvider.from_setting(raw_state.get("current_provider"))
        provider_name = current_provider.value if current_provider else DriverProvider.DEEPSEEK.value

        targets = []
        raw_targets = raw_state.get("hotswap_targets")
        if not isinstance(raw_targets, list):
            raw_targets = [name for name in provider_options() if name != provider_name]

        for raw_target in raw_targets:
            target_provider = DriverProvider.from_setting(raw_target)
            if target_provider is None or target_provider.value == provider_name:
                continue
            targets.append(
                {
                    "name": target_provider.value,
                    "icon_url": self.asset_url(f"providers/{target_provider.key}.svg"),
                }
            )

        model_switch_provider = current_provider or DriverProvider.DEEPSEEK
        current_model = str(raw_state.get("model_switch_current_model") or "").strip()
        model_options: list[dict[str, Any]] = []
        raw_model_options = raw_state.get("model_switch_options")
        if isinstance(raw_model_options, list):
            for raw_option in raw_model_options:
                option_name = str(raw_option or "").strip()
                if not option_name:
                    continue
                model_options.append(
                    {
                        "name": option_name,
                        "icon_url": self.asset_url(
                            f"providers/{model_switch_provider.key}.svg"
                        ),
                    }
                )

        return {
            "running": bool(raw_state.get("running", True)),
            "busy": bool(raw_state.get("busy", False)),
            "can_switch_account": bool(raw_state.get("can_switch_account", False)),
            "current_provider": provider_name,
            "hotswap_targets": targets,
            "model_switch": {
                "supported": bool(raw_state.get("model_switch_supported", False)),
                "current_model": current_model,
                "options": model_options,
            },
        }

    async def _run_deferred_action(
        self,
        action_name: str,
        action_coro: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            await asyncio.sleep(0.15)
            await action_coro()
        except Exception as exc:
            Logger.error(f"Remote control action '{action_name}' failed: {exc}")

    def _handle_log_message(self, level: LogLevel, message: str) -> None:
        event = {
            "level": level.value,
            "message": str(message or ""),
        }
        try:
            self._loop.call_soon_threadsafe(self._broadcast_log_event, event)
        except RuntimeError:
            pass

    def _broadcast_log_event(self, event: dict[str, Any]) -> None:
        self._log_history.append(dict(event))
        for queue in list(self._log_subscribers):
            try:
                queue.put_nowait(dict(event))
            except Exception:
                self._log_subscribers.discard(queue)

    async def _log_stream(
        self,
        queue: asyncio.Queue,
        history: list[dict[str, Any]],
        raw_request: Request,
    ):
        try:
            yield self._encode_sse_event("connected", {"ok": True})
            for entry in history:
                yield self._encode_sse_event("log", entry)

            while True:
                if await raw_request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    break
                yield self._encode_sse_event("log", event)
        except asyncio.CancelledError:
            raise
        finally:
            self._log_subscribers.discard(queue)

    @staticmethod
    def _encode_sse_event(event_name: str, payload: dict[str, Any]) -> str:
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        return f"event: {event_name}\ndata: {data}\n\n"
