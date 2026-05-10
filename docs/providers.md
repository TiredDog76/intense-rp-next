---
icon: material/cloud
---

# :material-cloud: Providers

IntenseRP Next v2 currently supports six providers, and each one has its own Behavior page. This overview gives you a quick sense of what each provider-specific settings section covers and links to the full docs for each one.

---

<div class="grid cards" markdown>

-   :providers-deepseek: **DeepSeek Behavior**

    Configure DeepThink, Search, anti-censorship, file uploads, and chat reuse.

    [:arrow_right: Learn More](providers/deepseek-behavior.md)

-   :providers-zai: **GLM Behavior**

    Configure Deep Think, Search, Tools, model selection, token counting, file uploads, regeneration controls, and GLM-specific quirks.

    [:arrow_right: Learn More](providers/glm-behavior.md)

-   :providers-moonshot: **Moonshot Behavior**

    Configure Thinking, Search, file uploads, anti-censorship, and Kimi-specific caveats.

    [:arrow_right: Learn More](providers/moonshot-behavior.md)

-   :providers-qwen: **QwenLM Behavior**

    Configure Thinking, Web search, model selection, token counting, uploads, and provider guardrails.

    [:arrow_right: Learn More](providers/qwen-behavior.md)

-   :providers-perplexity: **Perplexity Behavior**

    Configure Perplexity model selection, Thinking, Search, uploads, and email-code login notes.

    [:arrow_right: Learn More](providers/perplexity-behavior.md)

-   :providers-aistudio: **Google AI Studio Behavior**

    Configure AI Studio model selection, Thinking Level, Search, URL Context, uploads, and sampling controls.

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
| **Reuse Matching Chat** | Regenerate the last response instead of creating a new chat when the prompt is identical |

---

### :providers-zai: GLM Behavior

Fine-tune how GLM Chat processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Deep Think** | Toggle GLM reasoning mode |
| **Send Deep Think** | Include the thinking process in the response (wrapped in `<think>` tags) |
| **Search** | Toggle GLM Search (search results are not sent to the client) |
| **Tools** | Toggle GLM's separate Tools button on GLM-5V-Turbo |
| **Model** | Select GLM's real web UI model picker |
| **Count Tokens** | Return token usage in API responses |
| **File Upload Mode** | Send long prompts as a text file to bypass input limits |
| **Reuse Matching Chat** | Regenerate on duplicate prompts (currently unreliable for GLM) |
| **Repetition Buster** | Send a throwaway cache-buster prompt before duplicate prompts in a fresh chat |

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
| **Reuse Matching Chat** | Regenerate on duplicate prompts instead of opening a new chat |

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
| **Reuse Matching Chat** | Regenerate on duplicate prompts instead of opening a new chat |

---

### :providers-perplexity: Perplexity Behavior

Fine-tune how Perplexity processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Model Picker (UI)** | Select Perplexity's real model picker on paid accounts |
| **Enable Thinking** | Toggles Perplexity Thinking where available |
| **Send Thinking** | Reserved for consistency; no thinking traces are forwarded yet |
| **Web Search** | Toggles Perplexity Web search (search/source payloads are not sent to the client) |
| **File Upload Mode** | Uploads long prompts as a text file, with text fallback if uploads are capped |

---

### :providers-aistudio: Google AI Studio Behavior

Fine-tune how Google AI Studio processes your requests.

| Feature | What It Does |
|---------|-------------|
| **Model Picker (UI)** | Select Google AI Studio's real model |
| **Enable Thinking** | Uses a higher Thinking Level on supported AI Studio models |
| **Thinking Level** | Picks the Thinking Level tier for supported AI Studio models |
| **Send Thinking** | Includes AI Studio thinking summaries in the response (wrapped in `<think>` tags) |
| **Search** | Toggles Google Search grounding |
| **URL Context** | Toggles the URL Context browsing tool |
| **File Upload Mode** | Uploads prompts through AI Studio's media picker |
| **Anti-Censorship** | Detects blocked turns and runs the edit + continue workaround |
| **Temperature / Top P / Max Output Tokens** | Applies supported AI Studio sampling controls before sending |
| **Safety Filters** | Lowers AI Studio's safety sliders automatically once per browser session |
| **Reuse Matching Chat** | Regenerates on duplicate prompts instead of opening a new chat |

---

## What's Next?

<div class="grid cards" markdown>

-   :material-key: **Login & Sessions**

    Auto-login and persistent browser sessions for supported providers.

    [:arrow_right: Open Login & Sessions](features/login-sessions.md)

-   :material-account-switch: **Accounts & Credentials**

    Manage saved accounts, rotation, retry-on-failure, and sign-in settings.

    [:arrow_right: Open Accounts & Credentials](features/accounts.md)

-   :material-cloud: **Provider Support**

    See the provider roadmap, lifecycle stages, and implementation notes.

    [:arrow_right: Open Provider Support](advanced/provider-support.md)

</div>
