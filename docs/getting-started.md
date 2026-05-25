---
icon: material/rocket-launch
---

# :material-rocket-launch: Getting Started

Let's get you up and running with IntenseRP Next v2! This guide covers everything from installation to chatting in SillyTavern.

---

## :material-clipboard-check-outline: What You'll Need

Before we dive in, make sure you have:

| | |
|---|---|
| :material-microsoft-windows: **Windows 10/11** or :material-linux: **Linux** | 64-bit with a graphical desktop |
| :material-account-plus: **Provider account** | [DeepSeek](https://chat.deepseek.com), [GLM Chat (Z.ai)](https://chat.z.ai/), [Kimi](https://www.kimi.com/), [QwenLM](https://chat.qwen.ai/), [Perplexity](https://www.perplexity.ai/), [HuggingChat](https://huggingface.co/chat), or [Google AI Studio](https://aistudio.google.com/) |
| :material-chat: **SillyTavern** (or similar) | Any OpenAI-compatible client works |

---

## :material-download: Step 1: Download & Install

Pick your platform and let's go!

=== ":material-microsoft-windows: Windows"

    1. Head to the [:material-github: Releases page](https://github.com/LyubomirT/intense-rp-next/releases)
    2. Grab the latest **`intenserp-next-v2-win32-x64.zip`**
    3. Extract it somewhere you'll remember
    4. Open the `intense-rp-next` folder and run **`intenserp-next-v2.exe`**
    
    ![Extracted Folder](pics/getting-started/extracted_win32.png)
    
    !!! tip "First Time?"
        The app will download browser components on first launch. Give it a minute!

=== ":material-linux: Linux"

    1. Head to the [:material-github: Releases page](https://github.com/LyubomirT/intense-rp-next/releases)
    2. Grab the latest **`intenserp-next-v2-linux-x64.tar.gz`**
    3. Extract and run:
    
    ```bash
    tar -xzf intenserp-next-v2-linux-x64.tar.gz
    cd intense-rp-next
    chmod +x intenserp-next-v2
    ./intenserp-next-v2
    ```
    
    !!! warning "Missing Libraries?"
        This sometimes happens, especially if you don't install new software often. You might need to install Qt6 dependencies. The most common ones are: `libxcb-cursor0`, `libegl1`, `libxkbcommon0`.

=== ":material-git: From Source"

    For developers or those who like living on the edge:
    
    ```bash
    git clone https://github.com/LyubomirT/intense-rp-next.git
    cd intense-rp-next
    
    # Create a virtual environment (recommended)
    python -m venv venv

    source venv/bin/activate  # Linux/Mac
    # or: venv\Scripts\activate  # Windows
    
    # Install deps
    pip install -r requirements.txt

    # Optional, since IntenseRP can auto-download browsers
    playwright install chromium
    
    # Run it!
    python main.py
    ```
    
    !!! note "Python 3.12+"
        Make sure you're running Python 3.12 or newer.

---

## :material-cog: Step 2: Provider + Account

Before hitting Start, pick your provider and decide how you want to log in.

1. Click the :material-cog: **Settings** button
2. Go to **Provider and Login**
3. In **Current Provider**, choose your provider (DeepSeek, GLM Chat, Moonshot, QwenLM, Perplexity, HuggingChat, or Google AI Studio)
4. In **Sign-In and Accounts**, (optional) turn on :material-toggle-switch: **Sign In Automatically**
5. Open **Saved Accounts** and add your account(s)
6. (Optional) Enable **Prefer the Least Used Account** and/or **Retry With Another Account**
7. Hit :material-content-save: **Save**

<!-- TODO: replace with an updated screenshot -->
![Provider and Login (placeholder)](pics/getting-started/signin_and_accounts.png)

!!! info "Manual login"
    If you prefer to log in manually each time, leave **Sign In Automatically** off. The browser will wait for you to log in.

!!! note "Upgrading?"
    If you previously saved credentials in older versions, IntenseRP automatically imports them into **Saved Accounts** on startup.

!!! warning "GLM CAPTCHA"
    GLM Chat requires a CAPTCHA during login. **Sign In Automatically** can fill your credentials, but you still need to solve the CAPTCHA in the browser window.
    **Keep Provider Sessions Signed In** is strongly recommended if you do not want to solve it every start.

!!! note "Moonshot login"
    Moonshot uses a Google popup login flow. If **Sign In Automatically** is enabled, IntenseRP can try to fill the popup automatically, but Google may still ask for manual confirmation, 2FA, or leave the popup open until you close it yourself.

!!! note "Google AI Studio login"
    Google AI Studio also uses Google sign-in. IntenseRP can try to auto-fill the Google login flow if **Sign In Automatically** is enabled, but **Keep Provider Sessions Signed In** is strongly recommended because Google may still ask for manual confirmation.

!!! note "Perplexity login"
    Perplexity uses email-code login. Auto Login can fill your email and start the code flow, but you still need to type the 6-digit code in the browser window. Persistent Sessions are very helpful here.

!!! note "HuggingChat login"
    HuggingChat uses your Hugging Face username/email and password. Its monthly credits are small, so add extra accounts in **Saved Accounts** if you have them and disable rows that have hit their monthly limit.

---

## :material-play-circle: Step 3: Start the Server

Alright, the fun part!

1. Click the big :material-play: **Start** button
2. A browser window will pop up
3. All providers can use auto-login, though Moonshot, Perplexity, and Google AI Studio may still need manual confirmation in the browser.
4. Once logged in, the status changes to :material-check-circle: **Running (Port 7777)**

<div class="image-grid" markdown>

![Main Window](pics/getting-started/main_window.png)

![Running Status](pics/getting-started/main_window_running.png)

</div>

!!! success "You're Live!"
    IntenseRP is now running and ready to accept requests.

---

## :material-power-plug: Step 4: Connect SillyTavern

Now let's hook up SillyTavern to use IntenseRP as its backend.

### :material-numeric-1-circle: Open API Connections

Click the :material-power-plug: **API** button in SillyTavern's top bar.

![SillyTavern API Button](pics/getting-started/connections.png)

### :material-numeric-2-circle: Pick the Right Settings

| Setting | What to Choose |
|---------|---------------|
| **API Type** | :material-chat-processing: Chat Completion |
| **Chat Completion Source** | :material-tune: Custom (OpenAI-compatible) |

### :material-numeric-3-circle: Enter the Endpoint

| Field | Value |
|-------|-------|
| :material-web: **Custom Endpoint** | `http://127.0.0.1:7777/v1` |
| :material-key: **API Key** | Leave blank |
| :material-robot: **Model** | `deepseek-*` / `glm-*` / `moonshot-*` / `qwen-*` / `perplexity-*` / `huggingchat-*` / `aistudio-*` |

!!! note
    Use the model ID that matches your active provider:

    - DeepSeek -> `deepseek-auto`
    - GLM Chat -> `glm-auto`
    - Moonshot -> `moonshot-auto`
    - QwenLM -> `qwen-auto`
    - Perplexity -> `perplexity-auto`
    - HuggingChat -> `huggingchat-auto`
    - Google AI Studio -> `aistudio-auto`

!!! info "Model IDs"
    The `*-auto` model is the default and respects your IntenseRP settings for the active provider.

    There are also `*-chat` and `*-reasoner` variants.
    For the full list, see [:material-lan: Network & API](features/network-api.md).

![SillyTavern Endpoint Settings](pics/getting-started/preview_of_settings.png)

### :material-numeric-4-circle: Connect!

Click :material-connection: **Connect** and look for the green indicator.

!!! success ":material-party-popper: You Did It!"
    Start a chat and enjoy free LLM completions!

---

## :material-tune-vertical: Extra Settings (Optional)

Here are some handy tweaks you might want to know about.

### :material-tag-multiple: Set up Names

So that IntenseRP knows the names of your characters and personas, you'll want to set up a way to send names to it.

The recommended way is to set **Character Names Behavior** to **Completion Object**. This automatically sends character names to the API with every message, so IntenseRP can use them in formatting and injections.

![Character Names Setting](pics/getting-started/completion_object.png)

---

### :material-lan: Change the Port

By default IntenseRP listens on port `7777`. If that happens to be taken, you can change it:

:material-arrow-right: **Settings** → **API Server** → **Access** → **Server Port**

Don't forget to update your SillyTavern endpoint too!

---

### :material-brain: Enable DeepThink

And just as before, we support provider reasoning features. In simple words, it makes the model "smarter" by letting it think through problems step-by-step before answering (but also makes it slower and can change the tone).

:material-arrow-right: **Settings** → **Provider Behavior** → pick your provider in the selector

| Option | What It Does |
|--------|-------------|
| :material-toggle-switch: **Enable DeepThink** | Turns on the thinking toggle in DeepSeek |
| :material-toggle-switch: **Send DeepThink** | Includes reasoning in responses |

---

### :material-cookie: Persistent Sessions

Tired of logging in every time you restart?

:material-arrow-right: **Settings** → **Provider and Login** → **Saved Sessions** → :material-toggle-switch: **Keep Provider Sessions Signed In**

This saves your browser session so you stay logged in (unless you log out manually).

---

## :material-help-circle: Troubleshooting

!!! tip "Need more?"
    See [:material-bug: Troubleshooting](hands/troubleshooting.md) for a full checklist and bug report tips.

### :material-window-close: Browser Won't Open

- Make sure you have enough disk space (~500MB for browser, ~300MB for the app)
- Check if your antivirus is blocking the app
- Try restarting the app

### :material-connection: SillyTavern Can't Connect

- Is IntenseRP showing **Running**? If not, click Start
- Double-check the port matches (default: `7777`)
- Make sure you're using `http://`, not `https://`

### :material-alert: "Sorry, that's beyond my current scope"

That's DeepSeek's content filter kicking in. To hide this message:

:material-arrow-right: **Settings** → **Provider Behavior** → **DeepSeek** → :material-toggle-switch: **Anti-Censorship**

!!! note
    This doesn't bypass the filter; we just "snatch" the message before it's censored.

### :material-shield-off: Google AI Studio says "Content blocked"

That's AI Studio's harder backend-style censorship flow.

If you want IntenseRP to try the edit + continue workaround:

:material-arrow-right: **Settings** → **Provider Behavior** → **Google AI Studio** → :material-toggle-switch: **Anti-Censorship**

!!! note
    AI Studio's version is a bit weirder than DeepSeek's one.

    IntenseRP replaces the blocked assistant turn, sends a continue nudge, and retries up to 3 follow-up nudges before giving up.

---

## :material-arrow-right-bold: What's Next?

<div class="grid cards" markdown>

-   :material-star-four-points: **Explore Features**

    Learn about formatting templates, injections, and more.

    [:material-arrow-right: Features](features.md)

-   :material-transfer: **Migration Guide**

    Coming from IntenseRP v1? See what changed.

    [:material-arrow-right: Migrate](migration.md)

</div>
