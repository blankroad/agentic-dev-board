from __future__ import annotations

import re

from devboard.agents.base import AgentResult, run_agent
from devboard.llm.client import LLMClient, load_prompt
from devboard.models import LockedPlan
from devboard.tools.base import ToolRegistry


# Keywords that signal a diff deserves a security review
_SECURITY_KEYWORDS = [
    # Auth/session
    "auth", "login", "logout", "session", "token", "jwt", "password", "credential",
    "oauth", "saml", "cookie", "csrf", "xsrf",
    # Crypto
    "crypto", "cipher", "hash", "sign", "verify", "hmac", "secret", "private_key",
    "encrypt", "decrypt", "tls", "ssl",
    # Data access
    "sql", "query", "database", "cursor", "execute(",
    # IO
    "subprocess", "os.system", "exec(", "eval(", "shell=true",
    "pickle", "yaml.load", "marshal",
    "http", "request", "urllib", "requests.get", "fetch",
    # Path/file
    "os.path", "open(", "..", "/etc/", "/proc/",
    # Permissions
    "chmod", "setuid", "sudo", "root",
]


def diff_is_security_sensitive(diff: str) -> bool:
    if not diff:
        return False
    lower = diff.lower()
    return any(kw in lower for kw in _SECURITY_KEYWORDS)


def run_cso(
    client: LLMClient,
    plan: LockedPlan,
    execution_summary: str,
    diff: str,
    test_output: str = "",
    model: str | None = None,
) -> tuple[bool, AgentResult]:
    """Run the CSO security review. Returns (secure, result).

    secure=True means no CRITICAL/HIGH findings at confidence >= 7.
    """
    system = load_prompt("loop/cso")
    parts = [
        "## Changes to Review",
        f"```diff\n{diff[:4000]}\n```",
        "\n## Execution summary",
        execution_summary[:1500],
    ]
    if test_output:
        parts.append(f"\n## Test output (tail)\n{test_output[-800:]}")
    parts.append(
        "\nReview for security vulnerabilities using OWASP Top 10 + STRIDE. "
        "Report only findings with confidence ≥ 7/10. Output SECURE or VULNERABLE."
    )

    registry = ToolRegistry()
    result = run_agent(
        client=client,
        system=system,
        user_message="\n".join(parts),
        registry=registry,
        model=model,
        thinking=True,  # extended thinking — security reasoning
    )

    secure = _parse_cso_verdict(result.final_text)
    return secure, result


def _parse_cso_verdict(text: str) -> bool:
    upper = text.upper()
    if "VERDICT: SECURE" in upper or "**SECURE**" in upper:
        return True
    if "VERDICT: VULNERABLE" in upper or "**VULNERABLE**" in upper:
        return False
    # Fallback heuristic: count CRITICAL/HIGH findings
    crit_count = len(re.findall(r"CRITICAL", upper))
    high_count = len(re.findall(r"HIGH", upper))
    # Tolerate 1-2 mentions (could be references, not findings)
    return (crit_count + high_count) < 2
