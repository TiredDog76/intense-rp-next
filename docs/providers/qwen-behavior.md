---
icon: providers/qwen
---

# :providers-qwen: QwenLM Behavior

This page covers the toggles and options that control how IntenseRP interacts with **QwenLM** (`chat.qwen.ai`).

---

## :material-tune: Modes (model IDs)

In IntenseRP Next v2, the `model` you select in SillyTavern is mostly a **mode selector**, not a true model picker.

For QwenLM, these model IDs map to simple behavior presets:

| Model ID | Behavior |
|---|---|
| `qwen-auto` | Uses your IntenseRP settings |
| `qwen-chat` | Forces Thinking **off** and never emits `<think>` |
| `qwen-reasoner` | Forces Thinking **on** (Send Thinking follows your setting) |

!!! tip "Better Model Names (Experimental)"
    If you enable **Settings -> Experimental -> Better Model Names**, the model IDs become base-model-style names like:

    - `qwen3.5-plus-auto` / `qwen3.5-plus` / `qwen3.5-plus-think`

    The base depends on your **QwenLM Behavior -> Model** selection.
    Legacy IDs like `qwen-auto` still work either way.

---

## :material-chip: Real Qwen model selection (web UI)

IntenseRP can also switch QwenLM's *real* model picker in the web UI:

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Model**

The list is intentionally "what Qwen shows in the dropdown". If your selected model is missing (UI rollout / region / UI change), IntenseRP logs a warning and keeps going.

---

## :material-head-cog: Thinking

QwenLM exposes three thinking modes in the web UI: **Auto**, **Thinking**, and **Fast**.

IntenseRP keeps it simple:

- **Enable Thinking** -> selects **Thinking**
- Thinking disabled -> selects **Fast**

### Enable Thinking

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Enable Thinking**

### Send Thinking

When enabled, IntenseRP includes QwenLM's thinking *summaries* in the response, wrapped in `<think>` tags.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Send Thinking**

!!! note "Thinking content"
    QwenLM sends a short thinking summary stream. This is what IntenseRP forwards (not hidden internal chain-of-thought).

---

## :material-magnify: Search

QwenLM Web search can be toggled via IntenseRP.

Qwen streams tool/search payloads into the same response stream. For stability, IntenseRP strips these tool payloads, so search results are **not sent** to the client.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Enable Search**

---

## :material-calculator: Count Tokens

QwenLM reports token usage during the response stream. When enabled, IntenseRP captures those values and returns them in the OpenAI-style `usage` fields (`prompt_tokens`, `completion_tokens`, `total_tokens`). This is enabled by default.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Count Tokens**

---

## :material-file-upload: File Upload Mode

Instead of typing your message into QwenLM's chat box, IntenseRP can upload it as a text file attachment. This is useful for very long prompts that might hit input limits.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Send As Text File**

!!! warning "QwenLM file uploads are flaky"
    QwenLM does not handle files very reliably right now. If you are sending important context (system prompts, lore, character sheets), you will usually get better results by keeping File Upload Mode **off** and sending plain text instead.

### Text File Message

Optional text that IntenseRP pastes into QwenLM *alongside* the uploaded file.

Leave it empty to send a file-only message.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Text File Message**

!!! info "Helps a lot"
    QwenLM treats files as attachments rather than part of the message content, so it can be helpful to include a short message like "Context attached, please read it before answering" to make sure the model knows to look at the file.

### File Upload Timeout

After uploading, the send button can take a moment to become available. This setting controls how long IntenseRP waits (in seconds) before giving up.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **File Upload Timeout**

### Message Send Timeout

QwenLM doesn't render the send button until there's something to send (typed text or an uploaded file). This timeout controls how long IntenseRP waits for the send button to appear in normal (non-file) mode.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Message Send Timeout (s)**

---

## :material-shield-check: Provider guardrails (recommended)

QwenLM has a couple of web settings that can silently change how your prompt gets sent (for example, turning big messages into file attachments).

To keep things predictable, IntenseRP tries to auto-disable these when the driver starts:

- Large Text as File
- Split Large Chunks
- Memory
- History Memory

If any of those get changed, you might see the Qwen tab reload once. That is normal.

---

## :material-refresh: Clean Regeneration

Clean Regeneration tries to keep chats tidy: when you send the exact same prompt twice in a row, IntenseRP clicks Qwen's "Regenerate" instead of creating a brand new chat. Especially useful if you swipe a lot in SillyTavern and want to hit ratelimits less.

:material-arrow-right: **Settings** -> **QwenLM Behavior** -> **Clean Regeneration**

!!! tip "Multi-Slot Cache"
    QwenLM also supports **QwenLM Behavior** -> **Multi-Slot Cache**.

    That keeps up to 7 older cached Qwen chats per account, so IntenseRP can reopen a matching older conversation and regenerate there instead of only checking the most recent one.

---

## :material-key: Login notes

QwenLM supports Auto Login (email + password). Persistent Sessions are still recommended, since they reduce how often you need to log in.

See: [:material-key: Login & Sessions](../features/login-sessions.md)

---

## :material-translate: UI language requirement

The QwenLM driver currently expects the Qwen web UI language to be English (`en` / `en-US`). If QwenLM is set to another language, IntenseRP may fail to find buttons/toggles reliably.

If you see a warning about QwenLM UI language:

1. Change QwenLM language to **English**
2. Reload the page (F5 / Ctrl+R)
3. Retry / restart the browser from IntenseRP if needed

---

## :material-code-tags: Per-message macros

You can add simple `[[...]]` macros to the *latest* user message in SillyTavern to override certain QwenLM Behavior settings for that request only.

All macros are stripped from the message before sending it to QwenLM.

| Macro | Effect |
|------|--------|
| `[[think]]`, `[[r1]]` | Force Thinking on |
| `[[nothink]]`, `[[r0]]` | Force Thinking off |
| `[[search]]` | Force Search on |
| `[[nosearch]]`, `[[no_search]]` | Force Search off |
| `[[file]]` | Force Send As Text File on |
| `[[nofile]]` | Force Send As Text File off |

!!! note "Scope"
    Only macros from the latest user message apply. They do not persist across requests.

---

## :material-format-list-checks: Quick Reference

| Setting | What It Does | Default |
|---------|--------------|---------|
| **Model** | Selects QwenLM's real model picker (UI) | Qwen3.5-Plus |
| **Enable Thinking** | Switches QwenLM into Thinking (vs Fast) | Off |
| **Send Thinking** | Includes thinking summaries in response | Off |
| **Count Tokens** | Returns token usage in API responses | On |
| **Enable Search** | Enables QwenLM Web search | Off |
| **Send As Text File** | Uploads prompt as .txt | Off |
| **Text File Message** | Text pasted alongside uploaded file | (empty) |
| **File Upload Timeout** | Seconds to wait after upload | 20 |
| **Message Send Timeout (s)** | Seconds to wait for send button | 8 |
| **Clean Regeneration** | Regenerates on duplicate prompts | Off |

---

## :material-arrow-left: Back to Providers

[:material-arrow-left: Providers Overview](../providers.md)
