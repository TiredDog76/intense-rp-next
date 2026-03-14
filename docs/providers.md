---
icon: material/cloud
---

# :material-cloud: Providers

IntenseRP Next v2 currently supports five providers, and each one has its own Behavior page. This overview gives you a quick sense of what each provider-specific settings section covers and links to the full docs for each one.

---

<div class="grid cards" markdown>

-   :providers-deepseek: **DeepSeek Behavior**

    Configure DeepThink, Search, anti-censorship, file uploads, and clean regeneration.

    [:arrow_right: Learn More](providers/deepseek-behavior.md)

-   :providers-zai: **GLM Behavior**

    Configure Deep Think, Search, model selection, token counting, file uploads, and GLM-specific quirks.

    [:arrow_right: Learn More](providers/glm-behavior.md)

-   :providers-moonshot: **Moonshot Behavior**

    Configure Thinking, Search, file uploads, anti-censorship, and Kimi-specific caveats.

    [:arrow_right: Learn More](providers/moonshot-behavior.md)

-   :providers-qwen: **QwenLM Behavior**

    Configure Thinking, Web search, model selection, token counting, uploads, and provider guardrails.

    [:arrow_right: Learn More](providers/qwen-behavior.md)

-   :providers-aistudio: **Google AI Studio Behavior**

    Configure Gemini model selection, Thinking Level, Search, URL Context, uploads, and sampling controls.

    [:arrow_right: Learn More](providers/aistudio-behavior.md)

</div>

---

## Quick Reference

Here's a quick rundown of the provider-specific Behavior pages.

### :providers-deepseek: DeepSeek Behavior

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

### :providers-zai: GLM Behavior

Fine-tune how GLM Chat processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Deep Think** | Toggle GLM reasoning mode |
| **Send Deep Think** | Include the thinking process in the response (wrapped in `<think>` tags) |
| **Search** | Toggle GLM Search (search results are not sent to the client) |
| **Model** | Select GLM's real web UI model picker |
| **Count Tokens** | Return token usage in API responses |
| **File Upload Mode** | Send long prompts as a text file to bypass input limits |
| **Clean Regeneration** | Regenerate on duplicate prompts (currently unreliable for GLM) |

---

### :providers-moonshot: Moonshot Behavior

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

### :providers-qwen: QwenLM Behavior

Fine-tune how QwenLM processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Thinking** | Toggle QwenLM Thinking mode |
| **Send Thinking** | Include thinking summaries in the response (wrapped in `<think>` tags) |
| **Count Tokens** | Returns token usage in API responses |
| **Web Search** | Toggle QwenLM Web search (search results are not sent to the client) |
| **Model Picker (UI)** | Select Qwen's real model dropdown |
| **File Upload Mode** | Send long prompts as a text file |
| **Clean Regeneration** | Regenerate on duplicate prompts instead of opening a new chat |

---

### :providers-aistudio: Google AI Studio Behavior

Fine-tune how Google AI Studio processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Gemini Model Picker (UI)** | Select Google AI Studio's real Gemini model |
| **Enable Thinking** | Uses a higher Thinking Level on supported Gemini 3 / 3.1 models |
| **Thinking Level** | Picks the Thinking Level tier for supported Gemini 3 / 3.1 models |
| **Send Thinking** | Includes Gemini thinking summaries in the response (wrapped in `<think>` tags) |
| **Search** | Toggles Google Search grounding |
| **URL Context** | Toggles the URL Context browsing tool |
| **File Upload Mode** | Uploads prompts through AI Studio's media picker |
| **Temperature / Top P / Max Output Tokens** | Applies AI Studio sampling controls before sending |
| **Safety Filters** | Lowers AI Studio's safety sliders automatically once per browser session |
| **Clean Regeneration** | Regenerates on duplicate prompts instead of opening a new chat |

---

## What's Next?

<div class="grid cards" markdown>

-   :material-key: **Login & Sessions**

    Auto-login and persistent browser sessions for supported providers.

    [:arrow_right: Open Login & Sessions](features/login-sessions.md)

-   :material-account-switch: **Accounts & Credentials**

    Manage saved accounts, rotation, retry-on-failure, and Credential Manager.

    [:arrow_right: Open Accounts & Credentials](features/accounts.md)

-   :material-cloud: **Provider Support**

    See the provider roadmap, lifecycle stages, and implementation notes.

    [:arrow_right: Open Provider Support](advanced/provider-support.md)

</div>
