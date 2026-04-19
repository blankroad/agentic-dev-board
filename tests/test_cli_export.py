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
