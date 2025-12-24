---
icon: material/bug
---

# :material-bug: Troubleshooting

This page is a practical checklist for diagnosing problems with IntenseRP Next v2 - from basic "is it running?" checks, through common fixes, to filing a useful bug report.

---

## :material-clipboard-check-outline: Quick checks (do these first)

1. **Is IntenseRP running?**
    - The main window should say **Running (Port XXXX)**.
    - If it says Ready/Stopped, click :material-play: **Start**.

2. **Is the browser open and logged in?**
    - A Chromium window should be open.
    - If you're on a DeepSeek login page, log in (or enable Auto Login).

3. **Is your client pointing at the right endpoint?**
    - Default endpoint: `http://127.0.0.1:7777/v1`
    - If you changed the port, your client must match.

4. **If using API keys, is your client sending one?**
    - `Authorization: Bearer YOUR_KEY`

---

## :material-connection: Client cannot connect

Symptoms:

- "Connection refused"
- "Cannot reach server"
- SillyTavern Connect button stays red

Checklist:

- Confirm the server is running (status label shows Running).
- Confirm the port is correct (default `7777`).
- Confirm you are using `http://`, not `https://`.
- If connecting from another device:
    - Enable **Available on LAN**
    - Use your PC's LAN IP (for example `http://192.168.1.100:7777/v1`)

See: [:material-lan: Network & API](../features/network-api.md)

### Verify the port is listening

=== ":material-microsoft-windows: Windows"

    In Command Prompt:

    ```bat
    netstat -ano | findstr :7777
    ```

=== ":material-linux: Linux"

    In a terminal:

    ```bash
    ss -ltnp | grep ':7777'
    ```

If nothing is listening, IntenseRP is not started, or it failed to start.

---

## :material-key-variant: 401 Unauthorized (API keys)

If **Use API Keys** is enabled and your client does not send a key, IntenseRP will reject requests.

Fix:

1. Go to :material-arrow-right: **Settings** → **Network Settings**
2. Either disable **Use API Keys**, or add a key and configure your client to use it

See: [:material-lan: Network & API](../features/network-api.md)

---

## :material-window-close: Browser won't open / crashes immediately

Common causes:

- First-run browser install blocked (firewall, captive portal, restricted network)
- Antivirus interference
- Missing GUI dependencies (Linux)

What to try:

1. Restart IntenseRP and try again.
2. Check logs for "Verifying/Installing Chromium browser..." or install errors.
3. If running from source, try installing the browser once manually:

    ```bash
    playwright install chromium
    ```

See: [:material-console: Console & Logging](../features/console-logging.md)

---

## :material-account-alert: Login problems (stuck on sign-in, loops, expired sessions)

Fixes, in order:

1. If you use Auto Login, double-check your DeepSeek email/password in **Providers & Credentials**.
2. If Persistent Sessions is enabled but things feel "stuck", use **Clear Profile** to reset the saved browser profile.
3. Try manual login once (disable Auto Login temporarily) to confirm the provider isn't blocking automated sign-in.

See:

- [:material-key: Login & Sessions](../features/login-sessions.md)
- [:material-cog: System](../features/system.md)

---

## :material-timer-sand: Requests are slow / appear to hang

Reality check:

- IntenseRP currently processes **one request at a time**. If multiple clients/requests are active, later requests will wait in a queue.
- First request after launch can be slower (browser warmup, login, UI settling).

What to check:

- Look for "Processing queued request..." in logs.
- If you run many parallel chats, reduce concurrency on the client side.

See: [:material-api: API Behavior](../advanced/api-behavior.md)

---

## :material-bug-check: Bug reports

If something is genuinely broken (crash, login loop, API failures), a good report makes it much easier to fix quickly.

<div class="grid cards" markdown>

-   :material-github: **Search existing issues**

    Check if someone already reported it (and maybe a workaround exists).

    [:arrow_right: Open issues](https://github.com/LyubomirT/intense-rp-next/issues)

-   :material-bug: **Open a new issue**

    If it's new, file a bug report with the template below.

    [:arrow_right: New issue](https://github.com/LyubomirT/intense-rp-next/issues/new/choose)

-   :material-console: **Collect logs**

    Logs are usually the difference between "can't reproduce" and "fixed".

    [:arrow_right: Console & Logging](../features/console-logging.md)

</div>

### :material-clipboard-check-outline: Before you file

- [ ] Reproduce once (so you can describe exact steps).
- [ ] If possible, reproduce with logs enabled (console and/or logfiles).
- [ ] Note whether it happens on `deepseek-auto`, `deepseek-chat`, or `deepseek-reasoner`.
- [ ] If you are using LAN, try locally too (to rule out firewall/network issues).

### :material-clipboard-text-outline: What to include

- **Version** (app title bar)
- **OS** (Windows/Linux + version)
- **Install method** (release zip vs from source)
- **Provider** (currently: DeepSeek)
- **Client** (SillyTavern or other client + version)
- **Endpoint** (example: `http://127.0.0.1:7777/v1`)
- **Model** (`deepseek-auto` / `deepseek-chat` / `deepseek-reasoner`)
- **Streaming** (`stream: true` or `stream: false`)
- **Expected vs actual**
- **Logs** (console dump or `logs/log_*.txt`)

!!! danger "Redact secrets"
    Logs can contain your DeepSeek email, file paths, message content, and API keys. Always redact personal data before posting publicly.

### :material-text-box-outline: Copy/paste template

```text
Title:

Version:
OS:
Install method:
Provider:
Client:
Endpoint:
Model:
Streaming:

Steps to reproduce:
1)
2)
3)

Expected:
Actual:

Logs:
- (attach `logs/log_*.txt` or a console dump, redacted)
```

---

## :material-arrow-right: Related pages

<div class="grid cards" markdown>

-   :material-rocket-launch: **Getting Started**

    Install, launch, and connect SillyTavern.

    [:arrow_right: Getting Started](../getting-started.md)

-   :material-lan: **Network & API**

    Ports, LAN access, and API key auth.

    [:arrow_right: Network & API](../features/network-api.md)

-   :material-console: **Console & Logging**

    Capture logs and share them safely.

    [:arrow_right: Console & Logging](../features/console-logging.md)

-   :material-api: **API Behavior**

    Request flow, streaming, cancellation, and queueing.

    [:arrow_right: API Behavior](../advanced/api-behavior.md)

</div>

---

## :material-arrow-left: Back to Home

[:material-arrow-left: Home](../index.md)
