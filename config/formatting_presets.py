"""Built-in formatting preset definitions shared by the UI and migrators."""

FORMATTING_PRESET_TEMPLATES = {
    "Classic - Name": "{{name}}: {{content}}",
    "Classic - Role": "{{role}}: {{content}}",
    "XML-Like - Name": "<{{name}}>{{content}}</{{name}}>",
    "XML-Like - Role": "<{{role}}>{{content}}</{{role}}>",
    "Multiline XML-Like - Name": "<{{name}}>\n{{content}}\n</{{name}}>",
    "Multiline XML-Like - Role": "<{{role}}>\n{{content}}\n</{{role}}>",
    "Divided - Name": "### {{name}}\\n{{content}}",
    "Divided - Role": "### {{role}}\\n{{content}}",
}

FORMATTING_PRESET_OPTIONS = [
    *FORMATTING_PRESET_TEMPLATES.keys(),
    "Custom",
]

LEGACY_V2_FORMATTING_PRESET_MAP = {
    "Classic": "Classic - Name",
    "XML-Like": "XML-Like - Name",
    "Divided": "Divided - Name",
}

V1_FORMATTING_PRESET_MAP = {
    "Classic (Name)": "Classic - Name",
    "Classic (Role)": "Classic - Role",
    # v1 "Wrapped" was the older multiline XML-style preset.
    "Wrapped (Name)": "Multiline XML-Like - Name",
    "Wrapped (Role)": "Multiline XML-Like - Role",
    "Divided (Name)": "Divided - Name",
    "Divided (Role)": "Divided - Role",
    "Custom": "Custom",
}
