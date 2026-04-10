---
icon: providers/zai
---

# :providers-zai: GLM Behavior

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

!!! note "About real GLM model selection"
    IntenseRP can also switch GLM's *real* model picker in the web UI.

    :material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Model**

    Supported options:

    - **GLM-5.1** (recommended for rp)
    - **GLM-5-Turbo**
    - **GLM-5V-Turbo**
    - **GLM-5**
    - **GLM-4.7**

    !!! warning "Fallback behavior"
        If your selected model is not present in the dropdown (UI changes / rollout), IntenseRP logs a warning and selects the **first available** model instead.

---

## :material-head-cog: Deep Think

Deep Think is GLM's reasoning mode. When enabled, GLM produces an internal reasoning trace before (or alongside) the final answer.

### Enable Deep Think

Toggles the Deep Think button in GLM's interface.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Enable Deep Think**

### Send Deep Think

When enabled, IntenseRP includes GLM's reasoning in the response, wrapped in `<think>` tags.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Send Deep Think**

---

## :material-magnify: Search

GLM Chat Search can be toggled via IntenseRP.

GLM streams internal tool/search payloads into the same response stream (wrapped in `<glm_block>...</glm_block>`). IntenseRP strips these blocks, so search results are **not sent** to the client.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Enable Search**

---

## :material-calculator: Count Tokens

GLM's backend reports token usage near the end of a response stream. When enabled, IntenseRP captures these values and returns them in the OpenAI-style `usage` fields (`prompt_tokens`, `completion_tokens`, `total_tokens`). This is enabled by default.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Count Tokens**

!!! note "Caching"
    Sometimes GLM reports cached prompt tokens as `usage.prompt_tokens_details.cached_tokens`.

---

## :material-file-upload: File Upload Mode

Instead of typing your message into GLM's chat box, IntenseRP can upload it as a text file attachment. This is useful for very long prompts that might hit input limits.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Send As Text File**

### File Upload Timeout

When uploading files, GLM can take a moment before the send button becomes active. This setting controls how long IntenseRP waits (in seconds) before giving up.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **File Upload Timeout**

Default is 15 seconds. Increase it if you're on a slow connection/PC or uploading very large prompts.

### Text File Filler

GLM won't let you send a file with an empty textbox as it needs *some* text alongside it. By default IntenseRP pastes a single `.` (dot) as filler, but you can change this to whatever you want.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Text File Filler**

This setting only appears when **Send As Text File** is enabled.

---

## :material-refresh: Reuse Matching Chat

Reuse Matching Chat tries to keep chats tidy: when you send the exact same prompt twice in a row, IntenseRP clicks GLM's "Regenerate" instead of creating a brand new chat. This is done with the goal of reducing clutter in the chat history and generally just speeding up the workflow.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Reuse Matching Chat**

!!! note "Pick one"
    On GLM, you can use either **Reuse Matching Chat** (+ optional **Search Older Matching Chats**) or **Repetition Buster**.

    They are opposite strategies, so IntenseRP only uses one of them at a time.

!!! warning "Known issue (GLM)"
    Reuse Matching Chat is currently unreliable with GLM Chat. The option may error out even though your request still completes normally.

    If you want to experiment with it anyway, try enabling **Refresh After Generation** under **Settings -> Provider Behavior -> GLM Chat -> Quirks**. This reloads the page after each response and can sometimes restore the UI state so Regenerate becomes available again.

!!! tip "Search Older Matching Chats"
    GLM also supports **Provider Behavior** -> **GLM Chat** -> **Search Older Matching Chats**.

    That lets IntenseRP keep up to 7 older cached GLM chats per account and try reopening one of those when the current prompt matches.

    Same point as above, though: if GLM's regenerate UI is being annoying that day, **Search Older Matching Chats** inherits the same annoyance because it still depends on the Regenerate button working.

### :material-shuffle-variant: Repetition Buster

Repetition Buster is basically the opposite of **Reuse Matching Chat**.

Instead of trying to reuse the same chat, IntenseRP checks whether the current prompt matches the **immediately previous** one for the active GLM account/profile. That last-prompt memory is kept across restarts, because GLM's own caching can survive them too. If it matches, IntenseRP opens a throwaway fresh chat, sends a random **128-character** string there, and then opens another fresh chat for your real prompt.

That random string is just a cache buster. The whole idea is to disturb GLM's context caching before the real request goes out, which can help if you're worried about suspiciously repetitive duplicate generations.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Repetition Buster**

!!! note "No Search Older Matching Chats here"
    **Search Older Matching Chats** only works with **Reuse Matching Chat**, because it reopens an older chat and presses **Regenerate** there.

    Repetition Buster does the opposite. It intentionally burns one throwaway chat and then starts another brand new one for the real request.

---

## :material-delete-clock-outline: Delete Chat After Reply

If you want GLM's chat history cleaned up automatically, IntenseRP can delete the completed GLM chat after a successful reply finishes.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **GLM Chat** -> **Delete Chat After Reply**

!!! warning "Slower requests"
    This adds extra cleanup work after each request, so it can slow requests down quite a bit.

!!! note "No Reuse Matching Chat here"
    This does **not** work together with **Reuse Matching Chat** or **Search Older Matching Chats**.

!!! tip "Repetition Buster still works"
    GLM's **Repetition Buster** is still compatible with this.

    IntenseRP deletes the temporary cache-buster chat too before it sends the real request.

See also: [:material-delete-clock-outline: Chat Auto-Deletion](../features/chat-auto-deletion.md)

---

## :material-key: Login notes (CAPTCHA)

GLM requires a CAPTCHA during login. Even with Auto Login enabled, you must complete the CAPTCHA in the browser window, since it's not really possible to reliably automate that step.

!!! tip "Use Persistent Sessions"
    Persistent Sessions are strongly recommended for GLM. They help you avoid solving the CAPTCHA on every start.

See: [:material-key: Login & Sessions](../features/login-sessions.md)

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
| **Reuse Matching Chat** | Regenerates on duplicate prompts | Off (unstable for GLM) |
| **Delete Chat After Reply** | Deletes the completed GLM chat after a successful reply | Off |
| **Repetition Buster** | Sends a throwaway cache-buster prompt before duplicate prompts | Off |
| **First Chunk Timeout** | Seconds to wait for the response stream to start | 45 |
| **Refresh After Generation** | Reloads the GLM page after each response | Off |

---

## :material-arrow-left: Back to Providers

[:material-arrow-left: Providers Overview](../providers.md)
