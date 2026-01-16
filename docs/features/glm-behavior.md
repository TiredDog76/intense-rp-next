---
icon: material/chat-processing
---

# :material-chat-processing: GLM Behavior

This page covers the toggles and options that control how IntenseRP interacts with **GLM Chat** (chat.z.ai).

!!! warning "Beta quality"
    The GLM driver is still somewhat beta-like. It is mostly usable for daily driving, but you may occasionally run into quirks or instability.

---

## :material-tune: Modes (model IDs)

In IntenseRP Next v2, the `model` you select in SillyTavern is mostly a **mode selector**, not a true model picker.

For GLM, these model IDs map to simple behavior presets:

| Model ID | Behavior |
|---|---|
| `glm-auto` | Uses your IntenseRP settings |
| `glm-chat` | Forces Deep Think **off** and never emits `<think>` |
| `glm-reasoner` | Forces Deep Think **on** (Send Deep Think follows your setting) |

!!! note "About real GLM model selection"
    For now, IntenseRP only drives **GLM-4.7**. Support for selecting other GLM models (like GLM-4.6 / 4.6v) is planned, but not implemented yet.

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

## :material-file-upload: File Upload Mode

Instead of typing your message into GLM's chat box, IntenseRP can upload it as a text file attachment. This is useful for very long prompts that might hit input limits.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Send As Text File**

### File Upload Timeout

When uploading files, GLM can take a moment before the send button becomes active. This setting controls how long IntenseRP waits (in seconds) before giving up.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **File Upload Timeout**

Default is 15 seconds. Increase it if you're on a slow connection/PC or uploading very large prompts.

---

## :material-refresh: Clean Regeneration (known issues)

Clean Regeneration tries to keep chats tidy: when you send the exact same prompt twice in a row, IntenseRP clicks GLM's "Regenerate" instead of creating a brand new chat. This is done with the goal of reducing clutter in the chat history and generally just speeding up the workflow.

:material-arrow-right: **Settings** -> **GLM Behavior** -> **Clean Regeneration**

!!! warning "Known issue (GLM)"
    Clean Regeneration is currently unreliable with GLM Chat. The option may error out even though your request still completes normally. If this annoys you, keep it disabled for GLM for now.

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

## :material-format-list-checks: Quick Reference

| Setting | What It Does | Default |
|---------|--------------|---------|
| **Enable Deep Think** | Toggles GLM reasoning mode | Off |
| **Send Deep Think** | Includes thinking in response | Off |
| **Enable Search** | Enables GLM search | Off |
| **Send As Text File** | Uploads prompt as .txt | Off |
| **File Upload Timeout** | Seconds to wait for upload | 15 |
| **Clean Regeneration** | Regenerates on duplicate prompts | Off (unstable for GLM) |

---

## :material-arrow-left: Back to Features

[:material-arrow-left: Features Overview](../features.md)
