---
icon: material/flask-outline
---

# :material-flask-outline: Experimental

This section contains features that are still considered experimental. They can be extremely useful, but they can also change quickly, behave differently between providers, or get removed/reworked without much warning.

!!! warning "Expect changes"
    If you enable experimental features, keep a backup of your `[config_dir]` (Settings -> System -> Backup & Restore) so you can roll back if something goes wrong.

Experimental features currently include:

<div class="grid cards" markdown>

-   :material-key: **Experimental Credential Engine (ECE)**

    Manage multiple login pairs per provider and optionally rotate identities when the provider returns nothing (rate-limit-like failures).

    [:arrow_right: Read ECE docs](experimental/ece.md)

-   :material-tag-text-outline: **Better Model Names**

    Use friendlier OpenAI-style model IDs (based on real base model names) like `deepseek-v3.2` / `kimi-k2.5` / `glm-5`, with `-auto` and `-think` variants.

    [:arrow_right: Read Better Model Names docs](experimental/better-model-names.md)

</div>
