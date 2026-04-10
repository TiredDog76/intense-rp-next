from typing import Dict, Any
from config.formatting_presets import LEGACY_V2_FORMATTING_PRESET_MAP
from drivers.providers import DriverProvider


REMOVED_FIELDS = {
    ("application_settings", "paged_settings_view"),
    ("application_settings", "show_only_active_provider_behavior"),
    ("experimental", "better_model_names"),
}

GLM_MODEL_RENAMES = {
    "GLM-4.6": "GLM-5.1",
}


def migrate_glm_model_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return GLM_MODEL_RENAMES.get(value, value)


def migrate_glm_behavior_settings(raw_settings: Any) -> bool:
    if not isinstance(raw_settings, dict):
        return False

    raw_model = raw_settings.get("model")
    migrated_model = migrate_glm_model_value(raw_model)
    if migrated_model == raw_model:
        return False

    raw_settings["model"] = migrated_model
    return True


class SettingsMigrator:
    @staticmethod
    def migrate(settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrates settings from older versions to the current version.
        Modifies the settings dictionary in-place.
        """
        
        # Migration: Preset Variants (Non-Role/Name to Role/Name)
        if "formatting" in settings:
            formatting = settings["formatting"]
            if "formatting_preset" in formatting:
                preset = formatting["formatting_preset"]
                formatting["formatting_preset"] = LEGACY_V2_FORMATTING_PRESET_MAP.get(preset, preset)

        # Migration: enable_console moved from system_settings -> console_settings
        system_settings = settings.get("system_settings")
        if isinstance(system_settings, dict) and "enable_console" in system_settings:
            enable_console = system_settings.pop("enable_console")
            console_settings = settings.setdefault("console_settings", {})
            if isinstance(console_settings, dict) and "enable_console" not in console_settings:
                console_settings["enable_console"] = enable_console

        # Migration: Base Driver provider moved to providers_credentials.provider
        base_driver = settings.get("base_driver")
        if isinstance(base_driver, dict) and "provider" in base_driver:
            provider = base_driver.get("provider")
            providers_credentials = settings.setdefault("providers_credentials", {})
            if isinstance(providers_credentials, dict) and not providers_credentials.get("provider"):
                providers_credentials["provider"] = provider

        # Migration: normalize provider value to canonical enum label
        providers_credentials = settings.get("providers_credentials")
        if isinstance(providers_credentials, dict):
            raw_provider = providers_credentials.get("provider")
            providers_credentials["provider"] = DriverProvider.from_setting(raw_provider).value

        # Migration: removed GLM model labels -> current supported labels
        migrate_glm_behavior_settings(settings.get("glm_behavior"))

        loadouts_root = settings.get("loadouts")
        if isinstance(loadouts_root, dict):
            raw_definitions = loadouts_root.get("definitions")
            if isinstance(raw_definitions, list):
                for definition in raw_definitions:
                    if not isinstance(definition, dict):
                        continue
                    raw_provider = definition.get("provider")
                    if raw_provider is None:
                        continue
                    provider = DriverProvider.from_setting(str(raw_provider))
                    if provider is DriverProvider.GLM_CHAT:
                        migrate_glm_behavior_settings(definition.get("settings"))

        # Migration: account engine toggles moved from Experimental -> Providers & Credentials
        experimental = settings.get("experimental")
        if isinstance(experimental, dict):
            select_least_used = experimental.get("ece_select_least_used")
            reload_on_failure = experimental.get("ece_reauth_on_no_content")
            better_model_names = experimental.get("better_model_names")

            providers_credentials = settings.setdefault("providers_credentials", {})
            if isinstance(providers_credentials, dict):
                if "select_least_used" not in providers_credentials and select_least_used is not None:
                    providers_credentials["select_least_used"] = bool(select_least_used)
                if "reload_on_failure" not in providers_credentials and reload_on_failure is not None:
                    providers_credentials["reload_on_failure"] = bool(reload_on_failure)

            network_settings = settings.setdefault("network_settings", {})
            if isinstance(network_settings, dict):
                if "enable_umm" not in network_settings and better_model_names is not None:
                    network_settings["enable_umm"] = bool(better_model_names)

        # Migration: remove obsolete settings that no longer exist in the UI
        for category_key, field_key in REMOVED_FIELDS:
            category = settings.get(category_key)
            if isinstance(category, dict):
                category.pop(field_key, None)

        # Future migrations will be added here
        # e.g. v1 to v2
        
        return settings
