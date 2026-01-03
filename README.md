<p align="center">
  <img src=".github/images/logo-strip.png" alt="IntenseRP Next" />
</p>

<h1 align="center">IntenseRP Next v2</h1>

<p align="center">
  It's a local OpenAI-compatible API + desktop app that drives DeepSeek's web UI (via Playwright),
  so you can use it from SillyTavern and other clients without paying for the official API. <i>Slightly cursed yet surprisingly effective.</i>
</p>

<p align="center">
  <a href="https://github.com/LyubomirT/intense-rp-next/releases">
    <img alt="Release" src="https://img.shields.io/github/v/release/LyubomirT/intense-rp-next?style=for-the-badge" />
  </a>
  <a href="https://github.com/LyubomirT/intense-rp-next/releases">
    <img alt="Downloads" src="https://img.shields.io/github/downloads/LyubomirT/intense-rp-next/total?style=for-the-badge" />
  </a>
  <a href="https://github.com/LyubomirT/intense-rp-next/stargazers">
    <img alt="Stars" src="https://img.shields.io/github/stars/LyubomirT/intense-rp-next?style=for-the-badge" />
  </a>
  <a href="https://github.com/LyubomirT/intense-rp-next/issues">
    <img alt="Issues" src="https://img.shields.io/github/issues/LyubomirT/intense-rp-next?style=for-the-badge" />
  </a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <a href="LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/LyubomirT/intense-rp-next?style=for-the-badge" />
  </a>
  <a href="https://intense-rp-next.readthedocs.io/en/latest/">
    <img alt="Docs" src="https://img.shields.io/website?url=https%3A%2F%2Fintense-rp-next.readthedocs.io%2Fen%2Flatest%2F&label=docs&style=for-the-badge" />
  </a>
  <img alt="Status" src="https://img.shields.io/badge/status-stable-2ea44f?style=for-the-badge" />
</p>

<p align="center">
  <a href="https://github.com/LyubomirT/intense-rp-next/actions/workflows/release-pyinstaller-windows.yml">
    <img alt="Build Windows release" src="https://img.shields.io/github/actions/workflow/status/LyubomirT/intense-rp-next/release-pyinstaller-windows.yml?style=for-the-badge&label=windows%20release" />
  </a>
  <a href="https://github.com/LyubomirT/intense-rp-next/actions/workflows/release-pyinstaller-linux.yml">
    <img alt="Build Linux release" src="https://img.shields.io/github/actions/workflow/status/LyubomirT/intense-rp-next/release-pyinstaller-linux.yml?style=for-the-badge&label=linux%20release" />
  </a>
</p>

<p align="center">
  <a href="#what-is-this">What is this?</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#connect-sillytavern-or-any-openai-compatible-client">Client setup</a> ·
  <a href="#documentation">Documentation</a> ·
  <a href="https://github.com/LyubomirT/intense-rp-next/releases">Releases</a> ·
  <a href="https://github.com/LyubomirT/intense-rp-next/issues">Issues</a>
</p>

<h1 align="center">🎬 Preview Video 🎬</h1>



https://github.com/user-attachments/assets/ebf1bfcd-3b23-4614-b584-174791bcb004



## Welcome 👋

If you're here because you want DeepSeek (DS) in SillyTavern without wiring up the paid official API: Welcome to the club!
IntenseRP Next v2 drives the official DeepSeek web app in a real browser, and re-exposes it as an OpenAI-compatible endpoint.

Unlike the official API, this is usually free (DeepSeek is entirely free to use with limits, and paid plans aren't added yet) and it gives you access to the full web UI experience (including DeepThink, file uploads, and more). Not without tradeoffs, of course - see below.

## Start here! 🎁

1. Download a release (see [Releases](https://github.com/LyubomirT/intense-rp-next/releases)) and run it (or run from source)
2. Click **Start** and log in when the browser opens
3. Point your SillyTavern client at `http://127.0.0.1:7777/v1` (default) and pick `deepseek-auto`

And it's done! It should Just Work™️.

## What is this?

IntenseRP Next v2 (sometimes shortened to "IRP Next v2") is a local bridge between:

- an OpenAI-style client (like SillyTavern), and
- a provider web app (currently: DeepSeek)

Under the hood it:

1. Starts a local FastAPI server (OpenAI-compatible routes under `/v1`)
2. Launches a real Chromium session (Patchright/Playwright)
3. Logs in (manual or auto-login)
4. Intercepts the provider's streaming network responses
5. Re-emits them as OpenAI-style SSE deltas for your client

In normal human terms: it makes "use DeepSeek from SillyTavern" feel like a normal API connection, even though DeepSeek is a web app.

DeepSeek also has an official API (paid), but not everyone can pay for it, so this is kind of a free alternative. 🙂

## Should you use it? 🎯

If you read this far, you probably have a use case in mind! But here's the objective truth:

It would work well for you if you:

- want free-ish access to the official DeepSeek models via the web app
- prefer a clicky desktop app over a pile of scripts
- are OK with the occasional wait or hiccup (web apps change)

Not the best fit if you:

- need high throughput / parallel requests (this uses one live browser session)
- want to run headless on a server
- want something that never breaks (that's perhaps the biggest caveat)

> [!NOTE]
> 1. Provider web apps change. When they do, a driver can break until it's updated.
> 2. IntenseRP currently processes **one request at a time** (requests are queued). This is on purpose (single live browser session).
> 3. This project is not affiliated with DeepSeek, SillyTavern, or any provider.

</details>

## Why v2?

v2 is a full rewrite based on lessons learned from the original **IntenseRP API** (by Omega-Slender) and my own **IntenseRP Next v1**.
The focus is less on a pile of features and more on making it sane to maintain and hard to break.

It's a more modular codebase with a Playwright-first approach (network interception, no scraping), a better UI (PySide6), and a cleaner settings model, plus built-in update and migration flows.

If you want to compare, have a look:

| Area | IntenseRP API / Next v1 | IntenseRP Next v2 |
|---|---|---|
| Backend | Python (Flask) | Python (FastAPI) |
| UI | customtkinter | PySide6 (Qt) |
| Automation | Selenium-based | Playwright (Patchright) |
| Scraping | HTML parsing (plus workarounds for NI) | Native Network interception |

## Quick start

> [!TIP]
> First launch can take a bit - v2 will verify/download its browser components.

<details>
<summary><strong>Windows</strong> (recommended)</summary>

1. Download the latest `intenserp-next-v2-win32-x64.zip` from [Releases](https://github.com/LyubomirT/intense-rp-next/releases)
2. Extract it anywhere
3. Open the `intense-rp-next` folder and run `intenserp-next-v2.exe`
4. Click **Start** and wait for the browser to open

</details>

<details>
<summary><strong>Linux</strong></summary>

1. Download the latest `intenserp-next-v2-linux-x64.tar.gz` from [Releases](https://github.com/LyubomirT/intense-rp-next/releases)
2. Extract and run:

```bash
tar -xzf intenserp-next-v2-linux-x64.tar.gz
cd intense-rp-next
chmod +x intenserp-next-v2
./intenserp-next-v2
```

If it complains about missing libraries, you may need Qt6 deps installed on your system. The best way is to install the `qt6-base` package via your package manager, but if it doesn't stop you can just install the missing libs manually.

</details>

<details>
<summary><strong>From source</strong> (for devs)</summary>

Requirements: Python 3.12+ (3.13 recommended)

```bash
git clone https://github.com/LyubomirT/intense-rp-next.git
cd intense-rp-next

python -m venv venv

source venv/bin/activate  # Linux/Mac
# or: venv\\Scripts\\activate  # Windows

pip install -r requirements.txt
python main.py
```

</details>

## Connect SillyTavern (or any OpenAI-compatible client)

Once the app says **Running (Port 7777)**:

| Setting | Value |
|---|---|
| Endpoint | `http://127.0.0.1:7777/v1` |
| API | OpenAI-compatible chat completions |
| API key | Leave blank (unless you enabled API keys) |
| Model | `deepseek-auto` |

Available model IDs:

- `deepseek-auto` (uses your IntenseRP settings)
- `deepseek-chat` (forces DeepThink off)
- `deepseek-reasoner` (forces DeepThink on, Send DeepThink follows your setting)

If you change the port in Settings, update the endpoint to match (example: `http://127.0.0.1:YOUR_PORT/v1`).

## Quick troubleshooting 🧯

- **Browser takes forever on first run**: it may be downloading/verifying Chromium. Let it cook, then try again.
- **Client cannot connect**: confirm the app says **Running**, and the endpoint matches your port (`http://127.0.0.1:7777/v1` by default).
- **401 Unauthorized**: you probably enabled API keys in Settings. Either disable them or add a key in your client.
- **Login loops / stuck sign-in**: try disabling Persistent Sessions, or clear the profile in Settings (it wipes saved cookies).
- **Slow responses**: requests are queued (one at a time), and DeepThink can add extra time.

Tip: enable the console and/or logfiles before reporting issues. Logs help a lot when diagnosing!

</details>

## What you get ✨

There are a few highlights I think are worth calling out. Most have been in v1 as well, but v2 has them all better and in a cleaner way.

- 🖥️ A desktop UI that starts/stops everything for you (and doesn't require terminal work)
- 🔌 An OpenAI-compatible API under `/v1` for SillyTavern and other OpenAI-compatibles
- 🧩 A formatting pipeline: templates, divider, injection, name detection
- 🧠 DeepSeek behavior toggles: DeepThink, Search, file upload mode, clean regeneration, anti-censorship
- 🔐 Optional LAN mode and API keys
- 🪵 Built-in extensive logging: console window, log files, console dump
- ♻️ Built-in v1 migrator + built-in update flow (when running packaged builds)

## Provider support

Current:

- DeepSeek (usable; in "verification" stage)

Planned (not implemented yet):

- GLM Chat
- Moonshot

More detail lives in `docs/` (best viewed as the MkDocs site - see below).

## Documentation

There is a full docs site with screenshots and details if you want to dig a bit deeper:

Check out [the docs site here](https://intense-rp-next.readthedocs.io/en/latest/).

## Security and privacy notes

- IntenseRP is designed for local or LAN use. Do not expose it to the public internet unless you know what you're doing.
- If you enable **Available on LAN**, consider enabling **API Keys** too.
- Your config directory contains sensitive data (credentials, API keys, session cookies). Treat it like a password vault.

## Contributing 🤝

Bug reports, suggestions, and PRs are welcome!! 💖

Just note a few things:

- This is still a fast-moving codebase. A PR can become outdated quickly.
- Provider behavior changes are inevitable (web UIs are a moving target).
- I move this in a very "me" way due to how fast things change, meaning not every idea will align with my vision even if it's objectively good.

If you're not sure where to start, open an issue first - it saves everyone time.

## Contributors ❤️

| <a href="https://github.com/LyubomirT"><img src="https://avatars.githubusercontent.com/u/127299159?s=500&v=4" width="80" height="80" alt="LyubomirT" /></a> | <a href="https://github.com/Omega-Slender"><img src="https://avatars.githubusercontent.com/u/134849645?s=500&v=4" width="80" height="80" alt="Omega-Slender" /></a> | <a href="https://github.com/Deaquay"><img src="https://avatars.githubusercontent.com/u/103206423?s=500&v=4" width="80" height="80" alt="Deaquay" /></a> | <a href="https://github.com/Targren"><img src="https://avatars.githubusercontent.com/u/11566412?s=500&v=4" width="80" height="80" alt="Targren" /></a> | <a href="https://github.com/fushigipururin"><img src="https://avatars.githubusercontent.com/u/96440827?s=500&v=4" width="80" height="80" alt="fushigipururin" /></a> | <a href="https://github.com/Vova12344weq"><img src="https://avatars.githubusercontent.com/u/131772052?s=500&v=4" width="80" height="80" alt="Vova12344weq" /></a> |
|:---:|:---:|:---:|:---:|:---:|:---:|
| <a href="https://github.com/LyubomirT">LyubomirT</a> | <a href="https://github.com/Omega-Slender">Omega-Slender</a> | <a href="https://github.com/Deaquay">Deaquay</a> | <a href="https://github.com/Targren">Targren</a> | <a href="https://github.com/fushigipururin">fushigipururin</a> | <a href="https://github.com/Vova12344weq">Vova12344weq</a> |
| Project Maintainer | Original Creator | Contributor to OG | Feedback & Proposals, Code | Code and Concept Contributor | Early Testing, Bug Reports, Suggestions |

Full list: https://github.com/LyubomirT/intense-rp-next/graphs/contributors

## License

IntenseRP Next v2 is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

>[!NOTE]
> Original IntenseRP API by Omega-Slender is also MIT-licensed, but previously was a [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) project. This v2 rewrite is a new codebase and is not a derivative work, so the license has been switched to MIT for simplicity. I'm not affiliated with [Omega-Slender](https://github.com/Omega-Slender), even if I'm the official successor to their project (starting from v1).

## Credits

- FastAPI, Pydantic, Uvicorn
- PySide6 (Qt)
- Playwright + Patchright
- Feather Icons
- SillyTavern (client ecosystem)
- IntenseRP API (Omega-Slender) - original inspiration
- Me (LyubomirT) - for doing all the work :D
- RossAscends (for STMP)
