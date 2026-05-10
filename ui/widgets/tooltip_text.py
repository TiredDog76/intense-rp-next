from __future__ import annotations

import html
import re

from ui.core.brand import BrandColors


_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def _render_plain_segment(text: str) -> str:
    rendered = html.escape(str(text or ""), quote=False)
    rendered = _BOLD_RE.sub(
        rf"<span style='font-weight: 700; color: {BrandColors.TEXT_PRIMARY};'>\1</span>",
        rendered,
    )
    rendered = _ITALIC_RE.sub(
        rf"<span style='font-style: italic; color: {BrandColors.TEXT_SOFT};'>\1</span>",
        rendered,
    )
    return rendered


def _render_inline(text: str) -> str:
    parts = re.split(r"(`[^`\n]+`)", str(text or ""))
    rendered_parts: list[str] = []

    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            code_text = html.escape(part[1:-1], quote=False)
            rendered_parts.append(
                "<span style='"
                "font-family: Consolas, Cascadia Mono, monospace; "
                "font-weight: 300; "
                f"color: {BrandColors.TEXT_PRIMARY}; "
                "background-color: #08090c;"
                f"'>&nbsp;{code_text}&nbsp;</span>"
            )
        else:
            rendered_parts.append(_render_plain_segment(part))

    return "".join(rendered_parts)


def render_tooltip_text(text: str | None) -> str:
    """
    Render the small Markdown subset used by settings helper text.

    This intentionally stays tiny and only supports inline code, bold, italics, line breaks,
    and simple "- item" / "* item" list markers. Settings copy should still be
    readable as plain text when shown somewhere that does not use rich text.
    """
    raw = str(text or "")
    if not raw:
        return ""

    lines = raw.splitlines() or [raw]
    rendered_lines: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("- ", "* ")):
            rendered_lines.append(
                f"<span style='color: {BrandColors.TEXT_SECONDARY};'>&bull;</span>&nbsp;"
                f"{_render_inline(stripped[2:])}"
            )
        else:
            rendered_lines.append(_render_inline(line))

    return f"<qt>{'<br>'.join(rendered_lines)}</qt>"
