"""Converters from plan.md markdown to md / html / confluence."""

from __future__ import annotations

import pytest


def test_to_markdown_is_identity() -> None:
    from devboard.docs.export import to_markdown

    src = "# Title\n\n## Section\n\nhello\n"
    assert to_markdown(src) == src


def test_to_markdown_on_empty_string() -> None:
    """# guards: edge-case-red-rule
    edge: empty input — must not raise, return empty."""
    from devboard.docs.export import to_markdown
    assert to_markdown("") == ""


def test_to_confluence_converts_h2_to_h2_dot() -> None:
    from devboard.docs.export import to_confluence
    out = to_confluence("## Problem\nbody\n")
    assert "h2. Problem" in out
    assert "## Problem" not in out


def test_to_confluence_converts_h3_to_h3_dot() -> None:
    from devboard.docs.export import to_confluence
    assert "h3. Sub" in to_confluence("### Sub\n")


def test_to_confluence_converts_fenced_code_block() -> None:
    from devboard.docs.export import to_confluence
    src = "```python\nx = 1\n```\n"
    out = to_confluence(src)
    assert "{code:python}" in out
    assert "{code}" in out
    assert "x = 1" in out
    assert "```" not in out


def test_to_confluence_converts_markdown_table() -> None:
    src = "| a | b |\n|---|---|\n| c | d |\n"
    from devboard.docs.export import to_confluence
    out = to_confluence(src)
    assert "|| a || b ||" in out
    assert "| c | d |" in out
    assert "|---|" not in out


def test_to_html_wraps_in_doctype() -> None:
    from devboard.docs.export import to_html
    out = to_html("# Title\n")
    assert "<!DOCTYPE html>" in out or "<html" in out.lower()


def test_render_dispatches_by_format() -> None:
    """# guards: edge-case-red-rule
    edge: integration wiring — `render()` must route to the 3 converters."""
    from devboard.docs.export import render
    assert "h2." in render("## x\n", "confluence")
    assert "## x" in render("## x\n", "md")
    html = render("## x\n", "html")
    assert "<h2" in html.lower() or "<!DOCTYPE" in html


def test_render_rejects_unknown_format() -> None:
    from devboard.docs.export import render
    with pytest.raises(ValueError):
        render("# x", "pdf")
