from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvidenceRecord:
    item: str                # Checklist item or behavior
    command: str             # e.g. "pytest tests/test_calc.py::test_add -v"
    exit_code: int
    stdout_tail: str         # last ~30 lines of stdout
    stderr_tail: str
    passed: bool             # exit_code == 0
    matched_item: bool = False  # Did output mention the item's keywords?


@dataclass
class VerificationReport:
    """Deterministic evidence bundle. Feeds Reviewer; no LLM involved in producing it."""
    evidence: list[EvidenceRecord] = field(default_factory=list)
    full_suite_passed: bool = False
    full_suite_cmd: str = ""
    full_suite_exit: int = -1
    full_suite_tail: str = ""

    @property
    def all_items_have_evidence(self) -> bool:
        return all(e.matched_item and e.passed for e in self.evidence)

    def summary(self) -> str:
        lines = [f"## Verification Report"]
        lines.append(f"Full suite: exit={self.full_suite_exit} — {'PASS' if self.full_suite_passed else 'FAIL'}")
        lines.append(f"Items verified: {sum(1 for e in self.evidence if e.passed)}/{len(self.evidence)}")
        for e in self.evidence:
            status = "✓" if (e.passed and e.matched_item) else "✗"
            lines.append(f"- [{status}] {e.item}")
            lines.append(f"    cmd: {e.command}")
            lines.append(f"    exit: {e.exit_code}")
        return "\n".join(lines)


def run_pytest(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(cwd), timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"


def detect_test_runner(project_root: Path) -> tuple[str, list[str]]:
    """Detect the project's test runner. Returns (name, command_args).

    Precedence:
    1. package.json with test script → npm test
    2. vitest.config.* → vitest run
    3. jest.config.* → jest
    4. go.mod → go test ./...
    5. Cargo.toml → cargo test
    6. default → pytest
    """
    if (project_root / "package.json").exists():
        try:
            pkg = __import__("json").loads((project_root / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                return "npm test", ["npm", "test"]
        except Exception:
            pass

    if any((project_root / n).exists() for n in (
        "vitest.config.js", "vitest.config.ts", "vitest.config.mjs"
    )):
        return "vitest", ["npx", "vitest", "run"]

    if any((project_root / n).exists() for n in (
        "jest.config.js", "jest.config.ts", "jest.config.cjs", "jest.config.mjs"
    )):
        return "jest", ["npx", "jest"]

    if (project_root / "go.mod").exists():
        return "go test", ["go", "test", "./..."]

    if (project_root / "Cargo.toml").exists():
        return "cargo test", ["cargo", "test"]

    # Default: pytest
    return "pytest", ["pytest", "-v"]


def _tail(text: str, lines: int = 30) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:]) if parts else ""


def _keywords_from_item(item: str) -> list[str]:
    # Tokenize a checklist line into keywords (alphanumeric, len >= 3)
    return [w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", item) if len(w) >= 3]


def verify_checklist(
    checklist: list[str],
    project_root: Path,
    pytest_bin: str = "pytest",
    per_item_pattern: str | None = None,
    timeout: int = 120,
    auto_detect: bool = True,
) -> VerificationReport:
    """Run the project's test suite and collect evidence for each checklist item.

    auto_detect: if True (default), uses detect_test_runner() to pick the right
    command (npm test / vitest / jest / go test / cargo test / pytest). This makes
    agentboard_verify work across languages. Pass auto_detect=False and pytest_bin
    explicitly to force a specific runner.
    """
    report = VerificationReport()

    # Decide command
    if auto_detect and pytest_bin == "pytest":
        runner_name, full_cmd = detect_test_runner(project_root)
    else:
        full_cmd = [pytest_bin, "-v"]
        runner_name = pytest_bin

    # Full suite first — this is the ground truth
    exit_code, out, err = run_pytest(full_cmd, project_root, timeout)
    report.full_suite_cmd = " ".join(full_cmd)
    report.full_suite_exit = exit_code
    report.full_suite_passed = (exit_code == 0)
    report.full_suite_tail = _tail(out + "\n" + err, 40)

    combined = out + "\n" + err

    for item in checklist:
        keywords = _keywords_from_item(item)
        # Require at least one keyword present in passing test output
        matched = any(kw in combined.lower() for kw in keywords) if keywords else False
        # Check that no failure line mentions this item's keywords
        failed_lines = [ln for ln in combined.splitlines() if " FAILED " in ln or ln.endswith("FAILED")]
        failed_for_item = any(
            any(kw in ln.lower() for kw in keywords) for ln in failed_lines
        )
        passed = report.full_suite_passed and not failed_for_item

        report.evidence.append(EvidenceRecord(
            item=item,
            command=report.full_suite_cmd,
            exit_code=exit_code,
            stdout_tail=_tail(out, 20),
            stderr_tail=_tail(err, 10),
            passed=passed,
            matched_item=matched,
        ))

    return report
