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
            def convert_v1_template_to_v2(template_text: str) -> str:
                """
                V1 templates used single-brace placeholders like:
                  {name}, {role}, {content}

                V2 templates use double-brace placeholders like:
                  {{name}}, {{role}}, {{content}}

                Only convert *single* brace placeholders (avoid touching existing
                double-brace sequences).
                """
                import re

                text = "" if template_text is None else str(template_text)
                text = re.sub(r"(?<!\{)\{name\}(?!\})", "{{name}}", text)
                text = re.sub(r"(?<!\{)\{role\}(?!\})", "{{role}}", text)
                text = re.sub(r"(?<!\{)\{content\}(?!\})", "{{content}}", text)
                return text

            def convert_v1_injection_to_v2(injection_text: str) -> str:
                """
                V1 injection templates commonly used:
                  {username}, {asstname}

                v2 supports:
                  {{user}}, {{char}}
                """
                text = "" if injection_text is None else str(injection_text)
                return (
                    text.replace("{username}", "{{user}}")
                    .replace("{asstname}", "{{char}}")
                )

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
            
            # Handle Templates (V1 User/Character templates -> V2 single template)
            user_tmpl_enc = save_path / "custom_user_template.enc"
            char_tmpl_enc = save_path / "custom_char_template.enc"

            user_template = None
            char_template = None

            if user_tmpl_enc.exists():
                try:
                    with open(user_tmpl_enc, "rb") as f:
                        enc_tmpl = f.read()
                    user_template = cipher.decrypt(enc_tmpl).decode("utf-8")
                except Exception as e:
                    Logger.warning(f"Failed to migrate custom user template: {e}")

            if char_tmpl_enc.exists():
                try:
                    with open(char_tmpl_enc, "rb") as f:
                        enc_tmpl = f.read()
                    char_template = cipher.decrypt(enc_tmpl).decode("utf-8")
                except Exception as e:
                    Logger.warning(f"Failed to migrate custom character template: {e}")

            chosen_template = user_template if user_template else char_template
            if chosen_template:
                if user_template and char_template and user_template != char_template:
                    Logger.warning(
                        "V1 user/character templates differ; v2 supports a single template. "
                        "Imported the user template; please review Formatting in v2."
                    )

                self.v2_manager.set_setting(
                    "formatting",
                    "formatting_template",
                    convert_v1_template_to_v2(chosen_template),
                )
                self.v2_manager.set_setting("formatting", "formatting_preset", "Custom")
            
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
        email = get_v1("models.deepseek.email")
        if isinstance(email, str) and email.strip():
            self.v2_manager.set_setting("providers_credentials", "deepseek_email", email)

        pwd = get_v1("models.deepseek.password")
        if isinstance(pwd, str) and pwd:
            self.v2_manager.set_setting("providers_credentials", "deepseek_password", pwd)

        auto_login = get_v1("models.deepseek.auto_login")
        if auto_login is not None:
            self.v2_manager.set_setting("providers_credentials", "auto_login", bool(auto_login))

        # DeepSeek Behavior
        dt = get_v1("models.deepseek.deepthink")
        if dt is not None:
            self.v2_manager.set_setting("deepseek_behavior", "enable_deepthink", bool(dt))

        st = get_v1("models.deepseek.send_thoughts")
        if st is not None:
            self.v2_manager.set_setting("deepseek_behavior", "send_deepthink", bool(st))

        search = get_v1("models.deepseek.search")
        if search is not None:
            self.v2_manager.set_setting("deepseek_behavior", "enable_search", bool(search))

        tf = get_v1("models.deepseek.text_file")
        if tf is not None:
            self.v2_manager.set_setting("deepseek_behavior", "send_as_text_file", bool(tf))

        clean = get_v1("models.deepseek.clean_regeneration")
        if clean is not None:
            self.v2_manager.set_setting("deepseek_behavior", "clean_regeneration", bool(clean))

        # Console Settings
        font_size = get_v1("console.font_size")
        if font_size is not None:
            try:
                self.v2_manager.set_setting("console_settings", "font_size", int(font_size))
            except:
                pass
        
        palette = get_v1("console.color_palette")
        if isinstance(palette, str) and palette.strip():
            self.v2_manager.set_setting("console_settings", "color_palette", palette)
            
        dump_dir = get_v1("console.dump_directory")
        if isinstance(dump_dir, str):
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
        preset = get_v1("formatting.preset")
        migrated_preset = preset_map.get(preset) if isinstance(preset, str) else None
        if migrated_preset:
            self.v2_manager.set_setting("formatting", "formatting_preset", migrated_preset)

            # Make sure the v2 template matches the preset (v2 uses one template).
            if migrated_preset != "Custom":
                preset_templates = {
                    "Classic - Name": "{{name}}: {{content}}",
                    "Classic - Role": "{{role}}: {{content}}",
                    "XML-Like - Name": "<{{name}}>{{content}}</{{name}}>",
                    "XML-Like - Role": "<{{role}}>{{content}}</{{role}}>",
                    "Divided - Name": "### {{name}}\\n{{content}}",
                    "Divided - Role": "### {{role}}\\n{{content}}",
                }
                template = preset_templates.get(migrated_preset)
                if template:
                    self.v2_manager.set_setting("formatting", "formatting_template", template)

        # We rely on the template file migration for Custom.
        
        # Injection
        inj_enabled = get_v1("injection.enabled")
        prompt = get_v1("injection.system_prompt")
        if isinstance(prompt, str) and prompt:
            if inj_enabled is None or bool(inj_enabled):
                self.v2_manager.set_setting(
                    "formatting", "injection_content", convert_v1_injection_to_v2(prompt)
                )
            
        # Logging
        log_enabled = get_v1("logging.enabled")
        if log_enabled is not None:
            self.v2_manager.set_setting("logfiles", "enable_logfiles", bool(log_enabled))

        max_files = get_v1("logging.max_files")
        if max_files is not None:
            self.v2_manager.set_setting("logfiles", "max_files", int(max_files))
        
        # Log size (V1 bytes -> V2 Value + Unit)
        max_size_bytes = get_v1("logging.max_file_size")
        if max_size_bytes is not None:
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
        port = get_v1("api.port")
        if port is not None:
            try:
                self.v2_manager.set_setting("network_settings", "port", int(port))
            except:
                pass
        
        # API Keys
        # V1: {"Name": "secret"} -> V2: [["Name", "secret"]]
        auth_enabled = get_v1("security.api_auth_enabled")
        api_keys = get_v1("security.api_keys")
        if isinstance(api_keys, dict) and api_keys:
            v2_keys = [[str(k), str(v)] for k, v in api_keys.items()]
            self.v2_manager.set_setting("network_settings", "api_keys", v2_keys)
            self.v2_manager.set_setting(
                "network_settings",
                "use_api_keys",
                bool(auth_enabled) if auth_enabled is not None else True,
            )
        elif auth_enabled is not None:
            # Don't enable API auth with no keys.
            self.v2_manager.set_setting("network_settings", "use_api_keys", False)

        # Persistent Cookies
        persist = get_v1("browser_persistent_cookies")
        if persist is not None:
            self.v2_manager.set_setting("system_settings", "persistent_sessions", bool(persist))
