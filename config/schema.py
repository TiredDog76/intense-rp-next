from enum import Enum
from dataclasses import dataclass, field
from typing import List, Any, Optional, Callable, Dict
from .validators import (
    validate_port,
    validate_directory_path,
    validate_ip_address_list,
    validate_float_range,
)
from .formatting_presets import FORMATTING_PRESET_OPTIONS
from .location import get_config_storage_options
from drivers.providers import provider_options

DOCS_ACCOUNTS = "features/accounts/"
DOCS_AISTUDIO = "providers/aistudio-behavior/"
DOCS_API_BEHAVIOR = "advanced/api-behavior/"
DOCS_CONSOLE = "features/console-logging/"
DOCS_DEEPSEEK = "providers/deepseek-behavior/"
DOCS_FORMATTING = "features/formatting/"
DOCS_GLM = "providers/glm-behavior/"
DOCS_GLM_QUIRKS = "advanced/glm-quirks/"
DOCS_HOTSWAPS = "features/hotswaps/"
DOCS_IP_WHITELIST = "advanced/ip-whitelist/"
DOCS_LOGIN = "features/login-sessions/"
DOCS_MOONSHOT = "providers/moonshot-behavior/"
DOCS_MULTI_SLOT_CACHE = "features/multi-slot-cache/"
DOCS_NETWORK = "features/network-api/"
DOCS_PROVIDER_SUPPORT = "advanced/provider-support/"
DOCS_QWEN = "providers/qwen-behavior/"
DOCS_REMOTE_CONTROL = "experimental/remote-control/"
DOCS_BETTER_MODEL_NAMES = "experimental/better-model-names/"
DOCS_PROVIDERS_IN_PARALLEL = "experimental/providers-in-parallel/"
DOCS_SYSTEM = "features/system/"

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
    HINT = "hint"
    BUTTON = "button"
    ROW = "row"
    INPUT_PAIR = "input_pair"
    INPUT_LIST = "input_list"
    REDIRECT = "redirect"

@dataclass
class AlternativeAction:
    name: str
    action: str
    icon: Optional[str] = None

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
    affects: Optional[List[str]] = None # UI components to refresh when this field changes
    alternative_actions: Optional[List[AlternativeAction]] = None # For INPUT_PAIR-style fields
    docs_path: Optional[str] = None
    docs_anchor: Optional[str] = None
    hint_variant: Optional[str] = None

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
                docs_path=DOCS_PROVIDER_SUPPORT,
                docs_anchor="how-providers-work-in-v2",
            ),
            SettingField(
                key="auto_login",
                label="Auto Login",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Automatically log in using a saved account from Credential Manager.",
                docs_path=DOCS_LOGIN,
                docs_anchor="auto-login",
            ),
            SettingField(
                key="select_least_used",
                label="Select Least Used",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Prefer the least recently used account. Otherwise, a random account is selected.",
                docs_path=DOCS_ACCOUNTS,
                docs_anchor="how-account-selection-works",
            ),
            SettingField(
                key="reload_on_failure",
                label="Reload on Failure",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Restart and rotate to a different account/profile on empty or rate-limited responses.",
                docs_path=DOCS_ACCOUNTS,
                docs_anchor="reload-on-failure-auto-retry",
            ),
            SettingField(
                key="credential_manager",
                label="Credential Manager",
                type=SettingType.REDIRECT,
                default="Credential Manager",
                tooltip="Manage provider accounts (email/password) used for Auto Login.",
                action="open_credential_manager",
                docs_path=DOCS_ACCOUNTS,
                docs_anchor="quick-setup",
            )
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
                options=FORMATTING_PRESET_OPTIONS,
                tooltip="Choose a formatting preset or create your own.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="presets",
            ),
            SettingField(
                key="formatting_template",
                label="Template",
                type=SettingType.TEXTAREA,
                default="{{name}}: {{content}}",
                tooltip="Define how messages are formatted. Use {{name}}, {{role}}, and {{content}} placeholders.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="templates",
            ),
            SettingField(
                key="reset_formatting_btn",
                label="Reset to Default",
                type=SettingType.BUTTON,
                default="Reset",
                action="reset_formatting",
                tooltip="Reset formatting template to Classic - Name.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="presets",
            ),
            SettingField(
                key="formatting_divider",
                label="Divide messages with...",
                type=SettingType.TEXTAREA,
                default="\\n",
                tooltip="String to insert between messages. Default is a newline.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="message-divider",
            ),
            SettingField(
                key="apply_formatting",
                label="Apply Formatting",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Toggle whether to apply the formatting rules.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="disabling-formatting",
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
                tooltip="Scan for 'name' parameter in message objects (or 'irp-next' for RossAscends's STMP patcher compat).",
                docs_path=DOCS_FORMATTING,
                docs_anchor="message-objects",
            ),
            SettingField(
                key="enable_ir2",
                label="IR2 blocks",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Parse [[IR2u]]username[[/IR2u]]-[[IR2a]]charname[[/IR2a]] blocks.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="ir2-blocks",
            ),
            SettingField(
                key="enable_classic_irp",
                label="Classic IntenseRP",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Parse DATA1: \"{{char}}\" DATA2: \"{{user}}\" blocks.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="classic-intenserp",
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
                tooltip="Where to place the injected content.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="injection",
            ),
            SettingField(
                key="injection_content",
                label="Content",
                type=SettingType.TEXTAREA,
                default="",
                tooltip="Content to inject. Supports {{user}} and {{char}} placeholders.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="injection",
            ),
            SettingField(
                key="reset_injection_btn",
                label="Reset to Default",
                type=SettingType.BUTTON,
                default="Reset",
                action="reset_injection",
                tooltip="Reset injection settings to default.",
                docs_path=DOCS_FORMATTING,
                docs_anchor="injection",
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
                tooltip="Toggle the DeepThink button on the DeepSeek interface.",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="enable-deepthink",
            ),
            SettingField(
                key="send_deepthink",
                label="Send DeepThink",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include the thinking process in the response sent to the API.",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="send-deepthink",
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle the Search button on the DeepSeek interface.",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="search",
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Upload message as a text file instead of typing it.",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="file-upload-mode",
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=15,
                tooltip="Max seconds to wait for the send button to become enabled after file upload.",
                depends="deepseek_behavior.send_as_text_file",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="file-upload-timeout",
            ),
            SettingField(
                key="first_chunk_timeout",
                label="First Chunk Timeout (s)",
                type=SettingType.INTEGER,
                default=45,
                tooltip="Max seconds to wait for the response stream to start before timing out.",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="first-chunk-timeout",
            ),
            SettingField(
                key="anti_censorship",
                label="Anti-Censorship",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Suppress the refusal message when content filtering is triggered.",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="anti-censorship",
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Regenerate the last message instead of creating a new chat when the prompt is identical.",
                docs_path=DOCS_DEEPSEEK,
                docs_anchor="clean-regeneration",
            ),
            SettingField(
                key="multi_slot_cache",
                label="Multi-Slot Cache",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Reuse up to 7 older cached chats for duplicate prompts instead of only the most recent one.",
                depends="deepseek_behavior.clean_regeneration",
                force_when_dep_unmet=False,
                docs_path=DOCS_MULTI_SLOT_CACHE,
                docs_anchor="how-it-works",
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
                tooltip="Select which GLM model to use in the web UI. Not related to the API model IDs.",
                docs_path=DOCS_GLM,
                docs_anchor="modes-model-ids",
            ),
            SettingField(
                key="enable_deepthink",
                label="Enable Deep Think",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle the Deep Think button on the GLM interface.",
                docs_path=DOCS_GLM,
                docs_anchor="enable-deep-think",
            ),
            SettingField(
                key="send_deepthink",
                label="Send Deep Think",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include the thinking process in the response sent to the API.",
                docs_path=DOCS_GLM,
                docs_anchor="send-deep-think",
            ),
            SettingField(
                key="count_tokens",
                label="Count Tokens",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip=(
                    "Include a token count in the response metadata for each message."
                ),
                docs_path=DOCS_GLM,
                docs_anchor="count-tokens",
            ),
            SettingField(
                key="search_forced_off_note",
                label="Search",
                type=SettingType.HINT,
                default=(
                    "GLM Search results are not forwarded to the client for stability reasons. "
                    "You may still see citations in the response."
                ),
                tooltip=None,
                hint_variant="info",
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Toggle the Search button on the GLM interface. "
                    "Search results are not forwarded to the client."
                ),
                docs_path=DOCS_GLM,
                docs_anchor="search",
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Upload message as a text file instead of typing it.",
                docs_path=DOCS_GLM,
                docs_anchor="file-upload-mode",
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=15,
                tooltip="Max seconds to wait for the send button to become enabled after file upload.",
                depends="glm_behavior.send_as_text_file",
                docs_path=DOCS_GLM,
                docs_anchor="file-upload-timeout",
            ),
            SettingField(
                key="text_file_filler",
                label="Text File Filler",
                type=SettingType.TEXTAREA,
                default=".",
                tooltip="Text sent alongside the uploaded file. Required because GLM won't send a file-only message.",
                depends="glm_behavior.send_as_text_file",
                docs_path=DOCS_GLM,
                docs_anchor="text-file-filler",
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Regenerate the last message instead of creating a new chat when the prompt is identical.",
                depends="glm_behavior.repetition_buster!=true",
                docs_path=DOCS_GLM,
                docs_anchor="clean-regeneration-known-issues",
            ),
            SettingField(
                key="repetition_buster",
                label="Repetition Buster",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "The opposite of Clean Regeneration. "
                    "On duplicate prompts, send a throwaway random cache-buster prompt first, "
                    "then open another fresh chat for the real request."
                ),
                depends="glm_behavior.clean_regeneration!=true",
                docs_path=DOCS_GLM,
                docs_anchor="repetition-buster",
            ),
            SettingField(
                key="multi_slot_cache",
                label="Multi-Slot Cache",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Reuse up to 7 older cached chats for duplicate prompts instead of only the most recent one.",
                depends="glm_behavior.clean_regeneration",
                force_when_dep_unmet=False,
                docs_path=DOCS_MULTI_SLOT_CACHE,
                docs_anchor="how-it-works",
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
                tooltip="Timeout in milliseconds for UI element clicks (buttons, dropdowns, etc.).",
                docs_path=DOCS_GLM_QUIRKS,
                docs_anchor="ui-click-timeout",
            ),
            SettingField(
                key="post_action_delay",
                label="Post-Action Delay (ms)",
                type=SettingType.INTEGER,
                default=500,
                tooltip="Delay in milliseconds after UI actions (new chat, model switch) to let the interface settle.",
                docs_path=DOCS_GLM_QUIRKS,
                docs_anchor="post-action-delay",
            ),
            SettingField(
                key="message_send_timeout",
                label="Message Send Timeout (s)",
                type=SettingType.INTEGER,
                default=5,
                tooltip="Max seconds to wait for the send button to become enabled after text entry (non-file mode).",
                docs_path=DOCS_GLM_QUIRKS,
                docs_anchor="message-send-timeout",
            ),
            SettingField(
                key="first_chunk_timeout",
                label="First Chunk Timeout (s)",
                type=SettingType.INTEGER,
                default=45,
                tooltip="Max seconds to wait for the response stream to start before timing out.",
                docs_path=DOCS_GLM_QUIRKS,
                docs_anchor="first-chunk-timeout",
            ),
            SettingField(
                key="refresh_after_generation",
                label="Refresh After Generation",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Refresh the page after a response finishes. Can help restore UI state and improve Clean Regeneration.",
                docs_path=DOCS_GLM_QUIRKS,
                docs_anchor="refresh-after-generation",
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
                docs_path=DOCS_MOONSHOT,
                docs_anchor="enable-thinking",
            ),
            SettingField(
                key="send_deepthink",
                label="Send Thinking",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include Kimi's thinking content in the response sent to the API.",
                docs_path=DOCS_MOONSHOT,
                docs_anchor="send-thinking",
            ),
            SettingField(
                key="search_and_think_note",
                label="Search + Thinking",
                type=SettingType.HINT,
                default=(
                    "Kimi can emit multi-stage reasoning when Search and Thinking are both enabled. "
                    "Some clients (including SillyTavern) may not parse this cleanly, avoid using both at the same time if you see weird formatting or missing content in the responses."
                ),
                tooltip=None,
                hint_variant="warn",
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle Kimi's internet search tool in the web UI.",
                docs_path=DOCS_MOONSHOT,
                docs_anchor="search",
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Upload message as a text file instead of typing it.",
                docs_path=DOCS_MOONSHOT,
                docs_anchor="file-upload-mode",
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=15,
                tooltip="Max seconds to wait for the send button to become enabled after file upload.",
                depends="moonshot_behavior.send_as_text_file",
                docs_path=DOCS_MOONSHOT,
                docs_anchor="file-upload-timeout",
            ),
            SettingField(
                key="text_file_filler",
                label="Text File Filler",
                type=SettingType.TEXTAREA,
                default=".",
                tooltip="Text sent alongside the uploaded file. Required because Kimi won't send a file-only message.",
                depends="moonshot_behavior.send_as_text_file",
                docs_path=DOCS_MOONSHOT,
                docs_anchor="text-file-filler",
            ),
            SettingField(
                key="anti_censorship",
                label="Anti-Censorship",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Suppress refusal-like messages in the stream when a content-filter-style event is detected.",
                docs_path=DOCS_MOONSHOT,
                docs_anchor="anti-censorship",
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Regenerate the last message instead of creating a new chat when the prompt is identical.",
                docs_path=DOCS_MOONSHOT,
                docs_anchor="clean-regeneration",
            ),
            SettingField(
                key="multi_slot_cache",
                label="Multi-Slot Cache",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Reuse up to 7 older cached chats for duplicate prompts instead of only the most recent one.",
                depends="moonshot_behavior.clean_regeneration",
                force_when_dep_unmet=False,
                docs_path=DOCS_MULTI_SLOT_CACHE,
                docs_anchor="how-it-works",
            ),
        ],
    ),
    SettingCategory(
        name="QwenLM Behavior",
        key="qwen_behavior",
        fields=[
            SettingField(
                key="model",
                label="Model",
                type=SettingType.DROPDOWN,
                default="Qwen3.5-Plus",
                options=[
                    "Qwen3.5-Plus",
                    "Qwen3.5-Flash",
                    "Qwen3.5-397B-A17B",
                    "Qwen3.5-122B-A10B",
                    "Qwen3.5-27B",
                    "Qwen3.5-35B-A3B",
                    "Qwen3-Max",
                    "Qwen3-235B-A22B-2507",
                    "Qwen3-Coder",
                    "Qwen3-VL-235B-A22B",
                    "Qwen3-Omni-Flash",
                    "Qwen2.5-Max",
                ],
                tooltip="Select which Qwen model to use in the web UI. Not related to the API model IDs.",
                docs_path=DOCS_QWEN,
                docs_anchor="real-qwen-model-selection-web-ui",
            ),
            SettingField(
                key="enable_deepthink",
                label="Enable Thinking",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Switch QwenLM into Thinking mode before sending.",
                docs_path=DOCS_QWEN,
                docs_anchor="enable-thinking",
            ),
            SettingField(
                key="send_deepthink",
                label="Send Thinking",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include QwenLM thinking summaries in the response sent to the API.",
                docs_path=DOCS_QWEN,
                docs_anchor="send-thinking",
            ),
            SettingField(
                key="count_tokens",
                label="Count Tokens",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Include a token count in the response metadata for each message.",
                docs_path=DOCS_QWEN,
                docs_anchor="count-tokens",
            ),
            SettingField(
                key="search_forced_off_note",
                label="Search",
                type=SettingType.HINT,
                default=(
                    "QwenLM Search results are not forwarded to the client for stability reasons. "
                    "You may still see citations in the response."
                ),
                tooltip=None,
                hint_variant="info",
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle QwenLM Web search in the web UI. Search results are not forwarded to the client.",
                docs_path=DOCS_QWEN,
                docs_anchor="search",
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Upload message as a text file instead of typing it.",
                docs_path=DOCS_QWEN,
                docs_anchor="file-upload-mode",
            ),
            SettingField(
                key="text_file_message",
                label="Text File Message",
                type=SettingType.TEXTAREA,
                default="",
                tooltip="Optional text pasted alongside the uploaded file. Leave empty to send file-only.",
                depends="qwen_behavior.send_as_text_file",
                docs_path=DOCS_QWEN,
                docs_anchor="text-file-message",
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=20,
                tooltip="Max seconds to wait for the send button to become available after file upload.",
                depends="qwen_behavior.send_as_text_file",
                docs_path=DOCS_QWEN,
                docs_anchor="file-upload-timeout",
            ),
            SettingField(
                key="message_send_timeout",
                label="Message Send Timeout (s)",
                type=SettingType.INTEGER,
                default=8,
                tooltip="Max seconds to wait for the send button to appear after text entry (non-file mode).",
                docs_path=DOCS_QWEN,
                docs_anchor="message-send-timeout",
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Regenerate the last message instead of creating a new chat when the prompt is identical.",
                docs_path=DOCS_QWEN,
                docs_anchor="clean-regeneration",
            ),
            SettingField(
                key="multi_slot_cache",
                label="Multi-Slot Cache",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Reuse up to 7 older cached chats for duplicate prompts instead of only the most recent one.",
                depends="qwen_behavior.clean_regeneration",
                force_when_dep_unmet=False,
                docs_path=DOCS_MULTI_SLOT_CACHE,
                docs_anchor="how-it-works",
            ),
        ],
    ),
    SettingCategory(
        name="Google AI Studio Behavior",
        key="aistudio_behavior",
        fields=[
            SettingField(
                key="model_divider",
                label="Model & Thinking",
                type=SettingType.DIVIDER,
                default=None,
            ),
            SettingField(
                key="model",
                label="Model",
                type=SettingType.DROPDOWN,
                default="Gemini 2.5 Flash",
                options=[
                    "Gemini 3.1 Pro",
                    "Gemini 3.1 Flash Lite",
                    "Gemini 3 Flash",
                    "Gemini 2.5 Pro",
                    "Gemini 2.5 Flash",
                    "Gemini 2.5 Flash Lite",
                ],
                tooltip="Select which Gemini model to use in the Google AI Studio web UI.",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="real-gemini-model-selection-web-ui",
            ),
            SettingField(
                key="enable_deepthink",
                label="Enable Thinking",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Use the configured Thinking Level on supported Gemini 3 / 3.1 models. "
                    "When disabled, IntenseRP falls back to the lowest available level instead."
                ),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="enable-thinking",
            ),
            SettingField(
                key="thinking_level",
                label="Thinking Level",
                type=SettingType.DROPDOWN,
                default="Medium",
                options=["Minimal", "Low", "Medium", "High"],
                tooltip=(
                    "Thinking level for supported Gemini 3 / 3.1 models. "
                    "Gemini 2.5 models ignore this setting."
                ),
                depends="aistudio_behavior.enable_deepthink",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="thinking-level",
            ),
            SettingField(
                key="send_deepthink",
                label="Send Thinking",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include Gemini thinking summaries in the response sent to the API.",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="send-thinking",
            ),
            SettingField(
                key="tools_divider",
                label="Tools & Uploads",
                type=SettingType.DIVIDER,
                default=None,
            ),
            SettingField(
                key="enable_search",
                label="Enable Search",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle Google Search grounding in the AI Studio web UI.",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="enable-search",
            ),
            SettingField(
                key="enable_url_context",
                label="Enable URL Context",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Toggle AI Studio's URL Context browsing mode in the web UI.",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="enable-url-context",
            ),
            SettingField(
                key="use_system_prompt_field",
                label="Use System Prompt Field",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Move leading system messages into AI Studio's System Instructions UI instead "
                    "of sending them in the main chat prompt."
                ),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="system-prompt-field",
            ),
            SettingField(
                key="send_as_text_file",
                label="Send As Text File",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Upload the prompt as a text file through AI Studio's media picker instead of "
                    "typing the whole message into the textarea."
                ),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="file-upload-mode",
            ),
            SettingField(
                key="text_file_message",
                label="Text File Message",
                type=SettingType.TEXTAREA,
                default="",
                tooltip=(
                    "Optional text to send alongside the uploaded prompt file. Leave empty to try "
                    "file-only requests."
                ),
                depends="aistudio_behavior.send_as_text_file",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="text-file-message",
            ),
            SettingField(
                key="file_upload_timeout",
                label="File Upload Timeout",
                type=SettingType.INTEGER,
                default=20,
                tooltip=(
                    "Max seconds to wait for the send button to become available after selecting "
                    "a prompt file."
                ),
                depends="aistudio_behavior.send_as_text_file",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="file-upload-timeout",
            ),
            SettingField(
                key="anti_censorship",
                label="Anti-Censorship",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Detect AI Studio hard-censorship, replace the blocked assistant turn, "
                    "and send up to 3 continue nudges automatically."
                ),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="anti-censorship",
            ),
            SettingField(
                key="anti_censorship_replacement_message",
                label="Replacement Message",
                type=SettingType.TEXTAREA,
                default=".",
                tooltip="Text used to replace the blocked assistant message before retrying.",
                depends="aistudio_behavior.anti_censorship",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="replacement-message",
            ),
            SettingField(
                key="anti_censorship_continue_nudge",
                label="Continue Nudge",
                type=SettingType.TEXTAREA,
                default="Continue.",
                tooltip="Text sent as the follow-up user message after a blocked AI Studio turn.",
                depends="aistudio_behavior.anti_censorship",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="continue-nudge",
            ),
            SettingField(
                key="sampling_divider",
                label="Sampling",
                type=SettingType.DIVIDER,
                default=None,
            ),
            SettingField(
                key="temperature",
                label="Temperature",
                type=SettingType.STRING,
                default="1.0",
                tooltip="Default temperature for AI Studio requests. Request-level overrides still win.",
                validator=validate_float_range(0.0, 2.0, label="Temperature"),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="temperature",
            ),
            SettingField(
                key="top_p",
                label="Top P",
                type=SettingType.STRING,
                default="0.95",
                tooltip="Default top-p value for AI Studio requests. Request-level overrides still win.",
                validator=validate_float_range(0.0, 1.0, label="Top P"),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="top-p",
            ),
            SettingField(
                key="max_output_tokens",
                label="Max Output Tokens",
                type=SettingType.INTEGER,
                default=65536,
                tooltip=(
                    "Default output token budget for AI Studio requests. "
                    "This maps to the web UI's maxOutputTokens control."
                ),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="max-output-tokens",
            ),
            SettingField(
                key="automation_divider",
                label="Automation",
                type=SettingType.DIVIDER,
                default=None,
            ),
            SettingField(
                key="auto_login_redirect_timeout",
                label="Auto Login Redirect Timeout (s)",
                type=SettingType.INTEGER,
                default=15,
                tooltip=(
                    "How long to wait for Google to return to AI Studio after auto-filling "
                    "credentials before falling back to manual completion."
                ),
                docs_path=DOCS_AISTUDIO,
                docs_anchor="auto-login-redirect-timeout",
            ),
            SettingField(
                key="clean_regeneration",
                label="Clean Regeneration",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Regenerate the last message instead of creating a new chat when the prompt is identical.",
                docs_path=DOCS_AISTUDIO,
                docs_anchor="clean-regeneration",
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
                tooltip="Enable logging to files.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="file-logging",
            ),
            SettingField(
                key="log_dir",
                label="Log Directory",
                type=SettingType.DIRECTORY,
                default="logs",
                tooltip="Directory to store log files.",
                validator=validate_directory_path,
                nullable=True,
                docs_path=DOCS_CONSOLE,
                docs_anchor="configuration",
            ),
            SettingField(
                key="max_files",
                label="Max Log Files",
                type=SettingType.INTEGER,
                default=5,
                tooltip="Maximum number of log files to keep (before rotation). 0 for unlimited.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="configuration",
            ),
            SettingField(
                key="max_file_size",
                label="Max File Size",
                type=SettingType.ROW,
                default=None,
                ratios=[70, 30],
                docs_path=DOCS_CONSOLE,
                docs_anchor="configuration",
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
                default=True,
                tooltip="Reuse a persistent Playwright browser profile so logins persist between restarts.",
                docs_path=DOCS_SYSTEM,
                docs_anchor="persistent-sessions",
            ),
            SettingField(
                key="delete_persistent_profile_row",
                label="Delete Profile",
                type=SettingType.ROW,
                default=None,
                ratios=[80, 20],
                tooltip="Delete a specific saved browser profile used for Persistent Sessions (logs you out).",
                docs_path=DOCS_SYSTEM,
                docs_anchor="delete-profile",
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
                tooltip="Delete all saved browser profiles used for Persistent Sessions (Accounts + Legacy).",
                docs_path=DOCS_SYSTEM,
                docs_anchor="clear-all-profiles",
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
                docs_path=DOCS_SYSTEM,
                docs_anchor="config-storage-location-presets",
            ),
            SettingField(
                key="config_storage_custom_path",
                label="Custom Config Directory",
                type=SettingType.DIRECTORY,
                default="",
                tooltip="Absolute paths recommended. Relative paths resolve from the app folder.",
                validator=validate_directory_path,
                docs_path=DOCS_SYSTEM,
                docs_anchor="migrating-config-storage",
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
                docs_path=DOCS_API_BEHAVIOR,
                docs_anchor="request-queue-preview",
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
                docs_path=DOCS_CONSOLE,
                docs_anchor="logging-levels",
            ),
            SettingField(
                key="console_log_level",
                label="Console Window",
                type=SettingType.DROPDOWN,
                default="Debug",
                options=["Debug", "Success", "Info", "Warning", "Error"],
                tooltip="Minimum severity for messages shown in the Console Window.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="logging-levels",
            ),
            SettingField(
                key="mini_console_log_level",
                label="Mini-Console",
                type=SettingType.DROPDOWN,
                default="Success",
                options=["Debug", "Success", "Info", "Warning", "Error"],
                tooltip="Minimum severity for messages shown in the Activity Log (main window).",
                docs_path=DOCS_CONSOLE,
                docs_anchor="logging-levels",
            ),
            SettingField(
                key="logfile_log_level",
                label="Logfiles",
                type=SettingType.DROPDOWN,
                default="Debug",
                options=["Debug", "Success", "Info", "Warning", "Error"],
                tooltip="Minimum severity for messages written to log files.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="logging-levels",
            ),
        ]
    ),
    SettingCategory(
        name="Experimental",
        key="experimental",
        fields=[
            SettingField(
                key="providers_in_parallel",
                label="Providers in Parallel",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Experimental. Launch one browser per selected provider and route requests by "
                    "their model IDs. Applies on the next browser start and can use a lot of RAM."
                ),
                docs_path=DOCS_PROVIDERS_IN_PARALLEL,
            ),
            SettingField(
                key="providers_in_parallel_note",
                label="Providers in Parallel",
                type=SettingType.HINT,
                default=(
                    "This opens extra browser windows, keeps them idle in memory, and routes by "
                    "model IDs while active. Change the selection here, then restart the browser for it to take effect."
                ),
                tooltip=None,
                hint_variant="warn",
                visible_depends="experimental.providers_in_parallel",
                docs_path=DOCS_PROVIDERS_IN_PARALLEL,
            ),
            SettingField(
                key="parallel_enable_deepseek",
                label="DeepSeek",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include DeepSeek in the parallel browser pool.",
                visible_depends="experimental.providers_in_parallel",
                depends="providers_credentials.provider!=DeepSeek",
                force_when_dep_unmet=True,
                docs_path=DOCS_PROVIDERS_IN_PARALLEL,
            ),
            SettingField(
                key="parallel_enable_glm",
                label="GLM Chat",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include GLM Chat in the parallel browser pool.",
                visible_depends="experimental.providers_in_parallel",
                depends="providers_credentials.provider!=GLM Chat",
                force_when_dep_unmet=True,
                docs_path=DOCS_PROVIDERS_IN_PARALLEL,
            ),
            SettingField(
                key="parallel_enable_moonshot",
                label="Moonshot",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include Moonshot in the parallel browser pool.",
                visible_depends="experimental.providers_in_parallel",
                depends="providers_credentials.provider!=Moonshot",
                force_when_dep_unmet=True,
                docs_path=DOCS_PROVIDERS_IN_PARALLEL,
            ),
            SettingField(
                key="parallel_enable_qwen",
                label="QwenLM",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include QwenLM in the parallel browser pool.",
                visible_depends="experimental.providers_in_parallel",
                depends="providers_credentials.provider!=QwenLM",
                force_when_dep_unmet=True,
                docs_path=DOCS_PROVIDERS_IN_PARALLEL,
            ),
            SettingField(
                key="parallel_enable_aistudio",
                label="Google AI Studio",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Include Google AI Studio in the parallel browser pool.",
                visible_depends="experimental.providers_in_parallel",
                depends="providers_credentials.provider!=Google AI Studio",
                force_when_dep_unmet=True,
                docs_path=DOCS_PROVIDERS_IN_PARALLEL,
            ),
            SettingField(
                key="better_model_names",
                label="Better Model Names",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Use friendlier model IDs in /v1/models. Legacy IDs are still accepted.",
                docs_path=DOCS_BETTER_MODEL_NAMES,
                docs_anchor="enable-it",
            ),
            SettingField(
                key="classic_title",
                label="Classic Title Bar",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Use the classic title layout instead of the new logo + styled title.",
                affects=["title_bar"],
            ),
            SettingField(
                key="changelog_button",
                label="Changelog Button",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip=(
                    "Show the News bell button next to Help. "
                    "The button can show a red dot when new changelog/news items are available."
                ),
                affects=["news_button"],
            ),
            SettingField(
                key="enable_remote_control",
                label="Enable Remote Control",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Expose an opt-in HTML remote-control interface on the running API server. "
                    "Remote routes still respect the IP whitelist when enabled."
                ),
                docs_path=DOCS_REMOTE_CONTROL,
                docs_anchor="enable-it",
            ),
            SettingField(
                key="remote_control_password",
                label="Remote Control Password",
                type=SettingType.PASSWORD,
                default="",
                tooltip=(
                    "Optional password for the Remote Control interface. Leave blank to disable "
                    "password auth and rely on network restrictions only."
                ),
                depends="experimental.enable_remote_control",
                docs_path=DOCS_REMOTE_CONTROL,
                docs_anchor="passwords-and-tokens",
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
                tooltip="Check for available updates on GitHub.",
                docs_path=DOCS_SYSTEM,
                docs_anchor="updates",
            ),
            SettingField(
                key="check_for_updates_on_startup",
                label="Check for Updates on Startup",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Automatically check for updates when the app starts.",
                docs_path=DOCS_SYSTEM,
                docs_anchor="updates",
            ),
            SettingField(
                key="collapse_to_tray_on_close",
                label="Collapse to Tray (when closed)",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="When enabled, closing the main window hides it to the tray instead of exiting.",
            ),
            SettingField(
                key="enable_animations",
                label="Enable Animations",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip=(
                    "Enable non-essential UI animations. "
                ),
            ),
            SettingField(
                key="show_only_active_provider_behavior",
                label="Show Only Active Provider Behavior",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Only show the Behavior category for the currently selected Provider.",
            ),
            SettingField(
                key="paged_settings_view",
                label="Paged Settings View",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Show one category at a time. Use the sidebar to switch between them.",
            ),
            SettingField(
                key="hotswap_experience",
                label="Hotswap Experience",
                type=SettingType.DROPDOWN,
                default="Stop Menu",
                options=["Stop Menu", "Discrete", "Persistent Discrete"],
                tooltip=(
                    "How the Hotswap shortcut appears. "
                    "Stop Menu: in the Stop button dropdown. "
                    "Discrete: icon next to Help (while running). "
                    "Persistent Discrete: always visible."
                ),
                affects=["chevron_dropdown", "hotswap_button"],
                docs_path=DOCS_HOTSWAPS,
                docs_anchor="hotswap-experience",
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
                docs_path=DOCS_CONSOLE,
                docs_anchor="enabling-the-console",
            ),
            SettingField(
                key="log_to_main",
                label="Log to Main",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Also log to the Activity Log in the main window. Forced on if the console is disabled.",
                depends="console_settings.enable_console",
                force_when_dep_unmet=True,
                docs_path=DOCS_CONSOLE,
                docs_anchor="log-routing",
            ),
            SettingField(
                key="log_to_stdout",
                label="Log to Stdout",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Also log to stdout/terminal. Forced on if the console is disabled.",
                depends="console_settings.enable_console",
                force_when_dep_unmet=True,
                docs_path=DOCS_CONSOLE,
                docs_anchor="log-routing",
            ),
            SettingField(
                key="max_lines",
                label="Max Line Limit",
                type=SettingType.INTEGER,
                default=500,
                tooltip="Maximum number of lines to keep in the console history.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="console-appearance",
            ),
            SettingField(
                key="font_size",
                label="Font Size",
                type=SettingType.INTEGER,
                default=10,
                tooltip="Font size for the console text.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="console-appearance",
            ),
            SettingField(
                key="wrap_lines",
                label="Wrap Lines",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Soft-wrap long lines in the console window.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="console-appearance",
            ),
            SettingField(
                key="auto_scroll_mode",
                label="Auto-Scroll Mode",
                type=SettingType.DROPDOWN,
                default="Always",
                options=["Always", "Bottom only", "Never"],
                tooltip="Control how the console view follows new log messages.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="console-appearance",
            ),
            SettingField(
                key="color_palette",
                label="Color Palette",
                type=SettingType.DROPDOWN,
                default="Modern",
                options=["Modern", "Classic", "Bright"],
                tooltip="Choose a color scheme for log levels.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="color-palettes",
            ),
            SettingField(
                key="always_on_top",
                label="Always On Top",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Keep the console window on top of other windows.",
                docs_path=DOCS_CONSOLE,
                docs_anchor="console-appearance",
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
                docs_path=DOCS_CONSOLE,
                docs_anchor="dump-settings",
            ),
            SettingField(
                key="condump_directory",
                label="Condump Directory",
                type=SettingType.DIRECTORY,
                default=None,
                tooltip="Directory to write console dumps to. Leave blank to ask each time.",
                validator=validate_directory_path,
                nullable=True,
                docs_path=DOCS_CONSOLE,
                docs_anchor="dump-settings",
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
                docs_path=DOCS_NETWORK,
                docs_anchor="port",
            ),
            SettingField(
                key="available_on_lan",
                label="Available on LAN",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Make the API server accessible from other devices on the local network.",
                docs_path=DOCS_NETWORK,
                docs_anchor="lan-availability",
            ),
            SettingField(
                key="show_ip",
                label="Show IP",
                type=SettingType.BOOLEAN,
                default=True,
                tooltip="Print the server address(es) to the console when the API server starts.",
                docs_path=DOCS_NETWORK,
                docs_anchor="show-ip",
            ),
            SettingField(
                key="use_api_keys",
                label="Use API Keys",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Require an API key (Bearer) for incoming requests.",
                docs_path=DOCS_NETWORK,
                docs_anchor="api-keys",
            ),
            SettingField(
                key="api_keys",
                label="API Keys",
                type=SettingType.INPUT_PAIR,
                default=[],
                tooltip="List of API key name/value pairs.",
                alternative_actions=[
                    AlternativeAction(
                        name="Generate Key",
                        icon="dices.svg",
                        action="generate_api_key",
                    ),
                ],
                depends="network_settings.use_api_keys",
                required=True,
                docs_path=DOCS_NETWORK,
                docs_anchor="api-keys",
            ),
            SettingField(
                key="use_ip_whitelist",
                label="Use IP Whitelist",
                type=SettingType.BOOLEAN,
                default=False,
                tooltip="Only allow API requests from the listed IP addresses.",
                docs_path=DOCS_IP_WHITELIST,
                docs_anchor="how-to-use-it",
            ),
            SettingField(
                key="ip_whitelist",
                label="Whitelisted IPs",
                type=SettingType.INPUT_LIST,
                default=[],
                tooltip="List of IP addresses allowed to access the API.",
                validator=validate_ip_address_list,
                depends="network_settings.use_ip_whitelist",
                required=True,
                docs_path=DOCS_IP_WHITELIST,
                docs_anchor="how-to-use-it",
            ),
        ]
    ),
]
