---
icon: providers/moonshot
---

# :providers-moonshot: Moonshot Behavior

This page covers the toggles and options that control how IntenseRP interacts with **Moonshot** (`kimi.com`).

!!! note "Model IDs"
    Moonshot exposes three API behavior presets:
    `moonshot-auto`, `moonshot-chat`, and `moonshot-reasoner`.
    These are behavior modes, not separate backend model selection.

    If you enable **Settings -> Experimental -> Better Model Names**, the equivalent IDs become:

    - `kimi-k2.5-auto`
    - `kimi-k2.5`
    - `kimi-k2.5-think`

    Legacy IDs still work either way. See [:material-tag-text-outline: Better Model Names](../experimental/better-model-names.md).

---

## :material-login: Authentication

Unfortunately, Kimi has no support for an email/password login flow, so to auth IntenseRP will ask you to manually log in with Google. **Because of this, Persistent Sessions are almost a requirement for Kimi users.** Without them, you'll have to go through the google auth flow every time you start IntenseRP with Kimi selected as the provider.

!!! info "Multiple profiles"
    There's rate limiting as well, so you can set up multiple profiles (identities) even though Moonshot uses manual Google login.

    Open **Settings -> Providers & Credentials -> Credential Manager** and add multiple accounts under Moonshot.

    IntenseRP does **not** use those values for your Google login, but it treats each row as a separate identity (separate browser profile and session). Use a valid-looking email (required) and any non-empty password.

    You may wish to log in with different Google accounts in each profile to further reduce the risk of rate limits.

## :material-head-cog: Thinking

Kimi exposes reasoning through model mode selection in the web UI.

### Enable Thinking

Switches Kimi to **K2.5 Thinking** before sending a request.
When disabled, IntenseRP switches to **K2.5 Instant**.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **Enable Thinking**

### Send Thinking

When enabled, reasoning content is included in API output, wrapped in `<think>` tags.
When disabled, only final answer text is forwarded.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **Send Thinking**

!!! warning "Model downgrading"
    As part of a paywall strategy, Kimi will downgrade to K2.5 Instant (if you're on their Free plan) when you enable Thinking mode. This is a provider-side change and not something IntenseRP can control. They say it's because of high demand, but really it probably just means they're trying to force you to pay `¯\_(ツ)_/¯`.

---

## :material-magnify: Search

Toggles Kimi search tooling in the web UI.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **Enable Search**

!!! warning "Search + Thinking"
    Kimi can emit multi-stage reasoning when Search and Thinking are both enabled.
    Some clients (including SillyTavern) may not parse this perfectly.

!!! danger "On a personal note"
    Do not enable Search and Thinking at the same time. Just don't. It's a mess and IntenseRP sometimes breaks trying to handle it.

---

## :material-file-upload: File Upload Mode

Instead of typing your message into Kimi's editor, IntenseRP can upload it as a text file attachment.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **Send As Text File**

### File Upload Timeout

Controls how long IntenseRP waits (in seconds) for the send button to become enabled after upload.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **File Upload Timeout**

Default is 15 seconds.

### Text File Filler

Kimi won't let you send a file with an empty textbox as it needs *some* text alongside it. By default IntenseRP pastes a single `.` (dot) as filler, but you can change this to whatever you want.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **Text File Filler**

This setting only appears when **Send As Text File** is enabled.

---

## :material-shield-off: Anti-Censorship

When enabled, IntenseRP suppresses refusal-like stream events (when detected) and closes the response cleanly.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **Anti-Censorship**

!!! warning "What It Doesn't Do"
    This does not bypass provider filtering. It only suppresses refusal-style output from being forwarded to the client.

---

## :material-refresh: Clean Regeneration

When enabled, IntenseRP tries to click Kimi's regenerate action if:

1. The new prompt is identical to the cached last prompt
2. Effective behavior settings are also identical

Otherwise it starts a fresh chat.

:material-arrow-right: **Settings** -> **Moonshot Behavior** -> **Clean Regeneration**

---

## :material-code-tags: Per-Message Macros

You can add `[[...]]` macros to the latest user message to override behavior for that request only.
All macros are stripped before sending.

| Macro | Effect |
|------|--------|
| `[[think]]`, `[[r1]]` | Force Thinking on |
| `[[nothink]]`, `[[r0]]` | Force Thinking off |
| `[[search]]` | Force Search on |
| `[[nosearch]]`, `[[no_search]]` | Force Search off |
| `[[file]]` | Force Send As Text File on |
| `[[nofile]]` | Force Send As Text File off |

---

## :material-format-list-checks: Quick Reference

| Setting | What It Does | Default |
|---------|--------------|---------|
| **Enable Thinking** | Switches Kimi mode between Instant and Thinking | Off |
| **Send Thinking** | Includes reasoning in response | Off |
| **Enable Search** | Toggles Kimi search | Off |
| **Send As Text File** | Uploads prompt as .txt | Off |
| **File Upload Timeout** | Seconds to wait for upload | 15 |
| **Text File Filler** | Text pasted alongside the uploaded file | `.` |
| **Anti-Censorship** | Suppresses refusal-like outputs | Off |
| **Clean Regeneration** | Regenerates on duplicate prompts | Off |

---

## :material-arrow-left: Back to Features

[:material-arrow-left: Features Overview](../features.md)
