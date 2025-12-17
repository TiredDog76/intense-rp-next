import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
from config.manager import ConfigManager
from utils.logger import Logger

class V1Migrator:
    def __init__(self, v2_config_manager: ConfigManager):
        self.v2_manager = v2_config_manager

    def migrate(self, v1_dir: str) -> tuple[bool, str]:
        """
        Migrate V1 settings to V2.
        Returns (success, message).
        """
        v1_path = Path(v1_dir)
        save_path = v1_path / "save"
        
        if not save_path.exists():
            return False, "Could not find 'save' directory in the selected folder."
            
        config_enc = save_path / "config.enc"
        secret_key = save_path / "secret.key"
        
        if not config_enc.exists() or not secret_key.exists():
            return False, "Missing config.enc or secret.key in 'save' directory."
            
        try:
            # Decrypt V1 Config
            with open(secret_key, "rb") as f:
                key = f.read()
            
            cipher = Fernet(key)
            
            with open(config_enc, "rb") as f:
                encrypted_data = f.read()
                
            decrypted_data = cipher.decrypt(encrypted_data)
            v1_config = json.loads(decrypted_data.decode("utf-8"))
            
            # Perform Migration
            self._map_settings(v1_config)
            
            # Handle Templates (User template -> Formatting template)
            # Try to load custom_user_template.enc if it exists, as V1 stored it there
            user_tmpl_enc = save_path / "custom_user_template.enc"
            if user_tmpl_enc.exists():
                try:
                    with open(user_tmpl_enc, "rb") as f:
                        enc_tmpl = f.read()
                    dec_tmpl = cipher.decrypt(enc_tmpl).decode("utf-8")
                    self.v2_manager.set_setting("formatting", "formatting_template", dec_tmpl)
                    self.v2_manager.set_setting("formatting", "formatting_preset", "Custom")
                except Exception as e:
                    Logger.warning(f"Failed to migrate custom user template: {e}")
            
            self.v2_manager.save_settings()
            return True, "Migration completed successfully! Some settings may need manual review."
            
        except Exception as e:
            Logger.error(f"Migration failed: {e}")
            return False, f"Migration failed: {e}"

    def _map_settings(self, v1: dict):
        """Map V1 keys to V2 keys."""
        
        # Helper to safely get nested keys
        def get_v1(path, default=None):
            keys = path.split('.')
            val = v1
            for k in keys:
                if isinstance(val, dict) and k in val:
                    val = val[k]
                else:
                    return default
            return val

        # Providers & Credentials
        if email := get_v1("models.deepseek.email"):
            self.v2_manager.set_setting("providers_credentials", "deepseek_email", email)
        if pwd := get_v1("models.deepseek.password"):
            self.v2_manager.set_setting("providers_credentials", "deepseek_password", pwd)
        if auto_login := get_v1("models.deepseek.auto_login"):
            self.v2_manager.set_setting("providers_credentials", "auto_login", bool(auto_login))

        # DeepSeek Behavior
        if dt := get_v1("models.deepseek.deepthink"):
            self.v2_manager.set_setting("deepseek_behavior", "enable_deepthink", bool(dt))
        if st := get_v1("models.deepseek.send_thoughts"):
            self.v2_manager.set_setting("deepseek_behavior", "send_deepthink", bool(st))
        if search := get_v1("models.deepseek.search"):
            self.v2_manager.set_setting("deepseek_behavior", "enable_search", bool(search))
        if tf := get_v1("models.deepseek.text_file"):
            self.v2_manager.set_setting("deepseek_behavior", "send_as_text_file", bool(tf))
        if clean := get_v1("models.deepseek.clean_regeneration"):
            self.v2_manager.set_setting("deepseek_behavior", "clean_regeneration", bool(clean))

        # Console Settings
        if font_size := get_v1("console.font_size"):
            try:
                self.v2_manager.set_setting("console_settings", "font_size", int(font_size))
            except:
                pass
        
        if palette := get_v1("console.color_palette"):
            self.v2_manager.set_setting("console_settings", "color_palette", palette)
            
        if dump_dir := get_v1("console.dump_directory"):
            self.v2_manager.set_setting("console_dumping", "condump_directory", dump_dir)

        # Formatting
        preset_map = {
            "Classic (Name)": "Classic - Name",
            "Classic (Role)": "Classic - Role",
            "Wrapped (Name)": "XML-Like - Name",
            "Wrapped (Role)": "XML-Like - Role",
            "Divided (Name)": "Divided - Name", 
            "Divided (Role)": "Divided - Role",
            "Custom": "Custom"
        }
        if preset := get_v1("formatting.preset"):
            if preset in preset_map:
                self.v2_manager.set_setting("formatting", "formatting_preset", preset_map[preset])

        # We rely on the template file migration for Custom.
        
        # Injection
        if prompt := get_v1("injection.system_prompt"):
            self.v2_manager.set_setting("formatting", "injection_content", prompt)
            
        # Logging
        if log_enabled := get_v1("logging.enabled"):
            self.v2_manager.set_setting("logfiles", "enable_logfiles", bool(log_enabled))
        if max_files := get_v1("logging.max_files"):
            self.v2_manager.set_setting("logfiles", "max_files", int(max_files))
        
        # Log size (V1 bytes -> V2 Value + Unit)
        if max_size_bytes := get_v1("logging.max_file_size"):
            try:
                bytes_val = int(max_size_bytes)
                if bytes_val >= 1024 * 1024 * 1024:
                    self.v2_manager.set_setting("logfiles", "size_val", int(bytes_val / (1024*1024*1024)))
                    self.v2_manager.set_setting("logfiles", "size_unit", "GB")
                elif bytes_val >= 1024 * 1024:
                    self.v2_manager.set_setting("logfiles", "size_val", int(bytes_val / (1024*1024)))
                    self.v2_manager.set_setting("logfiles", "size_unit", "MB")
                else:
                    self.v2_manager.set_setting("logfiles", "size_val", int(bytes_val / 1024))
                    self.v2_manager.set_setting("logfiles", "size_unit", "KB")
            except:
                pass

        # Network
        if port := get_v1("api.port"):
            try:
                self.v2_manager.set_setting("network_settings", "port", int(port))
            except:
                pass
        
        # API Keys
        # V1: {"name": "key"} -> V2: [{"key": "name", "value": "key"}]
        if api_keys := get_v1("security.api_keys"):
            if isinstance(api_keys, dict):
                v2_keys = [{"key": k, "value": v} for k, v in api_keys.items()]
                self.v2_manager.set_setting("network_settings", "api_keys", v2_keys)
                self.v2_manager.set_setting("network_settings", "use_api_keys", True)

        # Persistent Cookies
        if persist := get_v1("browser_persistent_cookies"):
            self.v2_manager.set_setting("system_settings", "persistent_sessions", bool(persist))
