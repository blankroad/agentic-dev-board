from __future__ import annotations

from pathlib import Path

from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from devboard.tui.session_derive import SessionContext


_GAUNTLET_ORDER = ("frame", "scope", "arch", "challenge", "decide")


class PlanMarkdown(Widget):
    """Center-top pane. Renders active goal's plan.md as Rich Markdown and
    exposes gauntlet artifacts (frame/scope/arch/challenge/decide) behind
    a collapsed '▸ Gauntlet' section. 'g' toggles the collapsible."""

    DEFAULT_CSS = """
    PlanMarkdown { height: 1fr; padding: 0 1; overflow-y: auto; }
    """

    BINDINGS = [Binding("g", "toggle_gauntlet", "Gauntlet", show=False)]

    can_focus = True

    def __init__(self, session: SessionContext, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._session = session

    def compose(self) -> ComposeResult:
        plan_text, gauntlet_text = self._load()
        yield Static(Markdown(plan_text), id="plan-body")
        with Collapsible(title="▸ Gauntlet", collapsed=True, id="gauntlet-collapsible"):
            yield Static(Markdown(gauntlet_text), id="gauntlet-body")

    def action_toggle_gauntlet(self) -> None:
        c = self.query_one("#gauntlet-collapsible", Collapsible)
        c.collapsed = not c.collapsed

    def _load(self) -> tuple[str, str]:
        gid = self._session.active_goal_id
        if not gid:
            return ("_Plan not locked. Run `devboard-gauntlet`._", "_No gauntlet artifacts._")
        goal_dir: Path = self._session.store_root / ".devboard" / "goals" / gid
        plan_file = goal_dir / "plan.md"
        if plan_file.exists():
            try:
                plan = plan_file.read_text()
            except (OSError, UnicodeDecodeError):
                plan = "_plan.md unreadable (binary or permission denied)._"
        else:
            plan = "_Plan not locked. Run `devboard-gauntlet`._"
        gparts: list[str] = []
        gdir = goal_dir / "gauntlet"
        if gdir.exists():
            for step in _GAUNTLET_ORDER:
                f = gdir / f"{step}.md"
                if f.exists():
                    try:
                        gparts.append(f"## {step}.md\n\n{f.read_text()}")
                    except (OSError, UnicodeDecodeError):
                        continue
        gauntlet = "\n\n---\n\n".join(gparts) if gparts else "_No gauntlet artifacts._"
        return plan, gauntlet
