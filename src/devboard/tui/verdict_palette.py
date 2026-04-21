"""Verdict palette — maps verdict_source strings to (letter, color) tuples
so the plan / review / process widgets share one visual language.

Pure function. No Textual imports here — we return color names only,
letting widgets feed them into Rich styles or Textual CSS.
"""

from __future__ import annotations

_PALETTE: dict[str, tuple[str, str]] = {
    "PASS": ("P", "green"),
    "WARN": ("W", "yellow"),
    "FAIL": ("F", "red"),
    "SECURE": ("S", "green"),
    "VULNERABLE": ("V", "red"),
    "SURVIVED": ("S", "green"),
    "BROKEN": ("B", "red"),
    "APPROVED": ("A", "green"),
    "BLOCKER": ("X", "red"),
    "BLOCKER_OVERRIDDEN": ("O", "yellow"),
}


def map_verdict(verdict: str | None) -> tuple[str, str]:
    """Return (letter, color) for a verdict_source string.

    Unknown / None / empty → ("·", "grey50") for "in-flight" rendering.
    """
    if not verdict:
        return ("·", "grey50")
    key = verdict.strip().upper()
    return _PALETTE.get(key, ("·", "grey50"))
