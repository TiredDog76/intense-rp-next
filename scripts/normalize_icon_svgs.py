#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_COLOR_VALUE_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}$")
_COLOR_ATTR_RE = re.compile(
    r"(?P<attr>\b(?:fill|stroke|stop-color)\s*=\s*)(?P<q>[\"'])(?P<v>[^\"']+)(?P=q)",
    flags=re.IGNORECASE,
)
_STYLE_ATTR_RE = re.compile(
    r"(?P<prefix>\bstyle\s*=\s*)(?P<q>[\"'])(?P<style>[^\"']*)(?P=q)",
    flags=re.IGNORECASE,
)
_STYLE_DECL_RE = re.compile(
    r"(?P<prop>\b(?:fill|stroke|stop-color)\b)(?P<ws1>\s*):(?P<ws2>\s*)(?P<val>[^;]+)",
    flags=re.IGNORECASE,
)


def _should_replace_color(value: str) -> bool:
    raw = value.strip()
    if not raw:
        return False

    lower = raw.lower()
    if lower in {"none", "transparent", "currentcolor", "inherit", "unset", "initial"}:
        return False

    if lower.startswith(("var(", "url(")):
        return False

    if _COLOR_VALUE_HEX_RE.fullmatch(raw):
        return True

    if lower.startswith(("rgb(", "rgba(", "hsl(", "hsla(")):
        return True

    # Named CSS colors like "white", "black", etc.
    if re.fullmatch(r"[a-zA-Z]+", raw):
        return True

    return False


def _normalize_style_attr(style: str) -> tuple[str, bool]:
    changed = False

    def repl(m: re.Match[str]) -> str:
        nonlocal changed
        prop = m.group("prop")
        ws1 = m.group("ws1")
        ws2 = m.group("ws2")
        val_raw = m.group("val")
        val_stripped = val_raw.strip()

        important = ""
        if val_stripped.lower().endswith("!important"):
            important = " !important"
            val_stripped = val_stripped[: -len("!important")].strip()

        if not _should_replace_color(val_stripped):
            return m.group(0)

        changed = True
        return f"{prop}{ws1}:{ws2}currentColor{important}"

    new_style = _STYLE_DECL_RE.sub(repl, style)
    return new_style, changed


def normalize_svg_text(text: str) -> tuple[str, bool]:
    changed = False

    def repl_attr(m: re.Match[str]) -> str:
        nonlocal changed
        value = m.group("v")
        if not _should_replace_color(value):
            return m.group(0)
        changed = True
        return f'{m.group("attr")}{m.group("q")}currentColor{m.group("q")}'

    text = _COLOR_ATTR_RE.sub(repl_attr, text)

    def repl_style(m: re.Match[str]) -> str:
        nonlocal changed
        style = m.group("style")
        new_style, style_changed = _normalize_style_attr(style)
        if style_changed:
            changed = True
        return f'{m.group("prefix")}{m.group("q")}{new_style}{m.group("q")}'

    text = _STYLE_ATTR_RE.sub(repl_style, text)
    return text, changed


def _iter_svg_files(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*.svg") if p.is_file()])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize SVG icons by replacing hardcoded fill/stroke colors with currentColor."
    )
    parser.add_argument(
        "--icons-dir",
        default="ui/assets/icons",
        help="Directory to scan recursively (default: ui/assets/icons).",
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero if changes are needed.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes but do not write files.")
    args = parser.parse_args(argv)

    root = Path(args.icons_dir)
    if not root.exists():
        print(f"Error: icons dir does not exist: {root}", file=sys.stderr)
        return 2

    changed_files: list[Path] = []
    for path in _iter_svg_files(root):
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            original = path.read_text(encoding="utf-8", errors="replace")

        updated, changed = normalize_svg_text(original)
        if not changed:
            continue

        changed_files.append(path)
        if not args.dry_run and not args.check:
            path.write_text(updated, encoding="utf-8")

    if changed_files:
        print(f"SVGs needing changes: {len(changed_files)}")
        for p in changed_files:
            print(f"- {p.as_posix()}")
        if args.check:
            return 1
    else:
        print("No changes needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

