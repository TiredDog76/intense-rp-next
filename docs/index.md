---
icon: material/home
---

# Welcome to IntenseRP Next v2

<p align="center">
  <img
    src="assets/logo-strip.png"
    alt="IntenseRP Next v2 logo strip"
    style="max-width: 900px; width: 100%; height: auto;"
  />
</p>

**IntenseRP Next v2** is a complete rewrite of the original IntenseRP Next project. I rebuilt it from the ground up so that it's MUCH more stable, faster, and easier to use. It's a modern (but hacky) tool for getting free access to LLMs via their web apps, and connecting it to SillyTavern (or other clients) for RPs.

<div class="grid cards" markdown>

-   :material-rocket-launch: **Getting Started**

    New to IntenseRP? Set up your environment and start roleplaying in minutes.

    [:arrow_right: Get Started](getting-started.md)

-   :material-transfer: **Migration Guide**

    Coming from **IntenseRP Next v1** or **IntenseRP API** (by Omega-Slender)? Learn how to move to v2.

    [:arrow_right: Migrate to v2](migration.md)

-   :material-star-four-points: **Features**

    Explore the new architecture, tech stack, and capabilities of v2.

    [:arrow_right: See Features](features.md)

-   :material-flask-outline: **Experimental**

    Opt-in features that are still evolving (like ECE).

    [:arrow_right: Experimental](experimental.md)

</div>

## Why v2?

IntenseRP Next v2 takes an entirely different path from its predecessors. I've learned from the challenges faced by the original **IntenseRP API** (by Omega-Slender) and **IntenseRP Next v1**.

### The "Rewrite" Philosophy

Instead of patching old code, I started from scratch. So, now we have:

*   **Modern Tech Stack**: I built it with **Python 3.13+**, **FastAPI**, **PySide6**, and **Playwright**.
*   **Stability First**: For v1, I used the original HTML scraping method, with my own then-buggy network interception. Now, v2 only has native network interception thanks to Playwright.
*   **Performance**: Optimized for speed and low resource usage.
*   **Maintainability**: A modular codebase that is easier to contribute to and extend.

### Key Differences

| Feature | IntenseRP API / Next v1 | IntenseRP Next v2 |
| :------ | :---------------------- | :---------------- |
| **Backend** | Python (Flask) | Python (FastAPI) |
| **UI** | Customtkinter | Native (PySide6) |
| **Automation** | SeleniumBase (UC) | Playwright (Patchright) |
| **Stability** | Workaround-based | Native patching |
| **Scraping** | HTML Parsing + Buggy Network Interception | Network Interception |

!!! note "Work in Progress"
    This project is currently under active development. Features are being added rapidly. Please check the [GitHub Repository](https://github.com/LyubomirT/intense-rp-next) for the latest updates.

## Community & Support

Most of the support resources are still being built. Meanwhile, you can:

[Contact The Dev](hands/contact.md){ .md-button }
[Report a Bug](https://github.com/LyubomirT/intense-rp-next/issues){ .md-button }
