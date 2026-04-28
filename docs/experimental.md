---
icon: material/flask-outline
---

# :material-flask-outline: Experimental

This section contains features that are still considered experimental. They can be extremely useful, but they can also change quickly, behave differently between providers, or get removed/reworked without much warning.

!!! warning "Expect changes"
    If you enable experimental features, keep a backup of your `[config_dir]` (Settings -> System -> Backup & Restore) so you can roll back if something goes wrong.

Experimental features currently include:

<div class="grid cards" markdown>

-   :material-source-branch: **Providers in Parallel**

    Keeps multiple provider browser windows alive at once and routes requests by the legacy provider-prefixed model IDs, which helps when you switch between providers often.

    [:arrow_right: Read Providers in Parallel docs](experimental/providers-in-parallel.md)

-   :material-lan-connect: **Parallel Request Queue**

    Builds on top of Providers in Parallel and lets different active provider lanes work on API requests at the same time. Useful for shared API setups, but still very experimental.

    [:arrow_right: Read Parallel Request Queue docs](experimental/parallel-request-queue.md)

-   :material-source-branch-plus: **Full Parallelization**

    Adds multiple account-backed instances for the same enabled provider, so queue parallelization can spread work across providers and across accounts.

    [:arrow_right: Read Full Parallelization docs](experimental/full-parallelization.md)

-   :material-file-code-outline: **Loadouts**

    Lets you build and edit provider-specific Formatting + Provider Behavior presets directly in Settings, then switch the active one per provider.

    [:arrow_right: Read Loadouts docs](experimental/loadouts.md)

-   :material-remote-desktop: **Remote Control**

    Gives you a tiny browser-side control panel for **Stop**, **Restart**, **Hotswap**, **Switch Account**, and live logs. Very handy for when you don't want to go back to your PC every time.

    [:arrow_right: Read Remote Control docs](experimental/remote-control.md)

-   :material-bell-ring-outline: **Changelog Button**

    Adds a small bell button next to **Help** that opens the News page and lights up when new items are available. You can hide it via **Settings** -> **Experimental** -> **Changelog Button**.

    [:arrow_right: Read the News page](news.md)

</div>
