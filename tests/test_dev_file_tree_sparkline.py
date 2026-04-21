"""DevFileTree per-row sparkline tests (M1b-extra x_001/x_002/x_003)."""
from __future__ import annotations

from agentboard.analytics.diff_parser import DiffFile


def test_render_tree_appends_sparkline_when_data_provided() -> None:
    """x_001: render_tree appends colored sparkline markup per row when
    per_file_scrubber_data has an entry for that file's path.
    """
    from agentboard.tui.dev_file_tree import render_tree

    files = [
        DiffFile(path="src/foo.py", added=10, removed=2),
        DiffFile(path="src/bar.py", added=1, removed=0),
    ]
    scrubber = {
        "src/foo.py": ["tdd_red", "tdd_green", "redteam"],
        # bar.py deliberately missing from data to verify per-path handling
    }
    out = render_tree(files, reviewed=set(), per_file_scrubber_data=scrubber)

    # foo.py row should contain a sparkline with color markup
    assert "src/foo.py" in out
    assert "▇" in out, "sparkline glyph missing"
    # Color markup (Rich format)
    assert "[#" in out, "color markup missing"

    # bar.py row should NOT have a sparkline (no data)
    bar_row = [l for l in out.split("\n") if "bar.py" in l][0]
    assert "▇" not in bar_row, "bar.py got unexpected sparkline"


def test_render_tree_no_sparkline_when_data_none() -> None:
    """x_002: legacy behavior preserved — render_tree without scrubber_data
    produces the same output as the M1a/M1b-wiring version.
    """
    from agentboard.tui.dev_file_tree import render_tree

    files = [DiffFile(path="src/foo.py", added=10, removed=2)]
    out_legacy_style = render_tree(files, reviewed=set())
    assert "▇" not in out_legacy_style, "sparkline leaked into legacy mode"
    assert "src/foo.py" in out_legacy_style


def test_dev_file_tree_uses_markup_true() -> None:
    """x_003: DevFileTree widget instance has markup enabled so Rich
    color tags render colored cells (not raw bracket text).
    """
    from agentboard.tui.dev_file_tree import DevFileTree

    # Textual Static exposes markup via _markup or init param.
    # We verify via the `markup` init parameter being True.
    tree = DevFileTree(files=[], reviewed=set())
    # Textual Static stores markup as _markup (private) — read via attribute or init
    # To avoid private attr dependency: check the rendered output of a markup str
    # Instead of inspecting internals, just verify the update path accepts markup
    # via the wrapper: calling render with markup text should pass (smoke).
    # Runtime check: Static's `_markup` attribute is True when markup enabled
    # OR inspect init source for markup setup (implementation-agnostic).
    if hasattr(tree, "_markup"):
        assert tree._markup is True, (
            f"DevFileTree Static markup not enabled: got {tree._markup!r}"
        )
    else:
        # Fallback: source inspection for 'markup' wiring
        import inspect
        src = inspect.getsource(DevFileTree.__init__)
        assert "markup" in src, "DevFileTree must configure markup on Static"
