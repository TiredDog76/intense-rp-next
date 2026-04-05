---
icon: material/bug
---

# :material-bug: Bug Report

This window creates a quick `.zip` bundle you can attach to a GitHub issue or share privately for troubleshooting.

It is meant to save time when something is broken, not to replace normal backups.

---

## :material-cursor-default-click: How to open it

1. Open **Help & Extras**
2. Click **Bug Report**

---

## :material-toggle-switch: Before it works

The tool is opt-in. It only has anything useful to export if you turn on one or both of these first:

:material-arrow-right: **Settings** -> **Logs and Troubleshooting** -> **Bug Reports**

- **Keep an Internal Log**
- **Also Save the Last Prompt**

If both are off, the window will refuse to create a bundle and tell you to either enable them first or collect files manually.

---

## :material-folder-zip: What goes into the zip

Depending on what you enabled, the bundle can include:

- `internal-log.txt`
- `latest-prompt.txt`
- `latest-system-prompt.txt` for Google AI Studio, when the separate system prompt field was used
- `latest-prompt-metadata.json`
- `prompts/prompt-index.json`
- provider-specific prompt files and metadata inside `prompts/`

The prompt index and metadata files include timestamps, so you can tell when each saved prompt snapshot was captured. The newest saved prompt is also exported separately as `latest-prompt.txt`.

---

## :material-shield-alert: Privacy notes

This feature can still include sensitive data, so treat the bundle like something you would not casually toss into a public chat.

The internal diagnostics log tries to redact a few things automatically:

- full URLs are trimmed down to just the scheme + domain
- email addresses are replaced with labels like `[email 1]`
- API key names are replaced with `[API key name]`
- IPv4 addresses are replaced with `XXX.XXX.XXX.XXX` while keeping ports

That helps, but it is not magic. Prompts are still prompts, file paths can still be revealing, and there may be context you do not want to share.

!!! warning "Still review before sharing"
    The bundle is safer than dumping raw debug logs, but it is not guaranteed to be scrubbed perfectly. Give it a quick look before uploading it anywhere public.

---

## :material-progress-clock: How export works

When you click **Create Bug Report Zip**, the window asks where to save it, then builds the archive in a background thread. That part is on purpose, so the UI does not freeze on slower machines.

The default file name looks like this:

`irp-bug-report-YYYYMMDD-HHMMSS.zip`

---

## :material-note-text: Note about storage

Prompt snapshots are stored per provider. If you are using **Providers in Parallel**, the bundle can include more than one saved prompt snapshot, and the prompt index will show which one was captured most recently overall.

Also, if you turn the Bug Report settings back off later, IntenseRP clears those saved diagnostics artifacts right after saving settings. So this is not a hidden forever-archive.

!!! warning "About disabling"
    The log and prompt storage being deleted also means that you won't be able to create a bug report bundle with anything useful in it until you turn those settings back on and reproduce the issue again.

---

## :material-arrow-left: Back

[:material-arrow-left: Util Reference](../util-reference.md)
