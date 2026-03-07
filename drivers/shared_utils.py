from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union

from utils.logger import Logger


COMMON_REQUEST_MACRO_ACTIONS: Dict[str, tuple[str, bool]] = {
    # Thinking
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

_CLEAN_REGEN_STATE_KEYS = (
    "deepthink_enabled",
    "search_enabled",
    "send_as_text_file",
)
_MACRO_PATTERN = re.compile(r"\[\[\s*([a-zA-Z0-9_-]+)\s*\]\]")
_IR2_PATTERN = re.compile(r"\[\[IR2u\]\](.*?)\[\[/IR2u\]\]-\[\[IR2a\]\](.*?)\[\[/IR2a\]\]")
_CLASSIC_PATTERN = re.compile(r'DATA1: "(.*?)"\s*DATA2: "(.*?)"')


def clear_clean_regeneration_cache(
    cache_manager: Any,
    message_cache_key: str,
    state_cache_key: str,
) -> None:
    cache_manager.clear_cache(message_cache_key)
    cache_manager.clear_cache(state_cache_key)


def extract_macro_overrides(
    text: str,
    macro_actions: Dict[str, tuple[str, bool]] | None = None,
) -> tuple[str, Dict[str, bool]]:
    if not text:
        return text, {}

    actions = dict(COMMON_REQUEST_MACRO_ACTIONS)
    if macro_actions:
        actions.update(macro_actions)

    overrides: Dict[str, bool] = {}

    def _replace_macro(match: re.Match[str]) -> str:
        macro = (match.group(1) or "").strip().lower()
        action = actions.get(macro)
        if not action:
            return match.group(0)

        key, value = action
        overrides[key] = bool(value)
        return ""

    cleaned = _MACRO_PATTERN.sub(_replace_macro, text)
    return cleaned, overrides


def strip_macros_from_messages(
    messages: List[Any],
    macro_actions: Dict[str, tuple[str, bool]] | None = None,
) -> tuple[List[Any], Dict[str, bool]]:
    last_user_index = None
    for idx in range(len(messages) - 1, -1, -1):
        role = _coerce_role(messages[idx])
        if role.strip().lower() == "user":
            last_user_index = idx
            break

    if last_user_index is None:
        return messages, {}

    last_msg = messages[last_user_index]
    content = _get_message_field(last_msg, "content", "")
    if not isinstance(content, str):
        return messages, {}

    cleaned_content, overrides = extract_macro_overrides(content, macro_actions=macro_actions)
    if not overrides:
        return messages, {}

    cleaned_messages = list(messages)
    if isinstance(last_msg, dict):
        updated = dict(last_msg)
        updated["content"] = cleaned_content
        cleaned_messages[last_user_index] = updated
        return cleaned_messages, overrides

    role_value = _get_message_field(last_msg, "role", "")
    name_value = _get_message_field(last_msg, "name")
    updated = {"role": role_value, "content": cleaned_content}
    if name_value is not None:
        updated["name"] = name_value
    cleaned_messages[last_user_index] = updated
    return cleaned_messages, overrides


def read_clean_regeneration_state(
    cache_manager: Any,
    state_cache_key: str,
    *,
    log_label: str = "Clean Regeneration",
) -> Optional[Dict[str, bool]]:
    raw = cache_manager.read_cache(state_cache_key)
    if raw is None:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        Logger.warning(f"{log_label}: Cached state is invalid JSON, ignoring.")
        return None

    if not isinstance(data, dict):
        return None

    if not all(key in data for key in _CLEAN_REGEN_STATE_KEYS):
        return None

    return {
        "deepthink_enabled": bool(data.get("deepthink_enabled")),
        "search_enabled": bool(data.get("search_enabled")),
        "send_as_text_file": bool(data.get("send_as_text_file")),
    }


def write_clean_regeneration_state(
    cache_manager: Any,
    state_cache_key: str,
    state: Dict[str, bool],
) -> None:
    payload = {
        "deepthink_enabled": bool(state.get("deepthink_enabled")),
        "search_enabled": bool(state.get("search_enabled")),
        "send_as_text_file": bool(state.get("send_as_text_file")),
    }
    cache_manager.write_cache(
        state_cache_key,
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
    )


def format_messages(config_manager: Any, messages: Union[str, List[Any]]) -> str:
    apply_formatting = config_manager.get_setting("formatting", "apply_formatting")

    if not apply_formatting:
        if isinstance(messages, list):
            formatted_parts = []
            for msg in messages:
                role = _get_message_field(msg, "role", "")
                content = _get_message_field(msg, "content", "")
                formatted_parts.append(f"{role}: {content}")
            return "\n".join(formatted_parts)
        return messages

    user_name = "User"
    char_name = "Character"
    msgs_to_scan = messages if isinstance(messages, list) else []

    if config_manager.get_setting("formatting", "enable_msg_objects"):
        for msg in msgs_to_scan:
            role = _get_message_field(msg, "role", "")
            name = _get_message_name(msg)
            if name:
                if role == "user":
                    user_name = name
                elif role == "assistant":
                    char_name = name

    enable_ir2 = config_manager.get_setting("formatting", "enable_ir2")
    enable_classic = config_manager.get_setting("formatting", "enable_classic_irp")
    if enable_ir2 or enable_classic:
        for msg in msgs_to_scan:
            role = _get_message_field(msg, "role", "")
            content = _get_message_field(msg, "content", "")
            if role != "system":
                continue

            if enable_ir2:
                ir2_match = _IR2_PATTERN.search(str(content))
                if ir2_match:
                    user_name = ir2_match.group(1)
                    char_name = ir2_match.group(2)

            if enable_classic:
                classic_match = _CLASSIC_PATTERN.search(str(content))
                if classic_match:
                    char_name = classic_match.group(1)
                    user_name = classic_match.group(2)

    template = config_manager.get_setting("formatting", "formatting_template") or ""
    divider = config_manager.get_setting("formatting", "formatting_divider") or ""
    template = str(template).replace("\\n", "\n")
    divider = str(divider).replace("\\n", "\n")

    formatted_parts = []
    if isinstance(messages, list):
        use_msg_objects = bool(config_manager.get_setting("formatting", "enable_msg_objects"))
        for msg in messages:
            role_raw = _get_message_field(msg, "role", "")
            content = _get_message_field(msg, "content", "")
            msg_name = _get_message_name(msg) if use_msg_objects else None

            display_role = "System"
            display_name = "System"
            if role_raw == "user":
                display_role = "User"
                display_name = msg_name if msg_name else user_name
            elif role_raw == "assistant":
                display_role = "Character"
                display_name = msg_name if msg_name else char_name

            part = (
                str(template)
                .replace("{{name}}", str(display_name))
                .replace("{{role}}", str(display_role))
                .replace("{{content}}", str(content))
            )
            formatted_parts.append(part)
    else:
        part = (
            str(template)
            .replace("{{name}}", user_name)
            .replace("{{role}}", "User")
            .replace("{{content}}", str(messages))
        )
        formatted_parts.append(part)

    final_message = divider.join(formatted_parts)
    injection_pos = config_manager.get_setting("formatting", "injection_position")
    injection_content = config_manager.get_setting("formatting", "injection_content")
    if injection_content:
        rendered_injection = _render_injection(str(injection_content), user_name, char_name)
        if injection_pos == "Before":
            final_message = rendered_injection + "\n" + final_message
        else:
            final_message = final_message + "\n" + rendered_injection

    return final_message


def _coerce_role(message: Any) -> str:
    role = _get_message_field(message, "role", "")
    return str(role or "")


def _get_message_field(message: Any, key: str, default: Any = None) -> Any:
    try:
        value = getattr(message, key)
    except Exception:
        value = None

    if value is not None:
        return value
    if isinstance(message, dict):
        return message.get(key, default)
    return default


def _get_message_name(message: Any) -> Any:
    name_value = _get_message_field(message, "name")
    if name_value:
        return name_value
    return _get_message_field(message, "irp-next")


def _render_injection(text: str, user_name: str, char_name: str) -> str:
    rendered = "" if text is None else str(text)
    rendered = rendered.replace("{{user}}", user_name)
    rendered = rendered.replace("{{char}}", char_name)
    rendered = rendered.replace("{username}", user_name)
    rendered = rendered.replace("{asstname}", char_name)
    rendered = rendered.replace("{{username}}", user_name)
    rendered = rendered.replace("{{asstname}}", char_name)
    return rendered
