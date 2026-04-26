---
icon: providers/perplexity
---

# :providers-perplexity: Perplexity Behavior

This page covers the settings that control how IntenseRP interacts with **Perplexity** (`perplexity.ai`).

Perplexity is powerful, but its web app is fairly strict. IntenseRP drives the same composer you use in the browser, watches the `perplexity_ask` stream, and forwards only the assistant answer text to the OpenAI-compatible API.

!!! warning "Free tier limitations"
    It really only makes sense to use Perplexity with a paid (Pro or higher) account. IntenseRP can work with free accounts, but the experience is rough due to being locked mainly to the Sonar 2 model without Thinking controls. It's also heavily rate-limited, so expect slow responses and possible temporary blocks if you send too many requests.

!!! danger "Special thanks"
    Huge **thank you** to [Yurushia](https://github.com/twgok123) for their financial support and giving me access to a paid Perplexity account for development and testing. Without them, this integration quite literally would not exist. So, wholeheartedly, thank you!! 💙

---

## :material-tune: Modes (model IDs)

In IntenseRP Next v2, the `model` you select in SillyTavern is mostly a **behavior preset**, not the same thing as Perplexity's paid model picker.

For Perplexity, these model IDs map to simple behavior presets:

| Model ID | Behavior |
|---|---|
| `perplexity-auto` | Uses your IntenseRP settings |
| `perplexity-chat` | Forces Thinking off |
| `perplexity-reasoner` | Forces Thinking on when the account/model allows it |

---

## :material-chip: Real Perplexity model selection (web UI)

IntenseRP can switch Perplexity's real model picker in the web UI when your account exposes it:

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **Model**

Current options:

- `Best (Auto)`
- `Sonar 2`
- `GPT-5.4`
- `GPT-5.5`
- `Gemini 3.1 Pro`
- `Claude Sonnet 4.6`
- `Claude Opus 4.7`
- `Kimi K2.6`
- `Nemotron 3 Super`

!!! note "Paid-account controls"
    Perplexity only exposes model and Thinking controls on paid accounts. Free accounts can still send prompts, but IntenseRP skips those controls and uses whatever the Perplexity UI allows.

---

## :material-head-cog: Thinking

### Enable Thinking

When enabled, IntenseRP tries to toggle Perplexity Thinking before sending the prompt.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **Enable Thinking**

Some models force Thinking on, and some account tiers do not expose the toggle. In those cases IntenseRP logs what happened and keeps the request moving.

### Send Thinking

Perplexity does not currently expose usable thinking traces in the intercepted stream. The setting exists for mode/loadout consistency, but IntenseRP does **not** forward `<think>` content for Perplexity yet.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **Send Thinking**

---

## :material-magnify: Search

Perplexity Web search can be toggled through the composer tools menu.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **Enable Search**

!!! note "Search payloads"
    Perplexity streams search/source data around the answer. IntenseRP strips those provider-specific payloads and forwards only the assistant text.

---

## :material-file-upload: File Upload Mode

Instead of pasting your full prompt into Perplexity's editor, IntenseRP can upload it as a text file.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **Send As Text File**

If Perplexity indicates that the upload cap is reached, IntenseRP falls back to pasting the prompt as normal text for that request.

### Text File Message

Optional text pasted alongside the uploaded prompt file.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **Text File Message**

### File Upload Timeout

Controls how long IntenseRP waits for the send button to become available after selecting the file.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **File Upload Timeout**

### Message Send Timeout

Controls how long IntenseRP waits for the send button to appear after text entry in normal, non-file mode.

:material-arrow-right: **Settings** -> **Provider Behavior** -> **Perplexity** -> **Message Send Timeout (s)**

---

## :material-key: Login notes

Perplexity uses email-code login. Auto Login can enter the saved email and click through the first step, but you still need to type the 6-digit code in the browser window.

!!! warning "Persistent Sessions strongly recommended"
    Perplexity sessions are much nicer when the browser profile stays signed in. Keep **Persistent Sessions** on unless you have a specific reason to reset the provider profile each time.

See: [:material-key: Login & Sessions](../features/login-sessions.md)

---

## :material-translate: UI language requirement

The Perplexity driver currently expects the web UI language to be English (`en` / `en-US`). If the page is in another language, IntenseRP may fail to find the Sign In label, model menu, or tools menu reliably.

If you see a warning about Perplexity UI language:

1. Change Perplexity language to **English**
2. Reload the page (F5 / Ctrl+R)
3. Retry / restart the browser from IntenseRP if needed

---

## :material-code-tags: Per-message macros

You can add simple `[[...]]` macros to the latest user message in SillyTavern to override certain Perplexity Behavior settings for that request only.

All macros are stripped from the message before sending it to Perplexity.

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
| **Model** | Selects Perplexity's real model picker (paid accounts) | Best (Auto) |
| **Enable Thinking** | Toggles Perplexity Thinking where available | Off |
| **Send Thinking** | Reserved; no thinking traces are forwarded yet | Off |
| **Enable Search** | Enables Perplexity Web search | Off |
| **Send As Text File** | Uploads prompt as .txt | Off |
| **Text File Message** | Text pasted alongside uploaded file | (empty) |
| **File Upload Timeout** | Seconds to wait after upload | 20 |
| **Message Send Timeout (s)** | Seconds to wait for send button | 8 |

---

## :material-arrow-left: Back to Providers

[:material-arrow-left: Providers Overview](../providers.md)
