---
icon: material/chat-processing
---

# :material-chat-processing: GLM Behavior

This page covers the toggles and options that control how IntenseRP interacts with **GLM Chat** (chat.z.ai).

!!! warning "Beta quality"
    The GLM driver is still somewhat beta-like. It is mostly usable for daily driving, but you may occasionally run into quirks or instability. For a deep dive into known quirks and timing settings, see [:material-wrench-clock: GLM Quirks](../advanced/glm-quirks.md).

---

## :material-tune: Modes (model IDs)

In IntenseRP Next v2, the `model` you select in SillyTavern is mostly a **mode selector**, not a true model picker.

For GLM, these model IDs map to simple behavior presets:

| Model ID | Behavior |
|---|---|
| `glm-auto` | Uses your IntenseRP settings |
| `glm-chat` | Forces Deep Think **off** and never emits `<think>` |
| `glm-reasoner` | Forces Deep Think **on** (Send Deep Think follows your setting) |

!!! tip "Better Model Names (Experimental)"
    If you enable **Settings -> Experimental -> Better Model Names**, the model IDs become base-model-style names like:

    - `glm-5-auto` / `glm-5` / `glm-5-think`

    The base (`glm-5`, `glm-4.7`, `glm-4.6`) depends on your **GLM Behavior -> Model** selection.
    Legacy IDs like `glm-auto` still work either way.

!!! note "About real GLM model selection"
    IntenseRP can also switch GLM's *real* model picker in the web UI.

    :material-arrow-right: **Settings** -> **GLM Behavior** -> **Model**

    Supported options:

    - **GLM-5** (recommended default)
    - **GLM-4.7**
    - **GLM-4.6**

    !!! tip "About GLM-4.6v"
        GLM-4.6v exists, but IntenseRP intentionally does **not** select it (quality reasons for roleplay).

    !!! warning "Fallback behavior"
        If your selected model is not present in the dropdown (UI changes / rollout), IntenseRP logs a warning and selects the **first available** model instead.

---

## :material-head-cog: Deep Think

Deep Think is GLM's reasoning mode. When enabled, GLM produces an internal reasoning trace before (or alongside) the final answer.

### Enable Deep Think

Toggles the Deep Think button in GLM's interface.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Enable Deep Think**

### Send Deep Think

When enabled, IntenseRP includes GLM's reasoning in the response, wrapped in `<think>` tags.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Send Deep Think**

---

## :material-magnify: Search

GLM Chat Search can be toggled via IntenseRP.

GLM streams internal tool/search payloads into the same response stream (wrapped in `<glm_block>...</glm_block>`). IntenseRP strips these blocks, so search results are **not sent** to the client.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Enable Search**

---

## :material-calculator: Count Tokens

GLM's backend reports token usage near the end of a response stream. When enabled, IntenseRP captures these values and returns them in the OpenAI-style `usage` fields (`prompt_tokens`, `completion_tokens`, `total_tokens`). This is enabled by default.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Count Tokens**

!!! note "Caching"
    Sometimes GLM reports cached prompt tokens as `usage.prompt_tokens_details.cached_tokens`.

---

## :material-file-upload: File Upload Mode

Instead of typing your message into GLM's chat box, IntenseRP can upload it as a text file attachment. This is useful for very long prompts that might hit input limits.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Send As Text File**

### File Upload Timeout

When uploading files, GLM can take a moment before the send button becomes active. This setting controls how long IntenseRP waits (in seconds) before giving up.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **File Upload Timeout**

Default is 15 seconds. Increase it if you're on a slow connection/PC or uploading very large prompts.

### Text File Filler

GLM won't let you send a file with an empty textbox as it needs *some* text alongside it. By default IntenseRP pastes a single `.` (dot) as filler, but you can change this to whatever you want.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Text File Filler**

This setting only appears when **Send As Text File** is enabled.

---

## :material-refresh: Clean Regeneration (known issues)

Clean Regeneration tries to keep chats tidy: when you send the exact same prompt twice in a row, IntenseRP clicks GLM's "Regenerate" instead of creating a brand new chat. This is done with the goal of reducing clutter in the chat history and generally just speeding up the workflow.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Clean Regeneration**

!!! warning "Known issue (GLM)"
    Clean Regeneration is currently unreliable with GLM Chat. The option may error out even though your request still completes normally.

    If you want to experiment with it anyway, try enabling **Refresh After Generation** under GLM Behavior -> Quirks. This reloads the page after each response and can sometimes restore the UI state so Regenerate becomes available again.

---

## :material-key: Login notes (CAPTCHA)

GLM requires a CAPTCHA during login. Even with Auto Login enabled, you must complete the CAPTCHA in the browser window, since it's not really possible to reliably automate that step.

!!! tip "Use Persistent Sessions"
    Persistent Sessions are strongly recommended for GLM. They help you avoid solving the CAPTCHA on every start.

See: [:material-key: Login & Sessions](login-sessions.md)

---

## :material-translate: UI language requirement

The GLM driver currently expects the GLM web UI language to be English (`en-US`). If GLM is set to another language, IntenseRP may fail to find buttons/toggles reliably.

If you see a warning about GLM UI language:

1. Change GLM language to **English (en-US)** in the GLM browser window
2. Reload the page (F5 / Ctrl+R)
3. Retry / restart the browser from IntenseRP if needed

---

## :material-code-tags: Per-message macros

You can add simple `[[...]]` macros to the *latest* user message in SillyTavern to override certain GLM Behavior settings for that request only.

All macros are stripped from the message before sending it to GLM.

| Macro | Effect |
|------|--------|
| `[[think]]`, `[[r1]]` | Force Deep Think on |
| `[[nothink]]`, `[[r0]]` | Force Deep Think off |
| `[[search]]` | Force Search on |
| `[[nosearch]]`, `[[no_search]]` | Force Search off |
| `[[file]]` | Force Send As Text File on |
| `[[nofile]]` | Force Send As Text File off |

!!! note "Search macros"
    Search macros like `[[search]]` / `[[nosearch]]` override the **Enable Search** setting for that request only.

!!! note "Scope"
    Only macros from the latest user message apply. They do not persist across requests.

---

## :material-wrench-clock: Quirks & Timing

GLM has a few quirks worth knowing about, that could look as broken (but really they can be pretty easy to work around). These are covered briefly on this page (see individual sections above), but if you want the full picture including all the timing knobs and workarounds:

:material-arrow-right: [:material-wrench-clock: GLM Quirks (full page)](../advanced/glm-quirks.md)

---

## :material-format-list-checks: Quick Reference

| Setting | What It Does | Default |
|---------|--------------|---------|
| **Model** | Selects GLM's real model picker (UI) | GLM-5 |
| **Enable Deep Think** | Toggles GLM reasoning mode | Off |
| **Send Deep Think** | Includes thinking in response | Off |
| **Count Tokens** | Returns token usage in API responses | On |
| **Enable Search** | Enables GLM search | Off |
| **Send As Text File** | Uploads prompt as .txt | Off |
| **File Upload Timeout** | Seconds to wait for upload | 15 |
| **Text File Filler** | Text pasted alongside the uploaded file | `.` |
| **Clean Regeneration** | Regenerates on duplicate prompts | Off (unstable for GLM) |
| **Refresh After Generation** | Reloads the GLM page after each response | Off |

---

## :material-arrow-left: Back to Features

[:material-arrow-left: Features Overview](../features.md)
