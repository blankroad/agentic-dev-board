"""End-to-end CLI test for `devboard export`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from devboard.cli import app


def test_cli_export_md_to_stdout(tmp_path: Path) -> None:
    """# guards: edge-case-red-rule
    edge: integration wiring — CLI must dispatch to the render() pipeline."""
    # Set up a plan.md fixture
    goal_dir = tmp_path / ".devboard" / "goals" / "g_cli"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("# Hello\n\n## Section\n\nbody\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["export", "g_cli", "--format", "md", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "# Hello" in result.stdout
    assert "## Section" in result.stdout


def test_cli_export_confluence_to_file(tmp_path: Path) -> None:
    goal_dir = tmp_path / ".devboard" / "goals" / "g_cli2"
    goal_dir.mkdir(parents=True)
    (goal_dir / "plan.md").write_text("## Outcome\n\nbody\n")

    out_file = tmp_path / "out.txt"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "export", "g_cli2",
            "--format", "confluence",
            "--output", str(out_file),
            "--project-root", str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_file.exists()
    assert "h2. Outcome" in out_file.read_text()


def test_cli_export_unknown_goal_exits_nonzero(tmp_path: Path) -> None:
    (tmp_path / ".devboard" / "goals").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(
        app, ["export", "g_missing", "--project-root", str(tmp_path)]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Report source (s_005/s_006/s_007) — new path:
#   `devboard export <gid> --source report` reads report.md verbatim
#   (no format rendering; the file is already Markdown).
# Keeps the legacy plan.md export above unchanged.
# ---------------------------------------------------------------------------


def _bootstrap_with_report(tmp_path: Path, body: str, goal_id: str = "g_rep") -> None:
    gdir = tmp_path / ".devboard" / "goals" / goal_id
    gdir.mkdir(parents=True)
    (gdir / "plan.md").write_text("# plan\n")
    (gdir / "report.md").write_text(body, encoding="utf-8")


def test_export_stdout_prints_report_md(tmp_path: Path) -> None:
    """s_005 — `devboard export <gid> --source report` must emit report.md
    verbatim to stdout (no markdown → X renderer; report is already MD)."""
    _bootstrap_with_report(tmp_path, "SENTINEL_REPORT_S005\n\n본문.\n")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["export", "g_rep", "--source", "report", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, (
        f"expected exit 0; got {result.exit_code}. stdout={result.stdout!r}"
    )
    assert "SENTINEL_REPORT_S005" in result.stdout, (
        f"stdout must include report.md body verbatim; got {result.stdout!r}"
    )


def test_export_out_writes_to_path(tmp_path: Path) -> None:
    """s_006 — `--source report --output <path>` must write report.md to
    the destination file unchanged."""
    body = "SENTINEL_REPORT_S006\n\n내용.\n"
    _bootstrap_with_report(tmp_path, body)
    out_file = tmp_path / "out" / "report-copy.md"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "export", "g_rep",
            "--source", "report",
            "--output", str(out_file),
            "--project-root", str(tmp_path),
        ],
    )
    assert result.exit_code == 0, (
        f"expected exit 0; got {result.exit_code}. stdout={result.stdout!r}"
    )
    assert out_file.exists(), f"output file not written at {out_file}"
    assert out_file.read_text(encoding="utf-8") == body, (
        f"output file must match report.md verbatim; got {out_file.read_text()!r}"
    )


def test_synthesize_report_skill_md_present_and_complete() -> None:
    """s_008 — the agentboard-synthesize-report SKILL.md file must exist
    and contain the core contract: Agent tool invocation, report.md save
    path, and sanity check keywords."""
    repo = Path(__file__).resolve().parent.parent
    skill = repo / "skills" / "agentboard-synthesize-report" / "SKILL.md"
    assert skill.exists(), (
        f"synthesize-report skill missing at {skill.relative_to(repo)}"
    )
    text = skill.read_text(encoding="utf-8")
    must_contain = [
        "Agent",            # dispatches Claude Code Agent tool
        "report.md",        # names the output file
        "plan.md",          # reads plan artifact
        "challenge.md",     # reads challenge artifact
        "decisions.jsonl",  # reads decisions artifact
    ]
    missing = [k for k in must_contain if k not in text]
    assert not missing, (
        f"synthesize-report SKILL.md missing required keywords: {missing}"
    )


def test_approval_skill_has_synthesize_report_hook() -> None:
    """s_009 — the agentboard-approval skill must reference the
    synthesize-report skill near Step 4.5 so that report.md generation
    auto-triggers after a push."""
    repo = Path(__file__).resolve().parent.parent
    approval = repo / "skills" / "agentboard-approval" / "SKILL.md"
    assert approval.exists(), f"approval skill missing at {approval}"
    text = approval.read_text(encoding="utf-8")
    assert "agentboard-synthesize-report" in text, (
        "approval skill must reference `agentboard-synthesize-report` as an "
        "automatic post-push hook (try/except around it per Step 4.5)."
    )


def test_out_of_scope_files_untouched() -> None:
    """s_010 — LockedPlan out_of_scope_guard enforcement for this goal
    (g_20260421_013203_33d3ef). These files must not have been modified by
    this goal's changes (git diff vs main empty)."""
    import subprocess
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parent.parent
    guarded = [
        "src/devboard/tui/dev_timeline_render.py",
        "src/devboard/tui/result_timeline_render.py",
        "src/devboard/tui/review_sections_render.py",
        "src/devboard/narrative/generator.py",
        "src/devboard/models.py",
        "src/devboard/storage/file_store.py",
        "src/devboard/tui/app.py",
        "src/devboard/tui/phase_flow.py",
        "src/devboard/tui/status_bar.py",
        "src/devboard/tui/plan_markdown.py",
        "src/devboard/mcp_server.py",
    ]
    offenders: list[str] = []
    for base in ("main", "origin/main"):
        proc = subprocess.run(
            ["git", "-C", str(repo), "diff", base, "--", *guarded],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            if proc.stdout:
                for line in proc.stdout.splitlines():
                    if line.startswith("diff --git a/"):
                        offenders.append(line.split()[2].removeprefix("a/"))
            break
    else:
        import pytest as _pytest
        _pytest.skip("no main/origin/main baseline available")
    assert not offenders, (
        f"guarded files modified (scope_guard violation): {offenders}"
    )


def test_export_rejects_goal_id_with_path_traversal(tmp_path: Path) -> None:
    """redteam FM#1 — goal_id must be validated before being joined into
    the path. Reject anything that doesn't match the standard goal id
    shape (`g_YYYYMMDD_HHMMSS_<hex6>`) so `--goal-id ../../etc/passwd`
    and friends can't read or write outside the .devboard tree."""
    (tmp_path / ".devboard" / "goals").mkdir(parents=True)
    runner = CliRunner()
    for evil in ("../../etc/passwd", "..", "/etc/hosts", "g_ok/../../etc"):
        result = runner.invoke(
            app,
            ["export", evil, "--source", "report", "--project-root", str(tmp_path)],
        )
        assert result.exit_code != 0, (
            f"evil goal_id={evil!r} must be rejected; got exit_code=0"
        )
        assert "invalid goal_id" in result.output.lower() or "invalid" in result.output.lower(), (
            f"output should flag invalid goal_id for {evil!r}; got: {result.output!r}"
        )


def test_export_rejects_output_path_outside_cwd(tmp_path: Path) -> None:
    """redteam FM#2 — `--output <path>` must stay within cwd/project_root.
    Absolute paths outside the project root or paths resolving above the
    project root must be refused so a shipping script cannot use
    `devboard export` as a write primitive."""
    import os

    _bootstrap_with_report(tmp_path, "body\n")
    runner = CliRunner()
    # Absolute outside-of-project target:
    target = tmp_path.parent / "outside-project-should-be-rejected.md"
    result = runner.invoke(
        app,
        [
            "export", "g_rep",
            "--source", "report",
            "--output", str(target),
            "--project-root", str(tmp_path),
        ],
    )
    assert result.exit_code != 0, (
        f"output outside project_root must be rejected; got exit_code=0"
    )
    assert not target.exists(), f"file must not be written outside project_root; found at {target}"


def test_export_missing_report_exits_with_error(tmp_path: Path) -> None:
    """s_007 — `--source report` when report.md is absent must exit non-zero
    with a user-friendly hint on stderr/stdout."""
    # Create goal dir with plan.md but NO report.md.
    gdir = tmp_path / ".devboard" / "goals" / "g_no_report"
    gdir.mkdir(parents=True)
    (gdir / "plan.md").write_text("# plan\n")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["export", "g_no_report", "--source", "report", "--project-root", str(tmp_path)],
    )
    assert result.exit_code != 0, (
        f"expected non-zero exit when report.md absent; got 0. output={result.output!r}"
    )
    # Guidance text should point the user at the synthesize skill.
    combined = result.output
    assert (
        "report.md" in combined and ("synthesize" in combined or "not found" in combined.lower())
    ), (
        f"output must mention report.md missing + suggest next step; "
        f"got {combined!r}"
    )
