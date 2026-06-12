---
icon: material/source-branch-plus
---

# :material-source-branch-plus: Full Parallelization (Extremely Experimental)

Full Parallelization is the heavier sibling of **Providers in Parallel** and **Parallel Request Queue**.

Providers in Parallel can keep different provider browsers alive. Parallel Request Queue lets those provider lanes work at the same time. Full Parallelization adds one more step: it can launch more than 1 browser instance for the same enabled provider, backed by different saved accounts/profiles.

That means you can parallelize across providers and across accounts for the same provider. It is powerful, and it's also very much a feature you DON'T want to enable on weaker hardware or without a specific need for it.

!!! warning "This is the heavy one"
    Each extra instance is another live provider browser. RAM, CPU, provider-side limits, login state, and account risk all matter more here.

    Keep this disabled unless you are intentionally testing high-throughput API usage.

---

## :material-toggle-switch: Enable It

:material-arrow-right: **Settings** -> **Advanced** -> **Experimental Features**

Enable these in order:

1. **Run Providers in Parallel**
2. **Parallelize API Request Queue**
3. **Full Parallelization**

After Full Parallelization is on, the enabled provider toggles get an **Instances** number input underneath them. The current provider counts as enabled, even if its toggle is forced on.

Restart the browser with **Stop -> Start** after changing these settings.

If **Launch Parallel Providers Concurrently** is enabled in the Providers in Parallel settings, these extra same-provider lanes are included in that concurrent startup too. Use **Launch in Batches** if starting all of them at once feels too heavy on your machine.

---

## :material-account-multiple: Accounts and Instance Counts

Each extra same-provider lane needs a saved account/profile. IntenseRP will not launch more account-backed instances for a provider than the number of selectable saved accounts for that provider.

If you ask for 3 DeepSeek instances but only have 2 usable DeepSeek accounts saved, IntenseRP launches 2 and logs a warning. If there are no saved accounts, it falls back to one normal manual lane instead (it can't invent accounts out of thin air after all).

The default instance count is **1**.

!!! tip "Least-used account selection"
    If **Prefer the Least Used Account** is enabled, startup account selection favors accounts with older last-used timestamps before newer ones.

---

## :material-routes: Request Routing

When multiple instances are running for a provider, new requests prefer the least-loaded available lane first. Within equally loaded lanes, IntenseRP uses service-start usage tracking:

- lanes that have not been used during this service run are picked first
- if several lanes are equally unused, one is picked randomly
- after every lane has been used, the least-recently-used lane is picked next

So with 3 active lanes, traffic spreads across the available accounts instead of piling onto the first browser.

---

## :material-refresh-alert: Retry Behavior

If **Retry With Another Account** is enabled and one full-parallel instance hits an early empty/rate-limit-like failure, only that instance restarts.

It tries to rotate to a spare saved account that is not already allocated to another running instance. If no spare account is available, that instance is closed and stays offline until the next full service restart.

Other running instances keep going.

---

## :material-alert-circle-outline: Current Limits

- Requires **Parallelize API Request Queue**.
- Changes apply on the next browser start.
- Instance counts are capped by saved accounts for that provider.
- Manual browser crashes can still stop the parallel runtime.
- Model and loadout settings remain provider-level, so same-provider instances share those choices.

This is meant for testing throughput, not for making the default setup more relaxing. The normal single-provider path is still the calmest option.

---

## :material-arrow-left: Back to Experimental

[:material-arrow-left: Experimental Overview](../experimental.md)
