---
icon: material/tag-text-outline
---

# :material-tag-text-outline: Universal Model Names

This setting gives IntenseRP the same 3 API model IDs in normal single-provider mode, no matter which provider is active. It's **off** by default, since it does get a bit confusing at first, but it can be a nice quality-of-life improvement if you switch providers often.

!!! warning "Providers in Parallel ignores this"
    If you have **Providers in Parallel** enabled, this setting does nothing. You still have to use provider-prefixed model IDs, and `intenserp-*` is invalid.

:material-arrow-right: **Settings** -> **API Server** -> **Model IDs** -> **Use Universal Model Names**

When it's on, `GET /v1/models` returns:

- `intenserp-auto`
- `intenserp-reasoner`
- `intenserp-chat`

So if you switch or hotswap providers, you don't also have to go change the model name in SillyTavern or another client. Nice and boring, in a good way.

For providers with a real model picker, IntenseRP also lists the available real models as request-level overrides:

- GLM Chat
- Google AI Studio
- QwenLM
- Perplexity

Those IDs are lowercase, with spaces and dots converted to `-`, and they keep the normal suffixes. For example, a GLM model named **GLM-5.1** appears as `glm-5-1-auto`, `glm-5-1-reasoner`, and `glm-5-1-chat`.

`intenserp-*` still uses the model selected in Settings. A real-model ID switches the provider UI to that model for the request, then applies the suffix behavior on top.

Before you use it, though, there are some important things to know:

- Provider-specific IDs like `deepseek-auto` or `glm-chat` still work even when this is enabled.
- `intenserp-reasoner` is the universal version of the normal `*-reasoner` behavior preset.
- Real-model IDs are only visible and accepted while **Use Universal Model Names** is enabled.

!!! note "This replaces Better Model Names"
    The old experimental **Better Model Names** setting was removed in `v2.6.3`. Universal Model Names now covers that job too, without making it a separate experimental switch.

---

[:material-arrow-left: Network & API](network-api.md)
