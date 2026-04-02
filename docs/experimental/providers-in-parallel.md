---
icon: material/source-branch
---

# :material-source-branch: Providers in Parallel (Experimental)

This one is exactly what it sounds like: instead of keeping just 1 provider browser alive, IntenseRP can keep multiple provider browsers open at the same time and route requests between them.

It is neat, and can actually save you time if you use a lot of different models often, BUT it is also *extremely* heavy on resources, and it is still a bit rough around the edges.

!!! warning "Experimental and heavy"
    This feature opens extra browser windows and keeps their sessions loaded in memory.

    If your machine is already struggling with 1 provider window, this setting will make things much worse. RAM usage can easily jump from ~200-300MB to ~1-2GB with 3+ providers active.

---

## :material-toggle-switch: Enable it

:material-arrow-right: **Settings** -> **Experimental** -> **Providers in Parallel**

After you enable it, you also get per-provider toggles right under that setting.

- The **current provider** is always forced on.
- The other toggles let you choose which other providers you want to keep alive in parallel.
- Changes only apply after you **restart the browser** with **Stop -> Start**.

If fewer than 2 providers end up enabled, IntenseRP quietly falls back to the normal single-provider behavior.

---

## :material-monitor-multiple: What actually happens

When the feature is active, IntenseRP launches 1 browser window per selected provider.

Each provider keeps using its own normal stuff (accounts, sessions, cookies, etc.) but they all run at the same time instead of just 1.

!!! warn "Might not be worth it"
    Most of those browser windows are idle until you send a request that belongs to them. Do keep that in mind if you don't jump between providers often, as the extra windows will just consume resources without much benefit.

---

## :material-api: Model routing

While this mode is active, routing is done by the **provider-prefixed model IDs**:

- `deepseek-auto` / `deepseek-chat` / `deepseek-reasoner`
- `glm-auto` / `glm-chat` / `glm-reasoner`
- `moonshot-auto` / `moonshot-chat` / `moonshot-reasoner`
- `qwen-auto` / `qwen-chat` / `qwen-reasoner`
- `aistudio-auto` / `aistudio-chat` / `aistudio-reasoner`

`GET /v1/models` returns the variants for every enabled provider.

!!! warning "Universal Model Names doesn't work here"
    If you have **Use Universal Model Names** enabled, it is ignored while **Providers in Parallel** is active. You have to use the provider-prefixed model IDs above, and `intenserp-*` is not valid.

If you send a model ID that belongs to a provider you did **not** enable, IntenseRP returns an error instead of guessing.

---

## :material-lan-pending: Queue behavior

The queue becomes provider-aware.

That means that requests for the **same provider** still stay serialized, and requests for **different providers** can run side by side

So you can queue a `deepseek-*` request and a `glm-*` request and let them work in parallel, while 2 `glm-*` requests still line up behind each other on the GLM browser.

---

## :material-alert-circle-outline: Good to know

- Browser restarts are still required after changing the provider selection for this feature.
- If one of the managed provider browser windows crashes or gets closed, IntenseRP currently stops the parallel runtime and expects you to start it again.
- This feature does not rewrite provider behavior logic. It mostly reuses the normal provider drivers and runs more than 1 of them at once.

If you want something stable and lightweight, the normal single-provider mode is still the safer choice.
