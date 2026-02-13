from enum import Enum
from dataclasses import dataclass, field
from typing import List, Any, Optional, Callable, Dict
from .validators import validate_email, validate_port, validate_directory_path
from .location import get_config_storage_options
from drivers.providers import provider_options

class SettingType(Enum):
    BOOLEAN = "boolean"
    STRING = "string"
    DIRECTORY = "directory"
    INTEGER = "integer"
    PASSWORD = "password"
    TEXTAREA = "textarea"
    DROPDOWN = "dropdown"
    DIVIDER = "divider"
    DESCRIPTION = "description"
    BUTTON = "button"
    ROW = "row"
    INPUT_PAIR = "input_pair"
    REDIRECT = "redirect"

@dataclass
class SettingField:
    key: str
    label: str
    type: SettingType
    default: Any
    tooltip: Optional[str] = None
    validator: Optional[Callable[[Any], None]] = None
    required: bool = False
    nullable: bool = False
    depends: Optional[str] = None
    options: Optional[List[str]] = None # For dropdowns
    transient: bool = False # For UI-only fields (not persisted)
    action: Optional[str] = None # For buttons (function name to call)
    sub_fields: Optional[List["SettingField"]] = None # For ROW type
    ratios: Optional[List[int]] = None # For ROW type (e.g. [70, 30])
    force_when_dep_unmet: Optional[Any] = None
    visible_depends: Optional[str] = None

@dataclass
class SettingCategory:
    name: str
    key: str
    fields: List[SettingField] = field(default_factory=list)

# Define the schema
SCHEMA = [
    SettingCategory(
        name="Providers & Credentials",
        key="providers_credentials",
        fields=[
            SettingField(
                key="provider",
                label="Provider",
                type=SettingType.DROPDOWN,
                default="DeepSeek",
                options=provider_options(),
                tooltip=(
                    "Select the active provider driver. "
                    "This applies on the next browser start (Stop -> Start)."
                ),
            ),
            SettingField(
                key="auto_login",
                label="Auto Login",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Automatically log in using the provided credentials."
            ),
            SettingField(
                key="ece_credential_manager",
                label="Credential Manager",
                type=SettingType.REDIRECT,
                default="Credential Manager",
                tooltip="Manage provider credentials in the configurator.",
                action="open_ece_credential_manager",
                depends="experimental.ece_enabled",
                visible_depends="experimental.ece_enabled",
            ),
            SettingField(
                key="deepseek_email",
                label="DeepSeek Email",
                type=SettingType.STRING,
                default="",
                tooltip="Email address for DeepSeek login.",
                validator=validate_email,
                required=True,
                depends=(
                    "providers_credentials.auto_login && providers_credentials.provider==DeepSeek "
                    "&& experimental.ece_enabled==false"
                ),
                visible_depends="experimental.ece_enabled==false",
            ),
            SettingField(
                key="deepseek_password",
                label="DeepSeek Password",
                type=SettingType.PASSWORD,
                default="",
                tooltip="Password for DeepSeek login.",
                required=True,
                depends=(
                    "providers_credentials.auto_login && providers_credentials.provider==DeepSeek "
                    "&& experimental.ece_enabled==false"
                ),
                visible_depends="experimental.ece_enabled==false",
            ),
            SettingField(
                key="glm_email",
                label="GLM Email",
                type=SettingType.STRING,
                default="",
                tooltip="Email address for GLM Chat (Z.ai) login.",
                validator=validate_email,
                required=True,
                depends=(
                    "providers_credentials.auto_login && providers_credentials.provider==GLM Chat "
                    "&& experimental.ece_enabled==false"
                ),
                visible_depends="experimental.ece_enabled==false",
            ),
            SettingField(
                key="glm_password",
                label="GLM Password",
                type=SettingType.PASSWORD,
                default="",
                tooltip="Password for GLM Chat (Z.ai) login.",
                required=True,
                depends=(
                    "providers_credentials.auto_login && providers_credentials.provider==GLM Chat "
                    "&& experimental.ece_enabled==false"
                ),
                visible_depends="experimental.ece_enabled==false",
            ),
            SettingField(
                key="moonshot_email",
                label="Moonshot Email",
                type=SettingType.STRING,
                default="",
                tooltip=(
                    "Optional account identifier for Moonshot. "
                    "Not used for Moonshot login automation (manual Google sign-in is required)."
                ),
                validator=validate_email,
                required=False,
                depends=(
                    "providers_credentials.provider==Moonshot "
                    "&& experimental.ece_enabled==false"
                ),
                visible_depends="experimental.ece_enabled==false",
            ),
            SettingField(
                key="moonshot_password",
                label="Moonshot Password",
                type=SettingType.PASSWORD,
                default="",
                tooltip=(
                    "Optional account secret/identifier for Moonshot. "
                    "Not used for Moonshot login automation (manual Google sign-in is required)."
                ),
                required=False,
                depends=(
                    "providers_credentials.provider==Moonshot "
                    "&& experimental.ece_enabled==false"
                ),
                visible_depends="experimental.ece_enabled==false",
            ),
        ]
    ),
    SettingCategory(
        name="Formatting",
        key="formatting",
        fields=[
            SettingField(
                key="formatting_divider_1",
                label="Formatting Template",
                type=SettingType.DIVIDER,
                default=None
            ),
            SettingField(
                key="formatting_preset",
                label="Preset",
                type=SettingType.DROPDOWN,
                default="Classic - Name",
                options=[
                    "Classic - Name", "Classic - Role", 
                    "XML-Like - Name", "XML-Like - Role", 
                    "Divided - Name", "Divided - Role", 
                    "Custom"
                ],
                tooltip="Choose a formatting preset or create your own."
            ),
            SettingField(
                key="formatting_template",
                label="Template",
                type=SettingType.TEXTAREA,
                default="{{name}}: {{content}}",
                tooltip="Define how messages are formatted. Use {{name}}, {{role}}, and {{content}} placeholders."
            ),
            SettingField(
                key="reset_formatting_btn",
                label="Reset to Default",
                type=SettingType.BUTTON,
                default="Reset",
                action="reset_formatting",
                tooltip="Reset formatting template to Classic - Name."
            ),
            SettingField(
                key="formatting_divider",
                label="Divide messages with...",
                type=SettingType.TEXTAREA,
                default="\\n",
                tooltip="String to insert between messages. Default is a newline."
            ),
            SettingField(
                key="apply_formatting",
                label="Apply Formatting",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Toggle whether to apply the formatting rules."
            ),
            SettingField(
                key="formatting_divider_2",
                label="Name Behavior",
                type=SettingType.DIVIDER,
                default=None
            ),
            SettingField(
                key="name_behavior_desc",
                label="Description",
                type=SettingType.DESCRIPTION,
                default="Toggle methods for fetching names. If all fail or are disabled, role names are used. Methods run in order.",
                tooltip=None
            ),
            SettingField(
                key="enable_msg_objects",
                label="Message Objects",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Scan for 'name' parameter in message objects (or 'irp-next' for RossAscends's STMP patcher compat)."
            ),
            SettingField(
                key="enable_ir2",
                label="IR2 blocks",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Parse [[IR2u]]username[[/IR2u]]-[[IR2a]]charname[[/IR2a]] blocks."
            ),
            SettingField(
                key="enable_classic_irp",
                label="Classic IntenseRP",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Parse DATA1: \"{{char}}\" DATA2: \"{{user}}\" blocks."
            ),
            SettingField(
                key="formatting_divider_3",
                label="Injection",
                type=SettingType.DIVIDER,
                default=None
            ),
            SettingField(
                key="injection_desc",
                label="Description",
                type=SettingType.DESCRIPTION,
                default="Insert a small instruction before or after all other messages. Supports {{user}} and {{char}} placeholders.",
                tooltip=None
            ),
            SettingField(
                key="injection_position",
                label="Position",
                type=SettingType.DROPDOWN,
                default="Before",
                options=["Before", "After"],
                tooltip="Where to place the injected content."
            ),
            SettingField(
                key="injection_content",
                label="Content",
                type=SettingType.TEXTAREA,
                default="",
                tooltip="Content to inject. Supports {{user}} and {{char}} placeholders."
            ),
            SettingField(
                key="reset_injection_btn",
                label="Reset to Default",
                type=SettingType.BUTTON,
                default="Reset",
                action="reset_injection",
                tooltip="Reset injection settings to default."
            ),
        ]
    ),
    SettingCategory(
        name="DeepSeek Behavior",
        key="deepseek_behavior",
        fields=[
            SettingField(
                key="enable_deepthink",
                label="Enable DeepThink",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle the DeepThink button on the DeepSeek interface."
            ),
            SettingField(
                key="send_deepthink",
                label="Send DeepThink",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include the thinking process in the response sent to the API."
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle the Search button on the DeepSeek interface."
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Upload message as a text file instead of typing it."
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=15,
                tooltip="Max seconds to wait for the send button to become enabled after file upload.",
                depends="deepseek_behavior.send_as_text_file"
            ),
            SettingField(
                key="anti_censorship",
                label="Anti-Censorship",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="If enabled, suppresses the 'Sorry, that's beyond my current scope' message when content filtering is triggered."
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="If enabled, attempts to regenerate the last message instead of creating a new chat if the prompt is identical."
            ),
        ]
    ),
    SettingCategory(
        name="GLM Behavior",
        key="glm_behavior",
        fields=[
            SettingField(
                key="model",
                label="Model",
                type=SettingType.DROPDOWN,
                default="GLM-5",
                options=["GLM-5", "GLM-4.7", "GLM-4.6"],
                tooltip=(
                    "Select which GLM model to use in the GLM Chat web UI. "
                    "This is separate from the API 'glm-*' model IDs (those are behavior presets)."
                ),
            ),
            SettingField(
                key="enable_deepthink",
                label="Enable Deep Think",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle the Deep Think button on the GLM interface."
            ),
            SettingField(
                key="send_deepthink",
                label="Send Deep Think",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include the thinking process in the response sent to the API."
            ),
            SettingField(
                key="search_forced_off_note",
                label="Search (Note)",
                type=SettingType.DESCRIPTION,
                default=(
                    "Note: GLM Chat Search streams internal tool/search payloads into the response stream."
                    "IntenseRP does *not forward* these search results to the client for stability reasons."
                    "Despite that, you might still get citations or references in the response."
                ),
                tooltip=None,
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Toggle the Search button on the GLM interface. "
                    "Search results are not forwarded to the client."
                )
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Upload message as a text file instead of typing it."
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=15,
                tooltip="Max seconds to wait for the send button to become enabled after file upload.",
                depends="glm_behavior.send_as_text_file"
            ),
            SettingField(
                key="text_file_filler",
                label="Text File Filler",
                type=SettingType.TEXTAREA,
                default=".",
                tooltip="Text pasted into the textbox alongside the uploaded file. GLM refuses to send a file with no text in the message.",
                depends="glm_behavior.send_as_text_file"
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="If enabled, attempts to regenerate the last message instead of creating a new chat if the prompt is identical."
            ),
            SettingField(
                key="quirks_divider",
                label="Quirks",
                type=SettingType.DIVIDER,
                default=None
            ),
            SettingField(
                key="quirks_desc",
                label="Description",
                type=SettingType.DESCRIPTION,
                default="Timing and interaction tweaks for slower machines or flaky UI behavior.",
                tooltip=None
            ),
            SettingField(
                key="ui_click_timeout",
                label="UI Click Timeout (ms)",
                type=SettingType.INTEGER,
                default=3000,
                tooltip="Timeout in milliseconds for UI element clicks (buttons, dropdowns, etc.)."
            ),
            SettingField(
                key="post_action_delay",
                label="Post-Action Delay (ms)",
                type=SettingType.INTEGER,
                default=500,
                tooltip="Delay in milliseconds after UI actions (new chat, model switch) to let the interface settle."
            ),
            SettingField(
                key="message_send_timeout",
                label="Message Send Timeout (s)",
                type=SettingType.INTEGER,
                default=5,
                tooltip="Max seconds to wait for the send button to become enabled after text entry (non-file mode)."
            ),
        ]
    ),
    SettingCategory(
        name="Moonshot Behavior",
        key="moonshot_behavior",
        fields=[
            SettingField(
                key="enable_deepthink",
                label="Enable Thinking",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Switch Kimi between K2.5 Instant and K2.5 Thinking before sending.",
            ),
            SettingField(
                key="send_deepthink",
                label="Send Thinking",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include Kimi's thinking content in the response sent to the API.",
            ),
            SettingField(
                key="search_and_think_note",
                label="Search + Thinking (Note)",
                type=SettingType.DESCRIPTION,
                default=(
                    "Kimi can emit multi-stage reasoning when Search and Thinking are both enabled. "
                    "Some clients (including SillyTavern) may not parse this cleanly."
                ),
                tooltip=None,
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle Kimi's internet search tool in the web UI.",
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Upload message as a text file instead of typing it.",
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=15,
                tooltip="Max seconds to wait for the send button to become enabled after file upload.",
                depends="moonshot_behavior.send_as_text_file",
            ),
            SettingField(
                key="text_file_filler",
                label="Text File Filler",
                type=SettingType.TEXTAREA,
                default=".",
                tooltip="Text pasted into the textbox alongside the uploaded file. Kimi refuses to send a file with no text in the message.",
                depends="moonshot_behavior.send_as_text_file",
            ),
            SettingField(
                key="anti_censorship",
                label="Anti-Censorship",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Suppress refusal-like messages in the stream when a content-filter-style event is detected.",
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="If enabled, attempts to regenerate the last message instead of creating a new chat if the prompt is identical.",
            ),
        ],
    ),
    SettingCategory(
        name="Logfiles",
        key="logfiles",
        fields=[
            SettingField(
                key="enable_logfiles",
                label="Enable Logfiles",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Enable logging to files."
            ),
            SettingField(
                key="log_dir",
                label="Log Directory",
                type=SettingType.DIRECTORY,
                default="logs",
                tooltip="Directory to store log files.",
                validator=validate_directory_path,
                nullable=True,
            ),
            SettingField(
                key="max_files",
                label="Max Log Files",
                type=SettingType.INTEGER,
                default=5,
                tooltip="Maximum number of log files to keep (before rotation). 0 for unlimited."
            ),
            SettingField(
                key="max_file_size",
                label="Max File Size",
                type=SettingType.ROW,
                default=None,
                ratios=[70, 30],
                sub_fields=[
                     SettingField(
                        key="size_val",
                        label="Size Value",
                        type=SettingType.INTEGER,
                        default=10,
                        tooltip="Max file size value. 0 for unlimited."
                    ),
                    SettingField(
                        key="size_unit",
                        label="Unit",
                        type=SettingType.DROPDOWN,
                        default="MB",
                        options=["KB", "MB", "GB"],
                        tooltip="Unit for max file size."
                    ),
                ]
            ),
        ]
    ),
    SettingCategory(
        name="System Settings",
        key="system_settings",
        fields=[
            SettingField(
                key="persistent_sessions",
                label="Persistent Sessions",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Reuse a persistent Playwright browser profile so logins persist between restarts."
            ),
            SettingField(
                key="delete_persistent_profile_row",
                label="Delete Profile",
                type=SettingType.ROW,
                default=None,
                ratios=[80, 20],
                tooltip="Delete a specific saved browser profile used for Persistent Sessions (logs you out).",
                sub_fields=[
                    SettingField(
                        key="persistent_profile_to_delete",
                        label="Profile",
                        type=SettingType.DROPDOWN,
                        default="",
                        options=[],
                        transient=True,
                        tooltip="Choose which saved profile to delete.",
                    ),
                    SettingField(
                        key="delete_persistent_profile_btn",
                        label="Delete",
                        type=SettingType.BUTTON,
                        default="Delete",
                        action="delete_selected_persistent_profile",
                        tooltip="Delete the selected profile.",
                    ),
                ],
            ),
            SettingField(
                key="clear_all_persistent_profiles",
                label="Clear All Profiles",
                type=SettingType.BUTTON,
                default="Clear All",
                action="clear_all_persistent_profiles",
                tooltip="Delete all saved browser profiles used for Persistent Sessions (ECE + Legacy).",
            ),
            SettingField(
                key="notify_on_driver_crash",
                label="Notify on Driver Crash",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Show a notification when the provider browser is closed or crashes unexpectedly.",
            ),
            SettingField(
                key="config_storage_divider",
                label="Config Storage",
                type=SettingType.DIVIDER,
                default=None,
            ),
            SettingField(
                key="config_storage_location",
                label="Config Storage Location",
                type=SettingType.DROPDOWN,
                default="Relative",
                options=get_config_storage_options(),
                tooltip=(
                    "Choose where to store configuration data (settings/key/profiles). "
                    "Changing this will migrate the config directory and restart the app."
                ),
            ),
            SettingField(
                key="config_storage_custom_path",
                label="Custom Config Directory",
                type=SettingType.DIRECTORY,
                default="",
                tooltip=(
                    "Used when Config Storage Location is Custom. "
                    "Absolute paths are recommended; relative paths are resolved from the app folder."
                ),
                validator=validate_directory_path,
            ),
            SettingField(
                key="ui_divider",
                label="Main Window",
                type=SettingType.DIVIDER,
                default=None,
            ),
            SettingField(
                key="show_request_queue_preview",
                label="Request Queue Preview",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Show an optional Request Queue panel in the main window.",
            ),
            SettingField(
                key="logging_levels_divider",
                label="Logging Levels",
                type=SettingType.DIVIDER,
                default=None,
            ),
            SettingField(
                key="stdout_log_level",
                label="Stdout",
                type=SettingType.DROPDOWN,
                default="Debug",
                options=["Debug", "Success", "Info", "Warning", "Error"],
                tooltip="Minimum severity for messages printed to the terminal (stdout).",
            ),
            SettingField(
                key="console_log_level",
                label="Console Window",
                type=SettingType.DROPDOWN,
                default="Debug",
                options=["Debug", "Success", "Info", "Warning", "Error"],
                tooltip="Minimum severity for messages shown in the Console Window.",
            ),
            SettingField(
                key="mini_console_log_level",
                label="Mini-Console",
                type=SettingType.DROPDOWN,
                default="Success",
                options=["Debug", "Success", "Info", "Warning", "Error"],
                tooltip="Minimum severity for messages shown in the Activity Log (main window).",
            ),
            SettingField(
                key="logfile_log_level",
                label="Logfiles",
                type=SettingType.DROPDOWN,
                default="Debug",
                options=["Debug", "Success", "Info", "Warning", "Error"],
                tooltip="Minimum severity for messages written to log files.",
            ),
        ]
    ),
    SettingCategory(
        name="Experimental",
        key="experimental",
        fields=[
            SettingField(
                key="ece_enabled",
                label="Enable Experimental Credential Engine (ECE)",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Use the Experimental Credential Engine instead of the legacy per-provider credential fields.",
            ),
            SettingField(
                key="ece_select_least_used",
                label="Select Least Used",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Prefer the credential pair with the oldest last-use date (unused pairs are preferred). "
                    "When disabled, a random pair is selected."
                ),
                depends="experimental.ece_enabled",
            ),
            SettingField(
                key="ece_reauth_on_no_content",
                label="Re-auth on no content",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "If a provider returns no meaningful output (or a rate-limit-like failure), "
                    "restart the browser and rotate to a different ECE profile when possible."
                ),
                depends="experimental.ece_enabled",
            ),
        ],
    ),
    SettingCategory(
        name="Application Settings",
        key="application_settings",
        fields=[
            SettingField(
                key="current_version_info",
                label="Current Version",
                type=SettingType.DESCRIPTION,
                default="Current version: (loading...)",
                tooltip=None,
            ),
            SettingField(
                key="update_status_info",
                label="Update Status",
                type=SettingType.DESCRIPTION,
                default="Status: Not checked yet.",
                tooltip=None,
            ),
            SettingField(
                key="check_for_updates_btn",
                label="Check For Updates",
                type=SettingType.BUTTON,
                default="Check",
                action="check_for_updates",
                tooltip="Compare local version.json with the latest version on GitHub (version, aua, severity).",
            ),
            SettingField(
                key="check_for_updates_on_startup",
                label="Check for Updates on Startup",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Automatically check for updates when the app starts.",
            ),
            SettingField(
                key="show_only_active_provider_behavior",
                label="Show Only Active Provider Behavior",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip=(
                    "If enabled, only the Behavior category for the selected Provider is shown. "
                    "If disabled, all provider Behavior categories are shown."
                ),
            ),
        ],
    ),
    SettingCategory(
        name="Console Settings",
        key="console_settings",
        fields=[
            SettingField(
                key="enable_console",
                label="Enable Console",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Show a console window for viewing application logs.",
            ),
            SettingField(
                key="log_to_main",
                label="Log to Main",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Also log to the Activity Log in the main window. Forced on if the console is disabled.",
                depends="console_settings.enable_console",
                force_when_dep_unmet=True,
            ),
            SettingField(
                key="log_to_stdout",
                label="Log to Stdout",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Also log to stdout/terminal. Forced on if the console is disabled.",
                depends="console_settings.enable_console",
                force_when_dep_unmet=True,
            ),
            SettingField(
                key="max_lines",
                label="Max Line Limit",
                type=SettingType.INTEGER,
                default=500,
                tooltip="Maximum number of lines to keep in the console history."
            ),
            SettingField(
                key="font_size",
                label="Font Size",
                type=SettingType.INTEGER,
                default=10,
                tooltip="Font size for the console text."
            ),
            SettingField(
                key="wrap_lines",
                label="Wrap Lines",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Soft-wrap long lines in the console window.",
            ),
            SettingField(
                key="auto_scroll_mode",
                label="Auto-Scroll Mode",
                type=SettingType.DROPDOWN,
                default="Always",
                options=["Always", "Bottom only", "Never"],
                tooltip="Control how the console view follows new log messages.",
            ),
            SettingField(
                key="color_palette",
                label="Color Palette",
                type=SettingType.DROPDOWN,
                default="Modern",
                options=["Modern", "Classic", "Bright"],
                tooltip="Choose a color scheme for log levels."
            ),
            SettingField(
                key="always_on_top",
                label="Always On Top",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Keep the console window on top of other windows."
            ),
        ]
    ),
    SettingCategory(
        name="Console Dumping",
        key="console_dumping",
        fields=[
            SettingField(
                key="confirm_clear",
                label="Confirm Clear",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Ask for confirmation before clearing the console output.",
            ),
            SettingField(
                key="condump_directory",
                label="Condump Directory",
                type=SettingType.DIRECTORY,
                default=None,
                tooltip="Directory to write console dumps to. Leave blank to ask each time.",
                validator=validate_directory_path,
                nullable=True,
            ),
        ]
    ),
    SettingCategory(
        name="Network Settings",
        key="network_settings",
        fields=[
            SettingField(
                key="port",
                label="Port",
                type=SettingType.INTEGER,
                default=7777,
                tooltip="Port for the local API server.",
                validator=validate_port,
            ),
            SettingField(
                key="available_on_lan",
                label="Available on LAN",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Make the API server accessible from other devices on the local network.",
            ),
            SettingField(
                key="use_api_keys",
                label="Use API Keys",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Require an API key (Bearer) for incoming requests.",
            ),
            SettingField(
                key="api_keys",
                label="API Keys",
                type=SettingType.INPUT_PAIR,
                default=[],
                tooltip="List of API key name/value pairs.",
                depends="network_settings.use_api_keys",
                required=True,
            ),
        ]
    ),
]

