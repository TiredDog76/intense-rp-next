from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Optional

from utils.logger import Logger


PATCH_MARKER_START = "// --- IRP Next STMP patcher (names) ---"
PATCH_MARKER_END = "// --- /IRP Next STMP patcher (names) ---"


@dataclass(frozen=True)
class STMPPatcherScan:
    stmp_root: Path
    server_js: Path
    api_calls: Optional[Path]
    is_patched: bool
    has_legacy_irp_next_field: bool


def scan_stmp_installation(stmp_root: str | Path) -> STMPPatcherScan:
    root = Path(stmp_root).expanduser().resolve()
    server_js = root / "server.js"

    api_calls = None
    has_legacy = False
    is_patched = False

    if root.is_dir():
        candidate = root / "src" / "api-calls.js"
        if candidate.is_file():
            api_calls = candidate
            try:
                text = api_calls.read_text(encoding="utf-8", errors="replace")
                is_patched = PATCH_MARKER_START in text
                has_legacy = ("'irp-next'" in text) or ('"irp-next"' in text)
            except Exception:
                pass

    return STMPPatcherScan(
        stmp_root=root,
        server_js=server_js,
        api_calls=api_calls,
        is_patched=is_patched,
        has_legacy_irp_next_field=has_legacy,
    )


def patch_stmp_installation(stmp_root: str | Path) -> tuple[bool, str]:
    scan = scan_stmp_installation(stmp_root)

    if not scan.stmp_root.is_dir():
        return False, "Selected path is not a folder."

    if not scan.server_js.is_file():
        return False, "Not an STMP folder (missing server.js)."

    if scan.api_calls is None:
        return False, "Could not find src/api-calls.js in this STMP folder."

    api_calls_path = scan.api_calls

    try:
        original_text = api_calls_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Failed to read api-calls.js: {e}"

    if PATCH_MARKER_START in original_text:
        return True, "STMP already looks patched (IRP Next patch marker found)."

    patched_text, detail = _apply_patch_to_api_calls_text(original_text)
    if patched_text is None:
        return False, detail

    try:
        backup_path = _make_backup(api_calls_path)
    except Exception as e:
        return False, f"Failed to create backup for api-calls.js: {e}"

    try:
        api_calls_path.write_text(patched_text, encoding="utf-8")
    except Exception as e:
        try:
            shutil.copy2(backup_path, api_calls_path)
        except Exception:
            pass
        return False, f"Failed to write patched api-calls.js (restored backup): {e}"

    Logger.success(f"STMP patch applied: {api_calls_path}")
    return True, f"Patch applied successfully.\nBackup created: {backup_path}"


def _make_backup(target_file: Path) -> Path:
    parent = target_file.parent
    base_name = target_file.name + ".irpnext.bak"
    backup_path = parent / base_name

    if backup_path.exists():
        for i in range(2, 1000):
            candidate = parent / f"{target_file.name}.irpnext.bak{i}"
            if not candidate.exists():
                backup_path = candidate
                break

    shutil.copy2(target_file, backup_path)
    return backup_path


def _apply_patch_to_api_calls_text(original_text: str) -> tuple[Optional[str], str]:
    newline = "\r\n" if "\r\n" in original_text else "\n"

    insertion_re = re.compile(
        r"^(?P<indent>[ \t]*)resolve\(\s*\[\s*CCMessageObj\s*,\s*ChatObjsInPrompt\s*,\s*lastInContextMessageID\s*\]\s*\)\s*;\s*$",
        re.MULTILINE,
    )
    match = insertion_re.search(original_text)
    if not match:
        return None, "Could not locate the expected insertion point in api-calls.js (resolve([...]))."

    indent = match.group("indent")

    patch_lines = [
        f"{indent}{PATCH_MARKER_START}",
        f"{indent}// Adds OpenAI-style per-message names for IntenseRP (and keeps legacy 'irp-next' for compat).",
        f"{indent}try {{",
        f"{indent}    if (Array.isArray(CCMessageObj)) {{",
        f"{indent}        for (const msg of CCMessageObj) {{",
        f"{indent}            if (!msg || typeof msg !== 'object') continue;",
        f"{indent}            if (msg.role !== 'user' && msg.role !== 'assistant') continue;",
        f"{indent}            if (typeof msg.content !== 'string') continue;",
        f"{indent}            if (msg.name && msg['irp-next']) continue;",
        f"{indent}            const colonIndex = msg.content.indexOf(':');",
        f"{indent}            if (colonIndex <= 0 || colonIndex > 64) continue;",
        f"{indent}            const guessedName = msg.content.slice(0, colonIndex).trim();",
        f"{indent}            if (!guessedName) continue;",
        f"{indent}            if (!msg.name) msg.name = guessedName;",
        f"{indent}            if (!msg['irp-next']) msg['irp-next'] = guessedName;",
        f"{indent}        }}",
        f"{indent}    }}",
        f"{indent}}} catch (e) {{",
        f"{indent}    // Keep original behavior if anything goes wrong.",
        f"{indent}}}",
        f"{indent}{PATCH_MARKER_END}",
        "",
    ]

    patch_block = newline.join(patch_lines)

    patched = original_text[: match.start()] + patch_block + original_text[match.start() :]
    return patched, "OK"

