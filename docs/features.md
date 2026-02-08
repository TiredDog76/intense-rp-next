---
icon: material/star-four-points
---

# :material-star-four-points: Features

IntenseRP Next v2 packs a lot of useful features under the hood. This page gives you an overview of what's available and links to detailed documentation for each feature.

---

<div class="grid cards" markdown>

-   :material-format-text: **Formatting**

    Control how messages are processed and sent to the provider.

    [:arrow_right: Learn More](features/formatting.md)

-   :material-brain: **DeepSeek Behavior**

    Configure DeepThink, search, anti-censorship, and more.

    [:arrow_right: Learn More](features/deepseek-behavior.md)

-   :material-chat-processing: **GLM Behavior**

    Configure Deep Think modes, Search status, and GLM-specific quirks.

    [:arrow_right: Learn More](features/glm-behavior.md)

-   :material-meteor: **Moonshot Behavior**

    Configure Thinking, Search, file uploads, and Kimi-specific notes.

    [:arrow_right: Learn More](features/moonshot-behavior.md)

-   :material-key: **Login & Sessions**

    Auto-login and persistent browser sessions.

    [:arrow_right: Learn More](features/login-sessions.md)

-   :material-lan: **Network & API**

    Port settings, LAN access, and API key authentication.

    [:arrow_right: Learn More](features/network-api.md)

-   :material-console: **Console & Logging**

    Real-time logs, file logging, and console dumping.

    [:arrow_right: Learn More](features/console-logging.md)

-   :material-cog: **System**

    Config storage, updates, and application settings.

    [:arrow_right: Learn More](features/system.md)

</div>

---

## Quick Reference

Here's a quick rundown of all the major features you'll find in IntenseRP Next v2.

### :material-format-text: Formatting

IntenseRP doesn't just forward your messages to the provider. It formats them into a single prompt that the model can understand better.

| Feature | What It Does |
|---------|-------------|
| **Formatting Templates** | Define how messages appear using `{{name}}`, `{{role}}`, and `{{content}}` placeholders |
| **Built-in Presets** | Choose from Classic, XML-Like, or Divided styles |
| **Name Detection** | Extract character/user names from IR2 blocks, Classic IntenseRP tags, or message objects (`name` / `irp-next`) |
| **Message Injection** | Add custom text before or after all messages |

---

### :material-brain: DeepSeek Behavior

Fine-tune how DeepSeek processes your requests.

| Feature | What It Does |
|---------|-------------|
| **DeepThink** | Toggle DeepSeek's reasoning mode for more thoughtful responses |
| **Send DeepThink** | Include the thinking process in the response (wrapped in `<think>` tags) |
| **Search** | Enable web search capabilities |
| **File Upload Mode** | Send long prompts as a text file to bypass input limits |
| **Anti-Censorship** | Suppress "Sorry, that's beyond my current scope" messages |
| **Clean Regeneration** | Regenerate the last response instead of creating a new chat when the prompt is identical |

---

### :material-chat-processing: GLM Behavior

Fine-tune how GLM Chat processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Deep Think** | Toggle GLM reasoning mode |
| **Send Deep Think** | Include the thinking process in the response (wrapped in `<think>` tags) |
| **Search** | Toggle GLM Search (search results are not sent to the client) |
| **File Upload Mode** | Send long prompts as a text file to bypass input limits |
| **Clean Regeneration** | Regenerate on duplicate prompts (currently unreliable for GLM) |

---

### :material-meteor: Moonshot Behavior

Fine-tune how Moonshot processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Enable Thinking** | Switches Kimi between Instant and Thinking modes |
| **Send Thinking** | Include reasoning in response (wrapped in `<think>` tags) |
| **Search** | Toggle Kimi search tooling |
| **File Upload Mode** | Send long prompts as a text file |
| **Anti-Censorship** | Suppress refusal-like stream outputs when detected |
| **Clean Regeneration** | Regenerate on duplicate prompts instead of opening a new chat |

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

### :material-cog: System

Application-wide settings and maintenance.

| Feature | What It Does |
|---------|-------------|
| **Config Storage** | Choose where settings are stored (relative, AppData, or custom path) |
| **Auto Updates** | Check for and install updates directly from the app |
| **Delete Profile** | Delete a selected persistent browser profile to start fresh |
| **Clear All Profiles** | Wipe all persistent profiles (Legacy + ECE) |

---

## What's Next?

<div class="grid cards" markdown>

-   :material-rocket-launch: **Getting Started**

    New here? Set up the app and connect to SillyTavern.

    [:arrow_right: Get Started](getting-started.md)

-   :material-transfer: **Migration Guide**

    Coming from v1? Learn what's changed.

    [:arrow_right: Migrate](migration.md)

</div>
