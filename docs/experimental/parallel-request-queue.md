---
icon: material/lan-connect
---

# :material-lan-connect: Parallel Request Queue (Very Experimental)

Parallel Request Queue builds on **Providers in Parallel**.

Providers in Parallel keeps multiple provider browsers alive. This setting lets the API queue use those active provider lanes at the same time, instead of making every request wait behind one global queue.

In practice, this means a DeepSeek request and a GLM Chat request can run side by side, while 2 GLM Chat requests still wait for the same GLM lane.

!!! warning "Very experimental"
    This touches API request routing, cancellation, and the Request Queue panel. It is useful, but it is still new enough that you should expect rough edges.

    If you want the safest behavior, leave this disabled.

---

## :material-toggle-switch: Enable It

:material-arrow-right: **Settings** -> **Advanced** -> **Experimental Features** -> **Run Providers in Parallel**

First enable **Run Providers in Parallel** and pick at least one extra provider.

Then enable:

:material-arrow-right: **Settings** -> **Advanced** -> **Experimental Features** -> **Parallelize API Request Queue**

Restart the browser with **Stop -> Start** after changing either setting.

If **Providers in Parallel** is disabled, **Parallelize API Request Queue** is forced off as well. The router needs more than 1 active lane to do anything useful.

---

## :material-routes: How Routing Works

When multiple providers are active, API requests use provider-prefixed model IDs such as `deepseek-auto`, `glm-chat`, or `aistudio-reasoner`.

The router uses that model ID to pick the provider lane:

- `deepseek-*` goes to the DeepSeek lane
- `glm-*` goes to the GLM Chat lane
- `aistudio-*` goes to the Google AI Studio lane

Each lane still processes its own requests in order. The new part is that different lanes are allowed to work at the same time.

!!! note "Same-provider lanes are not here yet"
    This does not yet let 2 DeepSeek accounts process 2 DeepSeek requests at the same time. The internal router is now shaped around reusable lanes so that can be added later, but this first version is still one lane per active provider runtime.

---

## :material-format-list-bulleted: Request Queue Panel

The **Request Queue Panel** can now show more than one request as processing.

Each request card has a small action button:

- processing requests get a **Stop** action for that specific request
- pending requests get a **Cancel** action for that specific request

The footer buttons are still bulk actions. **Stop** aborts all active requests, and **Clear Queue** cancels all requests that are still waiting.

This gives you both quick cleanup and more precise control when multiple clients are using the API.

---

## :material-memory: Resource Notes

This can use more resources than plain **Providers in Parallel**.

Providers in Parallel already keeps extra browser sessions alive. Parallel Request Queue can make those sessions actively generate at the same time, so RAM, CPU, and provider-side concurrency pressure can all go up.

If your machine is already struggling with multiple provider windows, this setting probably is not the best first thing to try.

---

## :material-alert-circle-outline: Current Limits

- Changes apply on the next browser start.
- Requests for the same provider lane are still serialized.
- If a managed provider browser crashes, the parallel runtime may stop and ask you to start it again.
- The same-provider multi-account version is planned separately.

If you are sharing the API with multiple clients, this can make queue behavior much more useful. Keep it disabled unless you are comfortable testing experimental behavior.

---

## :material-arrow-left: Back to Experimental

[:material-arrow-left: Experimental Overview](../experimental.md)
