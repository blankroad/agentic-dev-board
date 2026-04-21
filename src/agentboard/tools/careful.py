from __future__ import annotations

import re
from dataclasses import dataclass


# Patterns that are destructive by nature — block outright or require explicit approval
_HARD_BLOCK = [
    re.compile(r"\brm\s+-rf?\s+/\s*$"),             # rm -rf /
    re.compile(r"\brm\s+-rf?\s+/\*"),                # rm -rf /*
    re.compile(r"\brm\s+-rf?\s+~(?:/|$)"),           # rm -rf ~
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),  # fork bomb
    re.compile(r"\bdd\s+.*of=/dev/"),                # dd if=... of=/dev/sda
    re.compile(r">\s*/dev/(sda|nvme|hda)"),          # > /dev/sda
    re.compile(r"mkfs\.[a-z0-9]+\s+/dev/"),          # format disk
]

# Patterns that are destructive in context — warn and require strict=False to run
_WARN = [
    (re.compile(r"\brm\s+-rf?\b"), "recursive file deletion"),
    (re.compile(r"\bgit\s+push\s+.*--force\b"), "force push (can overwrite upstream)"),
    (re.compile(r"\bgit\s+push\s+.*-f\b(?!\w)"), "force push (-f flag)"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "hard reset (loses uncommitted work)"),
    (re.compile(r"\bgit\s+clean\s+-[a-z]*f"), "git clean -f (removes untracked files)"),
    (re.compile(r"\bgit\s+branch\s+-D\b"), "force branch delete"),
    (re.compile(r"\bchmod\s+(-R\s+)?0?777\b"), "chmod 777 (world-writable)"),
    (re.compile(r"\bsudo\s+rm\b"), "sudo rm"),
    (re.compile(r"\bcurl\s+[^|]+\|\s*(sh|bash|zsh)\b"), "curl pipe shell (untrusted code execution)"),
    (re.compile(r"\bwget\s+[^|]+\|\s*(sh|bash|zsh)\b"), "wget pipe shell (untrusted code execution)"),
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "SQL DROP TABLE"),
    (re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE), "SQL TRUNCATE TABLE"),
    (re.compile(r"\beval\s*\("), "eval() call"),
    (re.compile(r"\bexec\s*\("), "exec() call"),
]


@dataclass
class DangerVerdict:
    level: str                  # "safe" | "warn" | "block"
    pattern: str = ""
    reason: str = ""


def check_command(cmd: str) -> DangerVerdict:
    for hard in _HARD_BLOCK:
        if hard.search(cmd):
            return DangerVerdict(
                level="block",
                pattern=hard.pattern,
                reason=f"irreversibly destructive command matched: {hard.pattern}",
            )
    for pat, desc in _WARN:
        if pat.search(cmd):
            return DangerVerdict(
                level="warn",
                pattern=pat.pattern,
                reason=f"potentially destructive ({desc})",
            )
    return DangerVerdict(level="safe")
