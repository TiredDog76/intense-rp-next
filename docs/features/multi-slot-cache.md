---
icon: material/layers-triple-outline
---

# :material-layers-triple-outline: Multi-Slot Cache

Multi-Slot Cache is basically **Clean Regeneration with a better memory**.

Normally, Clean Regeneration only remembers the very last prompt/chat it used. With Multi-Slot Cache enabled, IntenseRP can keep up to **7** older cached chats around and reuse one of those if the current request matches.

It is **off by default**, and it only works when **Clean Regeneration** is also enabled for that provider.

---

## :material-check-decagram: Supported providers

Right now this feature works on:

- DeepSeek
- GLM Chat
- Moonshot / Kimi
- QwenLM

It does **not** work on **Google AI Studio** right now.

---

## :material-cog-refresh: How it works

1. IntenseRP still tries the normal Clean Regeneration flow first.
2. If the current chat is already the right one, it just presses **Regenerate** there like usual.
3. If not, IntenseRP checks the older cached slots for the same prompt + relevant provider state.
4. If it finds a match, it opens that cached chat URL and tries to regenerate there instead.
5. If the regenerate button is missing, that cache entry gets dropped and IntenseRP falls back to sending the request normally.

The cache keeps the **last 7** saved chats per provider/account. When a new one gets added, the oldest one is removed.

If an old cached chat gets reused successfully, it stays where it is. IntenseRP does **not** bump it to the top or reshuffle the cache order.

---

## :material-tune-variant: What counts as a match?

It is not just the prompt text.

IntenseRP also checks the relevant provider-side request state, such as things like:

- the currently selected model (where that provider exposes one)
- whether thinking is enabled
- whether search is enabled
- whether the prompt was sent as a text file

That way it does not accidentally reopen an old chat and regenerate it under the wrong setup.

---

## :material-account-switch: Cache scope

Multi-Slot Cache is scoped **per provider** and **per account**.

That matters because provider chat IDs are usually only valid for the account that created them. A DeepSeek chat from Account A is not something Account B can normally reopen and regenerate.

!!! note "Manual-login fallback"
    When IntenseRP knows which saved account is active, it separates the cache by account email.

    If it cannot know that cleanly (for example a manual-login flow without a saved account), it falls back to the active browser profile instead. That is the safest approximation available across all providers.

---

## :material-warning-outline: DeepSeek special case

DeepSeek has one extra rule here.

If a DeepSeek chat gets content-filtered / censored, IntenseRP does **not** save that chat into the multi-slot cache. DeepSeek disables regeneration on censored chats anyway, so keeping those around would just create dead cache entries.

---

## :material-arrow-right: Where to enable it

You enable it in the provider Behavior pages:

- **DeepSeek Behavior** -> **Multi-Slot Cache**
- **GLM Behavior** -> **Multi-Slot Cache**
- **Moonshot Behavior** -> **Multi-Slot Cache**
- **QwenLM Behavior** -> **Multi-Slot Cache**

And again, it only does anything if **Clean Regeneration** is already enabled for that provider.

---

## :material-link-variant: Related pages

- [:material-refresh: DeepSeek Behavior](../providers/deepseek-behavior.md#clean-regeneration)
- [:material-refresh: GLM Behavior](../providers/glm-behavior.md#clean-regeneration-known-issues)
- [:material-refresh: Moonshot Behavior](../providers/moonshot-behavior.md#clean-regeneration)
- [:material-refresh: QwenLM Behavior](../providers/qwen-behavior.md#clean-regeneration)
- [:material-cloud: Provider Support](../advanced/provider-support.md)

---

## :material-arrow-left: Back to Features

[:material-arrow-left: Features](../features.md)
