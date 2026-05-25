---
icon: providers/huggingface
---

# :providers-huggingface: HuggingChat Behavior

This page covers the HuggingChat essentials and specifics, such as real model selection, inference provider hints, thinking effort, Exa search, prompt uploads, chat reuse, and the tiny monthly credit pool that makes account rotation worth caring about.

HuggingChat is one of the more fiddly providers because IntenseRP is driving the **web UI** at `huggingface.co/chat`, not a clean token API. It can work very nicely, but it also has a few weird moments. This page is here to make those moments less weird.

!!! warning "Not the Hugging Face Inference API"
    This provider uses your Hugging Face account in the HuggingChat browser UI. It is **not** the paid/token-based Hugging Face Inference API.

    The upside is that it works like the other IntenseRP providers: saved accounts, persistent browser sessions, queueing, chat reuse, account rotation, and the same OpenAI-compatible `/v1/chat/completions` surface.

    And the downside is that you don't get control over roles and sampling parameters, and you have to deal with the quirks of automating a web UI instead of talking to a clean API.

---

<a id="limits-and-account-rotation"></a>

## :material-login: Login and credits

HuggingChat supports Auto Login with a Hugging Face **username or email** plus password.

:material-arrow-right: **Settings** -> **Provider and Login** -> **Sign-In and Accounts**

Persistent Sessions are strongly recommended. If the browser profile stays signed in, you avoid most login weirdness and can spend more time actually using the models instead of logging in.

HuggingChat's monthly model credits are **extremely** small:

| Account type | Monthly HuggingChat credits |
|---|---:|
| Free | `$0.1` |
| Pro | `$2` |

!!! tip "For comparison..."
    You can run out of free limits in just ~8-10 turns with something like DeepSeek-V4 or GLM-5.1. So you're going to need **A LOT** of accounts for anything serious.

When an account runs out, HuggingChat usually shows **Upgrade Required** and stops sending messages from that account until the quota resets.

If you have multiple Hugging Face accounts, the practical setup is to

1. Add them in **Credential Manager** under HuggingChat.
2. Enable **Retry With Another Account** if you want IntenseRP to rotate after early quota failures.
3. Enable **Auto-Disable Rate-Limited Accounts** if you want IntenseRP to disable the current saved account when HuggingChat shows **Upgrade Required**.
4. Re-enable spent accounts later after their credits reset.

Disabled accounts stay visible in Credential Manager, but IntenseRP will skip them for login and retry rotation.

---

## :material-tune: Modes (model IDs)

In SillyTavern, the `model` value is mostly a **behavior preset**, not the real HuggingChat model picker.

| Model ID | Behavior |
|---|---|
| `huggingchat-auto` | Uses your HuggingChat Behavior settings |
| `huggingchat-chat` | Forces Thinking off and never emits `<think>` |
| `huggingchat-reasoner` | Forces Thinking on; **Send Thinking** still controls whether `<think>` is forwarded |

If **Universal Model Names** is enabled, IntenseRP can also expose cached real HuggingChat model IDs with the same `-auto`, `-chat`, and `-reasoner` suffixes.

!!! note "Behavior preset vs real model"
    `huggingchat-reasoner` means that it'll use HuggingChat with Thinking enabled, then apply whatever real model is configured or requested.

---

## :material-chip: Real HuggingChat model selection (web UI)

IntenseRP can switch HuggingChat's real model picker in the web UI:

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Model**

The default, **Current HuggingChat selection**, means IntenseRP leaves the currently selected HuggingChat model alone. If you choose a specific model, IntenseRP tries to apply it before each request when needed.

The model list is cached after a successful HuggingChat login. This lets Settings and `/v1/models` show HuggingChat model IDs without scraping the page on every request.

!!! info "Why the cache is still checked against the page"
    The cache is only a list of possible model labels. Before IntenseRP skips a model action, it still compares the current UI model so it does not blindly trust stale state.

---

## :material-router-network: Inference Provider

Some HuggingChat models expose an inference provider selector.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Inference Provider**

`auto` is the safe default. If you know the provider value HuggingChat expects, you can enter values such as `together`, `fireworks-ai`, or `featherless-ai`.

IntenseRP does not fetch a provider list ahead of time. If the selected model does not expose the provider selector, or the requested provider is not available, the driver skips that step or falls back to `auto` where possible.

API requests can override the provider for one request:

```json
{
  "inference_provider": "together"
}
```

This HuggingChat-prefixed form is also accepted:

```json
{
  "huggingchat_inference_provider": "together"
}
```

---

## :material-head-cog: Thinking Effort

HuggingChat's thinking control is model-dependent. Some models expose a composer-level **Thinking Effort** menu, and some models simply don't.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Enable Thinking**

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Thinking Effort**

Supported configured values are `auto`, `default`, `low`, `medium`, and `high`.

- `auto` leaves HuggingChat's effort alone.
- `default` tries to reset thinking effort to HuggingChat's default/off behavior.
- `low`, `medium`, and `high` request those HuggingChat effort levels when the model exposes them.

If the selector is missing, IntenseRP logs a warning and keeps going. That usually means the selected model doesn't support the control.

### Send Thinking

When **Send Thinking** is enabled, IntenseRP forwards HuggingChat `<think>...</think>` text to the API client. When it's disabled, IntenseRP strips those blocks from the incremental stream and from the final fallback text.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Send Thinking**

!!! tip "API reasoning_effort"
    If **Accept API Reasoning Effort** includes HuggingChat, `reasoning_effort=low`, `medium`, or `high` maps to HuggingChat thinking effort for that request. Unlike some providers, HuggingChat has a real `low` option, so `low` still means Thinking is enabled.

API requests can also set:

```json
{
  "huggingchat_thinking_effort": "medium"
}
```

---

## :material-magnify: Search

HuggingChat search uses the Exa MCP server from the HuggingChat UI.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Enable Search**

For stability, IntenseRP filters search/tool payloads and only forwards assistant answer text. The final answer may still contain search-informed wording or citations if HuggingChat includes them in normal assistant text.

---

## :material-text-box-edit: System Prompt Field

HuggingChat has a custom system prompt field in its model settings UI.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Use System Prompt Field**

When enabled, IntenseRP moves leading API `system` messages into that field, but only when **Paste Leading System Messages** is also enabled.

When disabled, IntenseRP does **not** use HuggingChat's custom field. Leading system messages stay in the normal formatted prompt instead, which is simpler and avoids touching HuggingChat's model settings UI for no reason.

!!! note "Leading only"
    Only leading `system` messages are eligible for the HuggingChat system field. Mid-chat `system` messages stay in the normal prompt because the separate field is global to the chat/model settings, not a message-by-message feature.

---

## :material-file-upload: File Upload Mode

Instead of pasting a long prompt into HuggingChat's textarea, IntenseRP can upload the prompt as a `.txt` attachment.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Send As Text File**

This is useful for long prompts that behave better as files, but normal text mode is still simpler for everyday use.

### Text File Message

HuggingChat needs some text alongside a file upload. IntenseRP pastes this companion message after the file is accepted:

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Text File Message**

Default:

```text
Please read the attached file and respond to it.
```

### File Upload Timeout

Controls how long IntenseRP waits for HuggingChat's send button to become available after a file upload.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **File Upload Timeout**

Default is `20` seconds.

### File Upload Settle Delay

After the file chooser returns, HuggingChat can still need a moment before the file is really attached to the composer. This setting controls the short pause before IntenseRP pastes the companion text.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **File Upload Settle Delay (s)**

Default is `3.0` seconds. If HuggingChat ever sends the companion text before the file appears, raise this a little.

### Message Send Timeout

In normal non-file mode, this controls how long IntenseRP waits for the send button after filling the chat textarea.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Message Send Timeout (s)**

Default is `8` seconds.

---

<a id="clean-regeneration"></a>

## :material-refresh: Reuse Matching Chat

Reuse Matching Chat is the setting that makes SillyTavern swipes behave like regenerations instead of new chat creations.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Reuse Matching Chat**

When the new prompt and important HuggingChat request state match the cached last chat, IntenseRP tries to reopen/use that chat and press HuggingChat's **Retry** button instead of creating a brand new chat.

The cache compares the prompt plus state that can change the response path:

- real HuggingChat model
- inference provider
- thinking effort
- search state
- file-upload mode
- system prompt field usage and content

!!! tip "Search Older Matching Chats"
    HuggingChat also supports **Search Older Matching Chats**.

    When enabled, IntenseRP keeps up to 7 reusable cached HuggingChat conversations per account/profile. If one of those older chats matches the current prompt/settings, it reopens that conversation and presses **Retry** there.

!!! warning "Reuse needs the chat to still exist"
    **Delete Chat After Reply** and **Reuse Matching Chat** are intentionally incompatible. If the chat was deleted, there is nothing left to retry.

---

## :material-delete-clock-outline: Delete Chat After Reply

If you want HuggingChat's chat list cleaned up automatically, IntenseRP can delete the completed conversation after a successful reply.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **HuggingChat** -> **Delete Chat After Reply**

This uses HuggingChat's same-session conversation delete endpoint after the response finishes.

!!! warning "Slower requests"
    This adds extra cleanup work after each request, so it can slow things down.

!!! note "No chat reuse here"
    This does **not** work together with **Reuse Matching Chat** or **Search Older Matching Chats**.

See also: [:material-delete-clock-outline: Chat Auto-Deletion](../features/chat-auto-deletion.md)

---

<a id="quirks"></a>

## :material-wrench-clock: Quirks and Timing

HuggingChat UI actions are not instant. IntenseRP waits after model selection, search/MCP toggles, uploads, sends, and retries so the page has time to settle.

If HuggingChat is slow on your machine or connection, raise the relevant timeout instead of assuming the whole provider is cooked:

| Setting | Default | What it controls |
|---|---:|---|
| **Completion Request Timeout** | `150` seconds | How long to wait after Send/Retry for HuggingChat's backend request |
| **First Chunk Timeout** | `150` seconds | How long to wait for answer text after the request starts |
| **Model Apply Timeout** | `20` seconds | How long to wait while applying model settings |
| **Post-Action Delay** | `0.35` seconds | Small pause after UI actions |
| **File Upload Settle Delay** | `3.0` seconds | Pause after upload before pasting the companion message |

The driver expects the HuggingChat page language to be English (`en` / `en-US`). If the page reports another language, IntenseRP stops before automation starts clicking the wrong thing.

---

## :material-code-tags: Per-message macros

You can add `[[...]]` macros to the latest user message to override HuggingChat behavior for that request only. IntenseRP strips the macro before sending the prompt.

| Macro | Effect |
|------|--------|
| `[[think]]`, `[[r1]]` | Force Thinking on |
| `[[nothink]]`, `[[r0]]` | Force Thinking off |
| `[[search]]` | Force Search on |
| `[[nosearch]]`, `[[no_search]]` | Force Search off |
| `[[file]]` | Force Send As Text File on |
| `[[nofile]]` | Force Send As Text File off |

!!! note "Scope"
    Macros only apply to the latest request. They don't change your saved HuggingChat Behavior settings.

---

## :material-format-list-checks: Quick Reference

| Setting | What It Does | Default |
|---|---|---|
| **Model** | Selects HuggingChat's real web UI model picker | Current HuggingChat selection |
| **Inference Provider** | Optionally selects a HuggingChat inference provider | `auto` |
| **Auto-Disable Rate-Limited Accounts** | Disables the active saved account when HuggingChat shows Upgrade Required | Off |
| **Enable Thinking** | Uses HuggingChat's thinking effort selector when available | Off |
| **Thinking Effort** | Selects `auto`, `default`, `low`, `medium`, or `high` | `auto` |
| **Send Thinking** | Forwards `<think>` text to the API client | Off |
| **Enable Search** | Enables HuggingChat's Exa MCP web search | Off |
| **Use System Prompt Field** | Moves leading system messages into HuggingChat's custom field | Off |
| **Send As Text File** | Uploads the prompt as `.txt` | Off |
| **Text File Message** | Companion text pasted with file uploads | `Please read the attached file and respond to it.` |
| **File Upload Timeout** | Seconds to wait for send availability after upload | `20` |
| **File Upload Settle Delay** | Seconds to pause after upload before pasting text | `3.0` |
| **Message Send Timeout** | Seconds to wait for send availability after text entry | `8` |
| **Reuse Matching Chat** | Retries a matching cached chat instead of creating a new one | Off |
| **Search Older Matching Chats** | Reuses up to 7 older matching cached conversations | Off |
| **Delete Chat After Reply** | Deletes completed HuggingChat conversations | Off |

---

## :material-arrow-left: Back to Providers

[:material-arrow-left: Providers Overview](../providers.md)
