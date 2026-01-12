import json
from pathlib import Path
from typing import Any, Dict
from cryptography.fernet import Fernet
from .schema import SCHEMA, SettingType
from .migrator import SettingsMigrator
from .location import get_active_config_dir
from utils.logger import Logger

class ConfigManager:
    def __init__(self, config_dir: str | Path | None = None):
        self.config_dir = Path(config_dir) if config_dir is not None else get_active_config_dir()
        self.config_dir = self.config_dir.resolve()
        self.settings_file = self.config_dir / "settings.json.enc"
        self.key_file = self.config_dir / "settings.key"
        self.settings: Dict[str, Any] = {}
        
        self._ensure_dir()
        self._load_key()
        self.load_settings()

    def reload_from_disk(self) -> None:
        """
        Reload the encryption key and settings data from disk.

        This is useful after external changes to the config directory contents
        (e.g., restoring settings from a backup zip).
        """
        self.config_dir = self.config_dir.resolve()
        self.settings_file = self.config_dir / "settings.json.enc"
        self.key_file = self.config_dir / "settings.key"
        self._ensure_dir()
        self._load_key()
        self.load_settings()

    def _ensure_dir(self):
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load_key(self):
        if self.key_file.exists():
            with open(self.key_file, "rb") as f:
                self.key = f.read()
        else:
            self.key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(self.key)
        self.cipher = Fernet(self.key)

    def load_settings(self):
        if not self.settings_file.exists():
            self._init_default_settings()
            return

        try:
            with open(self.settings_file, "rb") as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            self.settings = json.loads(decrypted_data.decode("utf-8"))
            
            # Migrate settings
            self.settings = SettingsMigrator.migrate(self.settings)
            
            # Validate/Merge with schema to ensure all fields exist
            self._merge_defaults()
            
        except Exception as e:
            Logger.error(f"Error loading settings: {e}")
            self._init_default_settings()

    def _init_default_settings(self):
        self.settings = {}
        for category in SCHEMA:
            if category.key not in self.settings:
                self.settings[category.key] = {}
            for field in category.fields:
                self.settings[category.key][field.key] = field.default
        self.save_settings()

    def _merge_defaults(self):
        updated = False
        for category in SCHEMA:
            if category.key not in self.settings:
                self.settings[category.key] = {}
                updated = True
            for field in category.fields:
                if field.key not in self.settings[category.key]:
                    self.settings[category.key][field.key] = field.default
                    updated = True
        if updated:
            self.save_settings()

    def save_settings(self):
        try:
            json_data = json.dumps(self.settings).encode("utf-8")
            encrypted_data = self.cipher.encrypt(json_data)
            
            with open(self.settings_file, "wb") as f:
                f.write(encrypted_data)
        except Exception as e:
            Logger.error(f"Error saving settings: {e}")

    def get_setting(self, category_key: str, field_key: str) -> Any:
        return self.settings.get(category_key, {}).get(field_key)

    def _iter_schema_fields(self, fields):
        for field in fields:
            yield field
            if field.type == SettingType.ROW and field.sub_fields:
                yield from self._iter_schema_fields(field.sub_fields)

    def _get_schema_field(self, category_key: str, field_key: str):
        for category in SCHEMA:
            if category.key != category_key:
                continue
            for field in self._iter_schema_fields(category.fields):
                if field.key == field_key:
                    return field
        return None

    def get_effective_setting(self, category_key: str, field_key: str) -> Any:
        """
        Returns the effective value for a setting, applying schema-driven rules
        such as forced values when dependencies are unmet.
        """
        value = self.get_setting(category_key, field_key)
        field_def = self._get_schema_field(category_key, field_key)
        if not field_def:
            return value

        depends = getattr(field_def, "depends", None)
        if not depends:
            return value

        def _get_setting_value(full_key: str) -> Any:
            try:
                dep_category, dep_field = full_key.split(".", 1)
            except ValueError:
                return None
            return self.get_setting(dep_category, dep_field)

        def _eval_dep_expr(expr: str) -> bool:
            parts = [part.strip() for part in str(expr).split("&&")]
            for part in parts:
                if not part:
                    continue

                if "==" in part:
                    left, right = part.split("==", 1)
                    dep_key = left.strip()
                    expected = right.strip()
                    value = _get_setting_value(dep_key)
                    if isinstance(value, bool):
                        expected_bool = expected.lower() in {"1", "true", "yes", "on"}
                        if value != expected_bool:
                            return False
                    else:
                        if str(value or "").strip() != expected:
                            return False
                    continue

                if "!=" in part:
                    left, right = part.split("!=", 1)
                    dep_key = left.strip()
                    expected = right.strip()
                    value = _get_setting_value(dep_key)
                    if isinstance(value, bool):
                        expected_bool = expected.lower() in {"1", "true", "yes", "on"}
                        if value == expected_bool:
                            return False
                    else:
                        if str(value or "").strip() == expected:
                            return False
                    continue

                value = _get_setting_value(part)
                if not value:
                    return False

            return True

        is_met = _eval_dep_expr(depends)
        forced_value = getattr(field_def, "force_when_dep_unmet", None)
        if (not is_met) and (forced_value is not None):
            return forced_value

        return value

    def set_setting(self, category_key: str, field_key: str, value: Any):
        if category_key not in self.settings:
            self.settings[category_key] = {}
        self.settings[category_key][field_key] = value
