---
icon: material/account-switch
---

# :material-account-switch: Accounts & Credentials

IntenseRP manages provider logins using an account-based saved-accounts system.

There's nothing to enable - this is the standard way IntenseRP manages credentials now.

You can store **multiple accounts per provider**, let IntenseRP pick one on start, and (optionally) **retry a failed request by restarting the browser and rotating to a different identity**.

---

## :material-information: Recommended setup

1. Keep **Persistent Sessions** enabled (it's on by default) so you stay logged in between restarts.
2. If you want auto-login for your provider, enable **Sign In Automatically** and add at least one account in **Saved Accounts**.
3. Keep a backup of your `[config_dir]` (see [Backup & Restore](system.md#backup--restore)).
4. (Optional) Enable:
    - **Prefer the Least Used Account**: spreads usage across accounts
    - **Retry With Another Account**: retries early failures with a rotated identity

---

## :material-lightbulb: The big picture

```mermaid
flowchart TD
    A[Add accounts in Saved Accounts] --> B[Enable Sign In Automatically]
    B --> C[Start provider driver]
    C --> D["An identity is selected<br/>(account + profile)"]
    D --> E[Driver logs in]
    E --> F[API request arrives]
    F --> G[Generate response via provider UI]
    G --> H{Meaningful output?}
    H -->|Yes| I[Forward response to client]
    H -->|No, early failure| J{Retry With Another Account enabled?}
    J -->|No| K[Return error / empty output]
    J -->|Yes| L[Restart driver + rotate identity]
    L --> G
```

Under the hood, accounts are used by the drivers at login time, and by the request retry logic when it decides whether to rotate and try again.

---

## :material-play-circle: Quick setup

1. Open **Settings**.
2. Go to **Provider and Login**.
3. In **Sign-In and Accounts**, (optional) enable **Sign In Automatically**.
4. Open **Saved Accounts** and add one or more accounts for your provider.
5. (Optional) Enable **Prefer the Least Used Account** and/or **Retry With Another Account**.
6. Click **Save**, then **Stop -> Start** the provider driver (so changes take effect).

!!! note "Migration from older versions"
    If you previously used the old per-provider fields (single email/password), IntenseRP automatically imports them into **Saved Accounts** on startup (before you open it).

    If you already have accounts saved for a provider, IntenseRP will not overwrite them with legacy credentials.

### Settings overview

| Setting | Where | What it does |
|---|---|---|
| **Saved Accounts** | Settings -> Provider and Login -> Sign-In and Accounts | Add and manage accounts per provider |
| **Sign In Automatically** | Settings -> Provider and Login -> Sign-In and Accounts | Uses a saved account for login |
| **Prefer the Least Used Account** | Settings -> Provider and Login -> Sign-In and Accounts | Chooses the least recently used account when starting the driver |
| **Retry With Another Account** | Settings -> Provider and Login -> Sign-In and Accounts | On early failures, restarts the driver and retries once with a rotated identity |

---

## :material-account-switch: How account selection works

Accounts are stored per provider (DeepSeek / GLM Chat / Moonshot / QwenLM / Google AI Studio).

When **Sign In Automatically** is enabled, IntenseRP selects an account on driver start and logs in automatically. If it is disabled, you can still log in manually and use **Keep Provider Sessions Signed In** to stay signed in between restarts.

There are two selection modes:

- If **Prefer the Least Used Account** is disabled, IntenseRP picks a random account from the list.
- If **Prefer the Least Used Account** is enabled, IntenseRP prefers the account that was used the longest time ago (accounts that have never been used are preferred first).

This is tracked in an internal "last used" map stored alongside the encrypted credentials.

!!! tip "Want to force a specific account?"
    For now, you cannot pin a specific row. If you need a specific account, keep only that account in **Saved Accounts** (remove others temporarily).

---

## :material-cookie: Persistent Sessions (profiles)

Persistent Sessions works the same way as always: it stores a reusable browser profile (cookies, local storage, etc.) so you stay logged in between restarts.

IntenseRP stores one profile per identity (account or manual) under:

```
[config_dir]/playwright_profiles/accounts/deepseek/<hash>/
[config_dir]/playwright_profiles/accounts/glm_chat/<hash>/
[config_dir]/playwright_profiles/accounts/moonshot_kimi/<hash>/
[config_dir]/playwright_profiles/accounts/qwenlm/<hash>/
[config_dir]/playwright_profiles/accounts/aistudio/<hash>/
```

The `<hash>` is derived from your email (SHA-256, truncated). It's only there so your email doesn't show up in folder names.

If no account is selected (for example Auto Login is off / manual login), the profile name falls back to:

```
[config_dir]/playwright_profiles/accounts/<provider>/manual
```

!!! note "Older installs may have Legacy profiles"
    Older versions stored profiles directly under:
    `playwright_profiles/<provider>/`.
    The Settings UI can still list and delete both Legacy and account-based profiles.

---

## :material-refresh: Retry With Another Account

This option is meant to handle cases where a provider fails early and returns no meaningful output (for example, a rate limit / quota style error).

When enabled, each request gets up to **two attempts**. If the first attempt produces no meaningful output, IntenseRP restarts the driver, rotates the identity, and retries once.

!!! note "This restarts the browser"
    The retry is implemented by closing and restarting the provider driver, which means the provider browser window is relaunched.

### What "rotate identity" means

IntenseRP tries two strategies, in this order:

1. Switch to a different **account** (another saved login), if you have more than one.
2. If there's only one account available, create a new **profile slot** for that same account (a fresh browser profile) and restart.

The second option is most useful when **Persistent Sessions** are enabled, because it forces a clean session/profile for the same login.

---

## :material-lock: Where account data is stored (and how secure it is)

The Saved Accounts manager stores its data inside your config directory:

```
[config_dir]/accounts/credentials.json.enc
[config_dir]/accounts/usage.json.enc
```

These files are encrypted using the same `settings.key` used for your main settings file:

```
[config_dir]/settings.key
```

!!! note "Security reality check"
    This is encryption-at-rest for the config files, not a password manager. If someone has access to your config directory, they can usually access the key too. Treat `[config_dir]` as sensitive.

---

## :material-chat-alert: Provider notes

**DeepSeek:** if Auto Login is enabled but no DeepSeek accounts are configured, IntenseRP waits for manual login.

**GLM Chat:** IntenseRP can fill email/password, but GLM still requires a CAPTCHA step. Persistent Sessions are strongly recommended so you don't have to repeat the CAPTCHA every start.

**Moonshot:** login is Google-based. Auto Login can try to fill the popup, but Google may still require manual confirmation/challenges depending on your account security settings.

**QwenLM:** standard email/password login. Auto Login can fill credentials automatically.

**Google AI Studio:** Google login with optional credential autofill. Persistent Sessions are strongly recommended because Google may still ask for manual confirmation/challenge steps.

---

## :material-frequently-asked-questions: Quick FAQ

??? question "Where did the provider email/password fields go?"
    Use **Settings -> Provider and Login -> Sign-In and Accounts -> Saved Accounts**.

??? question "Do I need to open Saved Accounts after updating?"
    Usually no. If you had legacy saved credentials, IntenseRP imports them automatically on startup.

??? question "How do I switch accounts?"
    - Enable **Prefer the Least Used Account** to spread usage across accounts, or
    - Use **Switch Account** in the Stop menu, or
    - Enable **Retry With Another Account** so early failures can trigger an automatic rotation.

??? question "Can I see which account is active?"
    Not in the UI yet. You can usually tell from the UI of the provider's frontend, as it often shows the logged-in email or profile name. In the future, I may add an indicator in IntenseRP's UI as well.

---

## :material-arrow-right: Related pages

[:material-key: Login & Sessions](login-sessions.md)

[:material-cog: System (config dir, profiles, backups)](system.md)

[:material-bug: Troubleshooting](../hands/troubleshooting.md)
