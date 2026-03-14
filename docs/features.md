---
icon: material/star-four-points
---

# :material-star-four-points: Features

IntenseRP Next v2 packs a lot of useful features under the hood. This page gives you an overview of the app-wide features and links to detailed documentation for each one.

!!! info "Provider settings moved"
    DeepSeek, GLM, Moonshot, QwenLM, and Google AI Studio Behavior settings now live in the dedicated [:material-cloud: Providers](providers.md) section.

---

<div class="grid cards" markdown>

-   :material-format-text: **Formatting**

    Control how messages are processed and sent to the provider.

    [:arrow_right: Learn More](features/formatting.md)

-   :material-cloud: **Providers**

    Provider-specific Behavior settings now live in their own section.

    [:arrow_right: Learn More](providers.md)

-   :material-key: **Login & Sessions**

    Auto-login and persistent browser sessions.

    [:arrow_right: Learn More](features/login-sessions.md)

-   :material-lan: **Network & API**

    Port settings, LAN access, and API key authentication.

    [:arrow_right: Learn More](features/network-api.md)

-   :material-console: **Console & Logging**

    Real-time logs, file logging, and console dumping.

    [:arrow_right: Learn More](features/console-logging.md)

-   :material-swap-horizontal: **Hotswaps**

    Switch providers on the fly without touching Settings.

    [:arrow_right: Learn More](features/hotswaps.md)

-   :material-cog: **System**

    Config storage, updates, and application settings.

    [:arrow_right: Learn More](features/system.md)

</div>

---

## Quick Reference

Here's a quick rundown of the major app-wide features you'll find in IntenseRP Next v2.

### :material-format-text: Formatting

IntenseRP doesn't just forward your messages to the provider. It formats them into a single prompt that the model can understand better.

| Feature | What It Does |
|---------|-------------|
| **Formatting Templates** | Define how messages appear using `{{name}}`, `{{role}}`, and `{{content}}` placeholders |
| **Built-in Presets** | Choose from Classic, XML-Like, Multiline XML-Like, or Divided styles |
| **Name Detection** | Extract character/user names from IR2 blocks, Classic IntenseRP tags, or message objects (`name` / `irp-next`) |
| **Message Injection** | Add custom text before or after all messages |

---

### :material-cloud: Providers

Provider-specific Behavior settings now live in their own section.

If you are looking for DeepSeek / GLM / Moonshot / QwenLM / Google AI Studio toggles, model pickers, search settings, or provider-specific quirks:

:material-arrow-right: **Open** [:material-cloud: Providers Overview](providers.md)

---

### :material-key: Login & Sessions

Make logging in less of a chore.

| Feature | What It Does |
|---------|-------------|
| **Auto Login** | Automatically sign in with saved credentials on startup |
| **Persistent Sessions** | Keep your browser session between restarts, no re-login needed |

---

### :material-lan: Network & API

Configure how IntenseRP listens for requests.

| Feature | What It Does |
|---------|-------------|
| **Port** | Change the default port (7777) if it's already in use |
| **LAN Availability** | Make the server accessible from other devices on your local network |
| **API Keys** | Require authentication for incoming requests |

---

### :material-console: Console & Logging

Keep track of what's happening under the hood.

| Feature | What It Does |
|---------|-------------|
| **Console Window** | A separate window showing real-time application logs |
| **Color Palettes** | Choose between Modern, Classic, or Bright color schemes |
| **File Logging** | Save logs to files with automatic rotation |
| **Console Dumping** | Export console contents to a file |

---

### :material-swap-horizontal: Hotswaps

Switch AI providers without leaving the main window.

| Feature | What It Does |
|---------|-------------|
| **Stop Menu mode** | Adds a Hotswap option to the chevron dropdown on the Stop button |
| **Discrete mode** | Shows a small provider-icon button next to Help |

---

### :material-cog: System

Application-wide settings and maintenance.

| Feature | What It Does |
|---------|-------------|
| **Config Storage** | Choose where settings are stored (relative, AppData, or custom path) |
| **Auto Updates** | Check for and install updates directly from the app |
| **Delete Profile** | Delete a selected persistent browser profile to start fresh |
| **Clear All Profiles** | Wipe all persistent profiles (Legacy + Accounts) |

---

## What's Next?

<div class="grid cards" markdown>

-   :material-rocket-launch: **Getting Started**

    New here? Set up the app and connect to SillyTavern.

    [:arrow_right: Get Started](getting-started.md)

-   :material-transfer: **Migration Guide**

    Coming from v1? Learn what's changed.

    [:arrow_right: Migrate](migration.md)

-   :material-cloud: **Providers**

    Need provider-specific Behavior settings? They're in their own section now.

    [:arrow_right: Browse Providers](providers.md)

</div>
