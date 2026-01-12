from typing import Dict, Any

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
                
                # Map old presets to new defaults
                if preset == "Classic":
                    formatting["formatting_preset"] = "Classic - Name"
                elif preset == "XML-Like":
                    formatting["formatting_preset"] = "XML-Like - Name"
                elif preset == "Divided":
                    formatting["formatting_preset"] = "Divided - Name"

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
                    
        # Future migrations will be added here
        # e.g. v1 to v2
        
        return settings
