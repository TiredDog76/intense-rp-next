---
icon: material/account-multiple
---

# :material-account-multiple: STMP Support

IntenseRP can be used as an OpenAI-compatible endpoint for **RossAscends's SillyTavern MultiPlayer (STMP)**.

RossAscends's STMP works fine out of the box, but it currently does **not** send per-message names. That means IntenseRP cannot automatically show the real user/character names unless STMP is patched.

This patcher targets RossAscends's STMP specifically. Other multiplayer projects may have a different code layout.

---

## :material-account-search: Why a patch is needed

IntenseRP can detect names from the standard Chat Completion message object format:

```json
{ "role": "user", "name": "Sophie", "content": "Hello!" }
```

RossAscends's STMP does not include the `name` field, so IntenseRP falls back to generic names ("User" / "Character") unless you use another name-passing method.

---

## :material-puzzle-edit-outline: Using the STMP patcher

1. Open **Help & Extras**
2. Click **STMP Patcher**
3. Select your RossAscends STMP folder (it must contain `server.js`)
4. Confirm the patch
5. Restart STMP

The patcher edits `src/api-calls.js` and creates a backup next to it.

!!! note "Name field compatibility"
    IntenseRP supports both:
    
    - Standard `name`
    - Legacy `irp-next` (used by the v1 patcher)

!!! warning "STMP license"
    RossAscends's STMP is licensed under the GNU AGPL. Patching modifies your local copy. If you run a modified STMP server for other users, make sure you comply with STMP's license requirements.

---

## :material-brush: IntenseRP settings

To make IntenseRP actually use message names:

:material-arrow-right: **Settings** → **Formatting** → **Name Behavior** → **Message Objects**

For more details on name detection, see:

:material-arrow-right: [Formatting → Name Detection](formatting.md#name-detection)
