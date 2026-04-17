---
icon: material/file-code-outline
---

# :material-file-code-outline: Loadouts (Experimental)

When Loadouts are enabled, IntenseRP lets you edit provider-specific **Formatting** + **Provider Behavior** presets directly inside Settings, then switch the active one per provider. In simple terms, it's like having multiple named profiles per provider that you can jump between on the fly.

---

## :material-toggle-switch: Enable it

:material-arrow-right: **Settings** -> **Advanced** -> **Experimental Features** -> **Enable Loadouts**

That toggle does 2 things:

- it turns on the loadout editor inside **Provider Behavior**
- it adds a matching loadout card inside **Formatting**

Both editor cards stay synced while the Settings window is open, so changing the provider or the loadout in 1 place updates the other one immediately.

---

## :material-view-dashboard-outline: How editing works

With Loadouts enabled, **Provider Behavior** keeps the provider switch at the top, and adds a new loadout dropdown under it.

**Formatting** gets its own blue loadout card with the same provider switch and the same dropdown, so you can jump between providers/loadouts without bouncing back and forth between sections.

DO NOTE that the provider switch selects which provider's loadouts you are editing, so you can't edit Moonshot loadouts while the provider switch is on DeepSeek, and so on.

If a provider has no loadouts yet, the dropdown stays empty except for the add control.

---

## :material-plus-circle-outline: Creating and deleting loadouts

Open the dropdown and hit the `+` row at the bottom. That turns the dropdown into an input field for the new loadout name. You can confirm with **Enter** or the check button.

New loadouts are provider-scoped, so if you are looking at **Moonshot**, the new entry belongs to Moonshot and only shows up under Moonshot later.

### Deleting

After you create at least 1 loadout for a provider, a trash icon appears next to the item when you hover over it. Click that to delete the loadout. Pretty simple.

The list refreshes immediately inside Settings. Unlike the old version of this system in v2.6.3, the list is updated immediately after creating or deleting loadouts, so you don't have to close and reopen anything.

---

## :material-swap-horizontal: Switching the active runtime loadout

The **Stop** button menu has **Switch Loadout** while Loadouts are enabled.

That menu action changes the active runtime loadout for the currently selected provider.

If the runtime is already running and you switch from the Stop menu, IntenseRP restarts the services so the newly selected loadout really takes effect.

Remote Control gets the same idea with **Switch Loadouts**. When Loadouts are enabled, the remote page hides **Switch Models** and uses the loadout switcher instead, since the model setting lives inside the selected loadout.

---

## :material-play-circle-outline: Runtime behavior

Loadouts are provider-specific, and the active loadout for each provider is independent from the others. You can have a "Creative" and "Analysis" loadout for DeepSeek, and a "Balanced" loadout for GLM, and a "Fast" loadout for Moonshot, and switch between them whenever you want.

Provider-specific toggles inside those loadouts behave the same way they do outside loadouts. So if a GLM loadout enables **Tools**, that still only takes effect when the selected GLM UI model actually supports it. No bonus chaos mode there.

If Loadouts are enabled but the provider you are about to run has no loadouts yet, startup is blocked until you create at least 1 for that provider (otherwise IntenseRP wouldn't know which one to use).

---

## :material-source-branch: Providers in Parallel

Loadouts also work with **Providers in Parallel**.

Internally, IntenseRP keeps the active loadout name per provider, so parallel runtimes do not cross the streams and accidentally send AI Studio settings into Moonshot or anything equally cursed.

---

## :material-file-replace-outline: Legacy `loadouts.json` migration

Old `loadouts.json` files are no longer used for normal runtime behavior.

If IntenseRP finds a legacy `loadouts.json` from the older v2.6.3-style system, it will try a 1-time migration, during which it will import the legacy loadouts into the encrypted GUI-backed settings store. If it succeeds, it also deletes the legacy file to avoid confusion.

If the migration fails, the file is left alone so you can fix it and try again later.

---

## :material-flag-outline: Re-running the legacy migration

The 1-time migration is guarded by an app flag. If you want to re-run it, clear app flags with:

```bash
--clearFlags
```

That resets the migration guard, so the next launch can try importing the legacy file again.

!!! danger "Don't mess with app flags unless you know what you're doing"
    App flags are used for various one-time guards and migrations. This clears **all** of them, which can have unintended consequences if you are not careful.

See also:

[:material-arrow-right: App Flags](../advanced/app-flags.md)

---

## :material-arrow-left: Back to Experimental

[:material-arrow-left: Experimental Overview](../experimental.md)
