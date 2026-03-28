from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from config.location import get_local_anchor_dir
from config.schema import SCHEMA, SettingField, SettingType
from drivers.providers import DriverProvider, provider_options
from utils.ip_utils import normalize_ip_list


LOADOUTS_FILENAME = "loadouts.json"
LOADOUT_META_KEY = "Meta"
LOADOUT_META_COMMENT_KEY = "_Comment"

LOADOUT_BEHAVIOR_CATEGORY_BY_PROVIDER: dict[DriverProvider, str] = {
    DriverProvider.DEEPSEEK: "deepseek_behavior",
    DriverProvider.GLM_CHAT: "glm_behavior",
    DriverProvider.MOONSHOT: "moonshot_behavior",
    DriverProvider.QWEN_LM: "qwen_behavior",
    DriverProvider.AI_STUDIO: "aistudio_behavior",
}


@dataclass(frozen=True)
class LoadoutDefinition:
    name: str
    provider: DriverProvider
    settings: dict[str, Any]
    meta_comment: str | None = None


class LoadoutValidationError(ValueError):
    """Raised when loadouts.json is missing or contains invalid data."""


def get_loadouts_path() -> Path:
    return get_local_anchor_dir().resolve() / LOADOUTS_FILENAME


def _iter_persisted_fields(fields: Iterable[SettingField]) -> Iterable[SettingField]:
    for field in fields:
        if field.type == SettingType.ROW and field.sub_fields:
            yield from _iter_persisted_fields(field.sub_fields)
            continue

        if getattr(field, "transient", False):
            continue

        if field.type in {
            SettingType.BUTTON,
            SettingType.DESCRIPTION,
            SettingType.DIVIDER,
            SettingType.HINT,
            SettingType.REDIRECT,
            SettingType.ROW,
        }:
            continue

        yield field


def _get_category_fields(category_key: str) -> dict[str, SettingField]:
    for category in SCHEMA:
        if category.key != category_key:
            continue
        return {field.key: field for field in _iter_persisted_fields(category.fields)}
    return {}


def get_behavior_category_for_provider(provider: DriverProvider) -> str | None:
    return LOADOUT_BEHAVIOR_CATEGORY_BY_PROVIDER.get(provider)


def get_loadout_field_defs(provider: DriverProvider) -> dict[str, SettingField]:
    fields: dict[str, SettingField] = {}
    fields.update(_get_category_fields("formatting"))

    behavior_category = get_behavior_category_for_provider(provider)
    if behavior_category:
        fields.update(_get_category_fields(behavior_category))
    return fields


def _normalize_provider(value: Any) -> DriverProvider | None:
    return DriverProvider.from_setting(str(value or "").strip())


def _clone_default(value: Any) -> Any:
    return copy.deepcopy(value)


def build_template_payload() -> list[dict[str, Any]]:
    provider_names = ", ".join(provider_options())
    payload: list[dict[str, Any]] = []

    for provider in LOADOUT_BEHAVIOR_CATEGORY_BY_PROVIDER:
        item: dict[str, Any] = {
            LOADOUT_META_KEY: {
                "Name": "Template",
                "Provider": provider.value,
                LOADOUT_META_COMMENT_KEY: f"Valid providers: {provider_names}",
            }
        }
        for field_key, field in get_loadout_field_defs(provider).items():
            item[field_key] = _clone_default(field.default)
        payload.append(item)

    return payload


def render_template_json() -> str:
    return json.dumps(build_template_payload(), indent=2, ensure_ascii=True) + "\n"


def write_template_file(path: Path, *, overwrite: bool = False) -> None:
    target = Path(path).resolve()
    if target.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {target}")
    target.write_text(render_template_json(), encoding="utf-8")


def _validation_prefix(index: int, provider: DriverProvider | None = None, name: str | None = None) -> str:
    parts = [f"Loadout #{index}"]
    if provider is not None:
        parts.append(provider.value)
    if name:
        parts.append(name)
    return " / ".join(parts)


def _validate_meta(index: int, item: dict[str, Any]) -> tuple[DriverProvider, str, str | None]:
    meta = item.get(LOADOUT_META_KEY)
    if not isinstance(meta, dict):
        raise LoadoutValidationError(f"Loadout #{index}: missing or invalid '{LOADOUT_META_KEY}' object.")

    allowed_meta_keys = {"Name", "Provider", LOADOUT_META_COMMENT_KEY}
    extra_meta_keys = sorted(set(meta.keys()) - allowed_meta_keys)
    if extra_meta_keys:
        raise LoadoutValidationError(
            f"Loadout #{index}: unknown Meta field(s): {', '.join(extra_meta_keys)}."
        )

    raw_name = meta.get("Name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise LoadoutValidationError(f"Loadout #{index}: Meta.Name must be a non-empty string.")
    name = raw_name.strip()

    raw_provider = meta.get("Provider")
    provider = _normalize_provider(raw_provider)
    if provider is None:
        valid_names = ", ".join(provider_options())
        raise LoadoutValidationError(
            f"{_validation_prefix(index, name=name)}: Meta.Provider must be one of: {valid_names}."
        )

    raw_comment = meta.get(LOADOUT_META_COMMENT_KEY)
    if (raw_comment is not None) and (not isinstance(raw_comment, str)):
        raise LoadoutValidationError(
            f"{_validation_prefix(index, provider, name)}: Meta.{LOADOUT_META_COMMENT_KEY} must be a string."
        )

    return provider, name, raw_comment


def _validate_field_type(prefix: str, field: SettingField, value: Any) -> Any:
    if value is None:
        if getattr(field, "nullable", False):
            return None
        raise LoadoutValidationError(f"{prefix}: '{field.key}' cannot be null.")

    if field.type == SettingType.BOOLEAN:
        if not isinstance(value, bool):
            raise LoadoutValidationError(f"{prefix}: '{field.key}' must be true or false.")
        return value

    if field.type == SettingType.INTEGER:
        if isinstance(value, bool) or (not isinstance(value, int)):
            raise LoadoutValidationError(f"{prefix}: '{field.key}' must be an integer.")
        return value

    if field.type in {
        SettingType.STRING,
        SettingType.PASSWORD,
        SettingType.TEXTAREA,
        SettingType.DIRECTORY,
    }:
        if not isinstance(value, str):
            raise LoadoutValidationError(f"{prefix}: '{field.key}' must be a string.")
        return value

    if field.type == SettingType.DROPDOWN:
        if not isinstance(value, str):
            raise LoadoutValidationError(f"{prefix}: '{field.key}' must be a string.")
        options = [str(option) for option in (field.options or [])]
        if options and value not in options:
            raise LoadoutValidationError(
                f"{prefix}: '{field.key}' must be one of: {', '.join(options)}."
            )
        return value

    if field.type == SettingType.INPUT_PAIR:
        if not isinstance(value, list):
            raise LoadoutValidationError(f"{prefix}: '{field.key}' must be a list of [name, value] pairs.")
        normalized_pairs: list[list[str]] = []
        for pair_index, pair in enumerate(value, start=1):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise LoadoutValidationError(
                    f"{prefix}: '{field.key}' pair #{pair_index} must contain exactly 2 items."
                )
            left, right = pair
            if not isinstance(left, str) or not isinstance(right, str):
                raise LoadoutValidationError(
                    f"{prefix}: '{field.key}' pair #{pair_index} must contain only strings."
                )
            normalized_pairs.append([left, right])
        return normalized_pairs

    if field.type == SettingType.INPUT_LIST:
        if not isinstance(value, list):
            raise LoadoutValidationError(f"{prefix}: '{field.key}' must be a list.")
        if any(not isinstance(item, str) for item in value):
            raise LoadoutValidationError(f"{prefix}: '{field.key}' must contain only strings.")
        return list(value)

    raise LoadoutValidationError(
        f"{prefix}: '{field.key}' uses unsupported field type '{field.type.value}'."
    )


def _validate_field_value(prefix: str, field: SettingField, value: Any) -> Any:
    normalized = _validate_field_type(prefix, field, value)

    try:
        if field.type == SettingType.INPUT_LIST and field.validator:
            normalize_ip_list(normalized)
        elif field.validator:
            field.validator(normalized)
    except ValueError as exc:
        raise LoadoutValidationError(f"{prefix}: '{field.key}' is invalid: {exc}") from exc

    return normalized


def load_and_validate_file(path: Path) -> list[LoadoutDefinition]:
    target = Path(path).resolve()
    if not target.exists():
        raise LoadoutValidationError(
            f"Loadouts are enabled, but '{target}' does not exist. Create the template from Settings first."
        )

    try:
        raw_text = target.read_text(encoding="utf-8")
    except Exception as exc:
        raise LoadoutValidationError(f"Failed to read '{target}': {exc}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LoadoutValidationError(
            f"Invalid JSON in '{target.name}' at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(payload, list):
        raise LoadoutValidationError(f"'{target.name}' must contain a top-level JSON list.")

    seen_names: set[tuple[DriverProvider, str]] = set()
    loadouts: list[LoadoutDefinition] = []

    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise LoadoutValidationError(f"Loadout #{index}: each entry must be a JSON object.")

        provider, name, meta_comment = _validate_meta(index, item)
        prefix = _validation_prefix(index, provider, name)
        field_defs = get_loadout_field_defs(provider)

        actual_keys = set(item.keys()) - {LOADOUT_META_KEY}
        expected_keys = set(field_defs.keys())

        missing_keys = sorted(expected_keys - actual_keys)
        extra_keys = sorted(actual_keys - expected_keys)
        if missing_keys:
            raise LoadoutValidationError(f"{prefix}: missing field(s): {', '.join(missing_keys)}.")
        if extra_keys:
            raise LoadoutValidationError(f"{prefix}: unknown field(s): {', '.join(extra_keys)}.")

        dedupe_key = (provider, name.casefold())
        if dedupe_key in seen_names:
            raise LoadoutValidationError(
                f"{prefix}: duplicate Meta.Name for provider '{provider.value}'. Names must be unique per provider."
            )
        seen_names.add(dedupe_key)

        settings: dict[str, Any] = {}
        for field_key, field in field_defs.items():
            settings[field_key] = _validate_field_value(prefix, field, item.get(field_key))

        loadouts.append(
            LoadoutDefinition(
                name=name,
                provider=provider,
                settings=settings,
                meta_comment=meta_comment,
            )
        )

    return loadouts


def group_by_provider(loadouts: Iterable[LoadoutDefinition]) -> dict[DriverProvider, list[LoadoutDefinition]]:
    grouped: dict[DriverProvider, list[LoadoutDefinition]] = {}
    for loadout in loadouts:
        grouped.setdefault(loadout.provider, []).append(loadout)
    return grouped
