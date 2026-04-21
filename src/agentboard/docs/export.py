"""Format converters for plan.md → md/html/confluence. Stdlib + rich only."""

from __future__ import annotations

import re


def to_markdown(text: str) -> str:
    """Identity pass-through — plan.md is already markdown."""
    return text


def to_confluence(text: str) -> str:
    """Convert standard markdown to Confluence wiki-flavored markup.

    Conversions:
    - ``` fenced code → {code:lang} / {code}
    - | a | b | / |---|---| tables → || a || b ||
    - Headings ## → h2., ### → h3., etc.
    - Bullets - → *
    - **bold** → *bold*
    - `code` → {{code}}
    """
    if not text:
        return ""

    # Fenced code blocks FIRST so `# ` inside code stays untouched by heading rules.
    def _code_block(m: re.Match) -> str:
        lang = m.group(1) or ""
        body = m.group(2)
        head = f"{{code:{lang}}}" if lang else "{code}"
        return f"{head}\n{body}{{code}}"

    out = re.sub(
        r"```([a-zA-Z0-9_+-]*)\n(.*?)```",
        _code_block,
        text,
        flags=re.DOTALL,
    )

    # Tables: header row then separator | --- | --- |, body rows unchanged.
    lines = out.splitlines(keepends=False)
    converted: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            line.startswith("|")
            and i + 1 < len(lines)
            and re.match(
                r"^\|\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|\s*$", lines[i + 1]
            )
        ):
            # Convert header row: | a | b | → || a || b ||
            converted.append(re.sub(r"\|", "||", line))
            # Skip separator line.
            i += 2
            # Body rows stay as-is.
            while i < len(lines) and lines[i].startswith("|"):
                converted.append(lines[i])
                i += 1
            continue
        converted.append(line)
        i += 1
    out = "\n".join(converted)
    if text.endswith("\n") and not out.endswith("\n"):
        out += "\n"

    # Headings (after code blocks to avoid touching text inside code).
    out = re.sub(r"(?m)^###### ", "h6. ", out)
    out = re.sub(r"(?m)^##### ", "h5. ", out)
    out = re.sub(r"(?m)^#### ", "h4. ", out)
    out = re.sub(r"(?m)^### ", "h3. ", out)
    out = re.sub(r"(?m)^## ", "h2. ", out)
    out = re.sub(r"(?m)^# ", "h1. ", out)

    # Bullets: - item → * item (preserve leading indent).
    out = re.sub(r"(?m)^(\s*)- ", r"\1* ", out)

    # Inline **bold** → *bold* (run before single-asterisk italic).
    out = re.sub(r"\*\*([^\*]+)\*\*", r"*\1*", out)

    # Inline code: `x` → {{x}}.
    out = re.sub(r"`([^`]+)`", r"{{\1}}", out)

    return out


def to_html(text: str) -> str:
    """Render plan.md to standalone HTML using rich.markdown + console.export_html."""
    from io import StringIO

    from rich.console import Console
    from rich.markdown import Markdown

    buf = StringIO()
    console = Console(file=buf, record=True, width=120)
    console.print(Markdown(text))
    return console.export_html(inline_styles=True)


def render(text: str, fmt: str) -> str:
    """Entry point: dispatch by format name."""
    if fmt == "md":
        return to_markdown(text)
    if fmt == "confluence":
        return to_confluence(text)
    if fmt == "html":
        return to_html(text)
    raise ValueError(f"unknown format: {fmt!r} (expected md|html|confluence)")
