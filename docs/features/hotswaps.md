---
icon: material/swap-horizontal
---

# :material-swap-horizontal: Hotswaps

Hotswaps let you switch between AI providers without opening the Settings window. Instead of navigating to **Providers & Credentials**, picking a new provider, saving, stopping, and starting again, you can do it all in one or two clicks.

---

## :material-cog-outline: How It Works

![Hotswap Modal](../pics/features/hotswap_modal.png)

When you trigger a Hotswap, IntenseRP shows a small dialog with the two providers you're **not** currently using. Pick one, and IntenseRP will:

1. Update your **Provider** setting to the new provider
2. If services are running, automatically restart the browser (stop + start)
3. If services are running, launch the new provider's web UI

That's it. Your other settings (credentials, behavior toggles, etc.) are untouched.

!!! tip "No data loss"
    Hotswapping is equivalent to changing the Provider dropdown in Settings and clicking Start again. Your browser profiles (Persistent Sessions), credentials, and behavior settings for each provider are preserved.

---

## :material-tune: Hotswap Experience

You can choose **how** the Hotswap shortcut appears in the UI:

:material-arrow-right: **Settings** -> **Application Settings** -> **Hotswap Experience**

### Stop Menu (default)

Adds a **Hotswap** option to the chevron dropdown on the **Stop** button - right alongside **Restart** and **ECE Switch** (if ECE is enabled).

I personally like this option more, since it keeps all the "big" controls together in one place, but it's a bit less discoverable than the Discrete mode.

### Discrete

Adds a small icon button to the **left of the Help button**. The button shows your current provider's icon:

| Provider | Icon |
|---|---|
| DeepSeek | :material-fishbowl: Whale |
| GLM Chat | Z |
| Moonshot | :material-moon-waning-crescent: Eclipse |

The button is only visible while services are running. Click it to open the same provider-selection dialog.

### Persistent Discrete

Uses the same small icon button as **Discrete**, but it stays visible even when services are stopped.

- If services are running: behavior is identical to **Discrete** (it restarts to apply the new provider).
- If services are stopped: it just switches your Provider setting (no restart, and it will not start anything).

!!! note "Switching modes"
    Changing the Hotswap Experience setting takes effect immediately (you won't need to restart). If you switch from **Stop Menu** to **Discrete** (or vice versa) while services are running, the UI updates right away. Thanks to the magic of Qt6!

---

## :material-help-circle: FAQ

??? question "Does Hotswap log me out?"
    Not by itself. If you have **Persistent Sessions** enabled, each provider keeps its own browser profile, so switching providers is seamless. If you **don't** have Persistent Sessions, you'll need to log in to the new provider (same as a normal restart with a different provider selected).

??? question "Can I Hotswap while the browser is stopped?"
    By default, no. The Hotswap option only appears when services are running.

    If you set **Hotswap Experience** to **Persistent Discrete**, the Hotswap button stays visible while stopped and will switch your Provider setting without starting or restarting services.

??? question "What about ECE credentials?"
    Hotswap changes the provider but doesn't rotate ECE identities. If you want to switch ECE profiles, use the **ECE Switch** option in the chevron menu instead.

---

## :material-format-list-checks: Quick Reference

| Setting | Where | Default |
|---|---|---|
| **Hotswap Experience** | Application Settings | Stop Menu |

| Experience | Location | Visible when |
|---|---|---|
| Stop Menu | Chevron dropdown (Stop button) | Services running |
| Discrete | Small button left of Help | Services running |
| Persistent Discrete | Small button left of Help | Always |

---

## :material-arrow-left: Back to Features

[:material-arrow-left: Features Overview](../features.md)
