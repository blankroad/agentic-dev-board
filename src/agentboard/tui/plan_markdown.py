from __future__ import annotations

from pathlib import Path

from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from agentboard.tui.session_derive import SessionContext


_GAUNTLET_ORDER = ("frame", "scope", "arch", "challenge", "decide")


def _safe_read(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return fallback


class PlanMarkdown(Widget):
    """Center-top pane. Primary view = plan_summary.md (LLM-curated digest)
    if present, else plan.md. Below: a '▸ Raw Artifacts' collapsible that
    holds plan.md + frame/scope/arch/challenge/decide.md so the user can
    always verify the source."""

    DEFAULT_CSS = """
    PlanMarkdown { height: 1fr; padding: 0 1; overflow-y: auto; }
    """

    BINDINGS = [Binding("g", "toggle_raw", "Raw", show=False)]

    can_focus = True

    def __init__(self, session: SessionContext, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._session = session

    def compose(self) -> ComposeResult:
        primary, raw = self._load()
        yield Static(Markdown(primary), id="plan-body")
        with Collapsible(title="▸ Raw Artifacts", collapsed=True, id="raw-artifacts-collapsible"):
            yield Static(Markdown(raw), id="raw-artifacts-body")

    def action_toggle_raw(self) -> None:
        try:
            c = self.query_one("#raw-artifacts-collapsible", Collapsible)
        except Exception:
            return
        c.collapsed = not c.collapsed

    def refresh_content(self) -> None:
        """Re-read the active goal's files and push new content into the
        existing Static widgets. Invoked after `:goto` or other state
        mutations that change `session.active_goal_id`."""
        primary, raw = self._load()
        try:
            self.query_one("#plan-body", Static).update(Markdown(primary))
        except Exception:
            pass
        try:
            self.query_one("#raw-artifacts-body", Static).update(Markdown(raw))
        except Exception:
            pass

    def _load(self) -> tuple[str, str]:
        """Returns (primary_markdown, raw_markdown). Primary prefers
        plan_summary.md; raw is plan.md + all gauntlet files."""
        gid = self._session.active_goal_id
        if not gid:
            return (
                "_Plan not locked. Run `agentboard-gauntlet`._",
                "_No raw artifacts._",
            )
        goal_dir: Path = self._session.store_root / ".devboard" / "goals" / gid
        summary_file = goal_dir / "plan_summary.md"
        plan_file = goal_dir / "plan.md"

        # Primary view — summary if present, else raw plan
        if summary_file.exists():
            primary = _safe_read(summary_file, "_plan_summary.md unreadable._")
        elif plan_file.exists():
            primary = _safe_read(
                plan_file,
                "_plan.md unreadable (binary or permission denied)._",
            )
        else:
            primary = "_Plan not locked. Run `agentboard-gauntlet`._"

        # Raw artifacts — always plan.md + all 5 gauntlet files
        raw_parts: list[str] = []
        if plan_file.exists():
            raw_parts.append(f"## plan.md\n\n{_safe_read(plan_file, '_unreadable_')}")
        gdir = goal_dir / "gauntlet"
        if gdir.exists():
            for step in _GAUNTLET_ORDER:
                f = gdir / f"{step}.md"
                if f.exists():
                    raw_parts.append(f"## {step}.md\n\n{_safe_read(f, '_unreadable_')}")
        raw = "\n\n---\n\n".join(raw_parts) if raw_parts else "_No raw artifacts._"

        return primary, raw
