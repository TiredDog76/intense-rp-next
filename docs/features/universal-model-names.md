---
icon: material/tag-text-outline
---

# :material-tag-text-outline: Universal Model Names

This setting gives IntenseRP the same 3 API model IDs in normal single-provider mode, no matter which provider is active. It's **off** by default, since it does get a bit confusing at first, but it can be a nice quality-of-life improvement if you switch providers often or use multiple providers at once.

!!! warning "Providers in Parallel ignores this"
    If you have **Providers in Parallel** enabled, this setting does nothing. You still have to use provider-prefixed model IDs, and `intenserp-*` is invalid.

:material-arrow-right: **Settings** -> **API Server** -> **Model IDs** -> **Use Universal Model Names**

When it's on, `GET /v1/models` returns:

- `intenserp-auto`
- `intenserp-reasoner`
- `intenserp-chat`

So if you switch or hotswap providers, you don't also have to go change the model name in SillyTavern or another client. Nice and boring, in a good way.

Before you use it, though, there are some important things to know:

- Provider-specific IDs like `deepseek-auto` or `glm-chat` still work even when this is enabled.
- `intenserp-reasoner` is the universal version of the normal `*-reasoner` behavior preset.

!!! note "This replaces Better Model Names"
    The old experimental **Better Model Names** setting was removed in `v2.6.3`. This is the replacement.

---

[:material-arrow-left: Network & API](network-api.md)
