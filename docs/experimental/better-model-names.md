---
icon: material/tag-text-outline
---

# :material-tag-text-outline: Better Model Names (Experimental)

IntenseRP has always used the OpenAI `model` field as a **behavior preset** (mode selector).

Historically that looked like:

- `deepseek-auto` / `deepseek-chat` / `deepseek-reasoner`
- `glm-auto` / `glm-chat` / `glm-reasoner`
- `moonshot-auto` / `moonshot-chat` / `moonshot-reasoner`
- `qwen-auto` / `qwen-chat` / `qwen-reasoner`
- `aistudio-auto` / `aistudio-chat` / `aistudio-reasoner`

That works, but it can get a bit confusing once you start thinking in terms of "real" models (especially for GLM, where you can pick between multiple models in Settings).

The **Better Model Names** experimental setting changes the *names* you see in `GET /v1/models` to be closer to the base model names you're actually using.

!!! warning "Experimental"
    This setting can change and may be removed/reworked.

    If you enable it, consider keeping a backup of your `[config_dir]` (Settings -> System -> Backup & Restore).

---

## :material-toggle-switch: Enable it

:material-arrow-right: **Settings** -> **Experimental** -> **Better Model Names**

This takes effect immediately for `GET /v1/models` (no restart required).

---

## :material-tag: New suffix rules

Better Model Names uses these suffixes:

- **(no suffix)** = legacy `-chat` (forces reasoning/thinking off)
- **`-think`** = legacy `-reasoner` (forces reasoning/thinking on)
- **`-auto`** = legacy `-auto` (uses your IntenseRP settings)

So a "mode trio" now looks like:

- `some-base-model-auto`
- `some-base-model`
- `some-base-model-think`

---

## :material-api: Provider mapping

### :material-brain: DeepSeek

Base model name:

- `deepseek-v3.2`

Model IDs:

| Model ID | Behavior |
|---|---|
| `deepseek-v3.2-auto` | Uses your IntenseRP settings |
| `deepseek-v3.2` | Forces DeepThink off |
| `deepseek-v3.2-think` | Forces DeepThink on |

### :material-meteor: Moonshot (Kimi)

Base model name:

- `kimi-k2.5`

Model IDs:

| Model ID | Behavior |
|---|---|
| `kimi-k2.5-auto` | Uses your IntenseRP settings |
| `kimi-k2.5` | Forces Thinking off |
| `kimi-k2.5-think` | Forces Thinking on |

### :material-chat-processing: GLM Chat

GLM is a bit special because it has **real model selection** in the web UI:

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Model**

Supported base models:

- `glm-4.6`
- `glm-4.7`
- `glm-5`

When Better Model Names is enabled, `GET /v1/models` uses the base model that matches your current GLM selection.

Example (if you selected **GLM-5** in Settings):

| Model ID | Behavior |
|---|---|
| `glm-5-auto` | Uses your IntenseRP settings |
| `glm-5` | Forces Deep Think off |
| `glm-5-think` | Forces Deep Think on |

!!! tip "If you switch GLM models often"
    If you use the Better Model Names IDs, you may need to update the selected model in your client after changing **GLM Behavior -> Model** (because the base name changes).

    If you want stable IDs that never change, keep using the legacy `glm-auto` / `glm-chat` / `glm-reasoner` names.

### :material-chat: QwenLM

QwenLM also has **real model selection** in the web UI:

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Model**

When Better Model Names is enabled, `GET /v1/models` uses the base model that matches your current QwenLM selection.

Example (if you selected **Qwen3.5-Plus** in Settings):

| Model ID | Behavior |
|---|---|
| `qwen3.5-plus-auto` | Uses your IntenseRP settings |
| `qwen3.5-plus` | Forces Thinking off |
| `qwen3.5-plus-think` | Forces Thinking on |

!!! tip "If you switch Qwen models often"
    If you use the Better Model Names IDs, you may need to update the selected model in your client after changing **QwenLM Behavior -> Model** (because the base name changes).

    If you want stable IDs that never change, keep using the legacy `qwen-auto` / `qwen-chat` / `qwen-reasoner` names.

### :material-image-auto-adjust: Google AI Studio

Google AI Studio also has **real Gemini model selection** in the web UI:

:material-arrow-right: **Settings** -> **Google AI Studio Behavior** -> **Model**

When Better Model Names is enabled, `GET /v1/models` uses the base model that matches your current Google AI Studio selection.

Example (if you selected **Gemini 2.5 Flash** in Settings):

| Model ID | Behavior |
|---|---|
| `gemini-2.5-flash-auto` | Uses your IntenseRP settings |
| `gemini-2.5-flash` | Uses AI Studio's chat-like behavior preset |
| `gemini-2.5-flash-think` | Uses AI Studio's reasoner-like behavior preset |

!!! tip "If you switch Gemini models often"
    If you use the Better Model Names IDs, you may need to update the selected model in your client after changing **Google AI Studio Behavior -> Model** (because the base name changes).

    If you want stable IDs that never change, keep using the legacy `aistudio-auto` / `aistudio-chat` / `aistudio-reasoner` names.

---

## :material-shield-check: Compatibility

- IntenseRP **still accepts the legacy IDs** (`deepseek-auto`, `glm-chat`, `moonshot-reasoner`, etc.).
- This setting only changes what you see in `GET /v1/models` (and what your client will typically offer in its model dropdown).

If something doesn't work after enabling this, you can simply disable the setting and go back to the legacy names.
