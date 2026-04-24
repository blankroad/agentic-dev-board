"""Classify a filesystem path into Cross-Project Memory tiers.

Return values:
  - "tier1": inside an agentboard-initialized project (walks up to find .agentboard/)
  - "tier2": non-init project directory (ambient capture)
  - "skip":  home / system paths that must not be captured
"""

from pathlib import Path


def resolve_tier(path: Path) -> str:
    home = Path.home()
    # FM7 escape hatch: ~/.agentboard/ignore_paths.txt exact-prefix match wins first.
    ignore_file = home / ".agentboard" / "ignore_paths.txt"
    if ignore_file.is_file():
        try:
            ignore_body = ignore_file.read_text()
        except (OSError, UnicodeDecodeError):
            # Fail-closed per arch.md edge #11 — unreadable or binary content
            # falls through to normal tier classification instead of crashing
            # the hook that called us.
            ignore_body = ""
        path_str = str(path)
        for line in ignore_body.splitlines():
            prefix = line.strip()
            if prefix and path_str.startswith(prefix):
                return "skip"
    # Walk up looking for a project-local .agentboard/ marker.
    # Stop at home — ~/.agentboard/ is the GLOBAL store, not a tier1 marker.
    for p in [path, *path.parents]:
        if p == home:
            break
        if (p / ".agentboard").is_dir():
            return "tier1"
    if path == home:
        return "skip"
    return "tier2"
