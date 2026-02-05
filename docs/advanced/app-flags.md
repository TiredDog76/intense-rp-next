---
icon: material/flag-outline
---

# :material-flag-outline: App Flags

App Flags are hidden persistent key/value entries used for internal one-time behaviors (for example migrations).

They are not exposed in the Settings UI.

---

## :material-database-lock: Storage and encryption

App Flags are stored in your active config directory:

```
[config_dir]/appflags.json.enc
```

This file is encrypted using the same key as regular settings:

```
[config_dir]/settings.key
```

---

## :material-list-box-outline: Current usage

Right now, App Flags are used to track one-time ECE migration behavior:

- `ece.legacy_credentials_imported`

When this flag is set, IntenseRP knows it already attempted the first-open legacy credential import for ECE.

---

## :material-console: `--clearFlags`

You can clear all App Flags by launching IntenseRP with:

```bash
--clearFlags
```

### What it does

- Clears all entries from `appflags.json.enc`
- Exits immediately after clearing
- Does not delete normal settings, ECE credentials, or browser profiles

### Examples

=== ":material-microsoft-windows: Packaged build (Windows)"

    ```powershell
    .\intenserp-next-v2.exe --clearFlags
    ```

=== ":material-linux: Packaged build (Linux)"

    ```bash
    ./intenserp-next-v2 --clearFlags
    ```

=== ":material-language-python: Source run"

    ```bash
    python main.py --clearFlags
    ```

!!! warning "This resets one-time guards"
    Clearing flags can re-enable one-time actions (such as migration helpers) on next launch.

---

## :material-arrow-left: Back to Advanced

[:material-arrow-left: Advanced Overview](../advanced.md)
