from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agentboard.agents.cso import diff_is_security_sensitive, run_cso
from agentboard.agents.executor import run_executor
from agentboard.agents.iron_law import check_iron_law
from agentboard.agents.planner import run_planner
from agentboard.agents.redteam import run_redteam
from agentboard.agents.reflect import run_reflect
from agentboard.agents.reviewer import ReviewVerdict, run_reviewer
from agentboard.agents.router import route
from agentboard.agents.systematic_debug import run_systematic_debug
from agentboard.agents.tdd import (
    parse_green_status, parse_red_status, parse_refactor_status,
    run_tdd_green, run_tdd_red, run_tdd_refactor,
)
from agentboard.config import AgentBoardConfig
from agentboard.llm.client import BudgetTracker, LLMClient
from agentboard.models import AtomicStep, DecisionEntry, LockedPlan
from agentboard.orchestrator.checkpointer import Checkpointer
from agentboard.orchestrator.interrupt import HintQueue
from agentboard.orchestrator.state import IterationRecord
from agentboard.orchestrator.verify import verify_checklist
from agentboard.storage.file_store import FileStore


class GraphState(TypedDict):
    # Immutable context
    goal_id: str
    task_id: str
    goal_description: str
    project_root: str
    max_iterations: int
    # Mutable loop state
    iteration: int
    plan_text: str
    execution_summary: str
    test_output: str
    diff: str
    prev_diff: str
    verdict: str
    reviewer_feedback: str
    redteam_feedback: str
    reflect_json: dict
    converged: bool
    blocked: bool
    block_reason: str
    tokens_used: int
    cost_usd: float
    history: list[dict]
    pending_hints: list[str]
    # Phase G — TDD state
    current_step_id: str           # active atomic_step.id during TDD cycle
    red_summary: str
    green_summary: str
    refactor_summary: str
    tdd_status: str                # RED_CONFIRMED|GREEN_CONFIRMED|... last TDD phase outcome
    verification_report: str       # serialized VerificationReport summary
    consecutive_failures: int      # track same-symptom retries for RCA escalation
    # Phase H — CSO state
    cso_feedback: str


def build_graph(
    locked_plan: LockedPlan,
    store: FileStore,
    budget: BudgetTracker,
    checkpointer: Checkpointer,
    client: LLMClient,
    config: AgentBoardConfig,
    console: Any,
    hint_queue: HintQueue | None = None,
    enable_redteam: bool = True,
    enable_cso: bool = True,
) -> StateGraph:
    cfg = config
    tdd_enabled = cfg.tdd.enabled and bool(locked_plan.atomic_steps)

    def _route(role: str) -> str:
        return route(role, cfg.llm, budget)

    def _current_step() -> AtomicStep | None:
        return locked_plan.next_step()

    def plan_node(state: GraphState) -> GraphState:
        i = state["iteration"]

        # ── HITL: drain pending hints ──────────────────────────────────────
        hints: list[str] = list(state.get("pending_hints", []))
        if hint_queue is not None:
            for h in hint_queue.drain():
                hints.append(h.text)
                store.append_decision(state["task_id"], DecisionEntry(
                    iter=i, phase="plan", reasoning="",
                    next_strategy=h.text, verdict_source="user_hint",
                    user_hint=h.text,
                ))

        # ── Pause check ────────────────────────────────────────────────────
        if hint_queue is not None:
            hint_queue.wait_if_paused()

        console.print(f"\n[bold cyan]── Iteration {i}/{state['max_iterations']} ──[/bold cyan]")
        if hints:
            console.print(f"  [yellow]Hints injected: {len(hints)}[/yellow]")
        console.print("  [dim]Planning...[/dim]")

        prev_verdict = state["verdict"] if i > 1 else ""
        prev_strategy = state["reflect_json"].get("next_strategy", "") if state["reflect_json"] else ""
        if hints:
            prev_strategy = "\n\n**User hints:**\n" + "\n".join(f"- {h}" for h in hints) + "\n\n" + prev_strategy

        result = run_planner(
            client=client,
            plan=locked_plan,
            iteration=i,
            previous_verdict=prev_verdict,
            previous_strategy=prev_strategy,
            model=_route("planner"),
        )
        if result.completion:
            budget.record(result.completion, f"plan_{i}")

        console.print(f"  [green]✓ Plan[/green] ({result.iterations} LLM rounds)")
        new_state = {**state, "plan_text": result.final_text, "pending_hints": []}
        checkpointer.save("plan_complete", new_state)
        return new_state

    def execute_node(state: GraphState) -> GraphState:
        """Legacy / non-TDD path: single-shot code + test in one executor call."""
        i = state["iteration"]
        console.print("  [dim]Executing...[/dim]")
        task_forbids = list(locked_plan.out_of_scope_guard)

        result = run_executor(
            client=client,
            plan=locked_plan,
            iteration_plan=state["plan_text"],
            project_root=Path(state["project_root"]),
            model=_route("executor"),
            shell_allowlist=cfg.tools.shell_allowlist,
            shell_timeout=cfg.tools.shell_timeout,
            forbids=task_forbids,
        )
        if result.completion:
            budget.record(result.completion, f"exec_{i}")

        test_output = _extract_test_output(result.tool_calls)
        diff = _get_diff(Path(state["project_root"]))
        store.save_iter_diff(state["task_id"], i, diff)

        # ── Iron Law check (G7) ────────────────────────────────────────────
        iron = check_iron_law(result.tool_calls)
        iron_violation = ""
        if iron.violated:
            iron_violation = iron.reason
            console.print(f"  [bold red]⚠ TDD Iron Law violated:[/bold red] {iron.reason}")
            store.append_decision(state["task_id"], DecisionEntry(
                iter=i, phase="iron_law",
                reasoning=iron.reason,
                next_strategy="write tests BEFORE production code next iteration",
                verdict_source="iron_law",
            ))

        console.print(f"  [green]✓ Execute[/green] ({len(result.tool_calls)} tool calls)")
        new_state = {
            **state,
            "execution_summary": result.final_text + (f"\n\n⚠ IRON LAW VIOLATED: {iron_violation}" if iron_violation else ""),
            "test_output": test_output,
            "diff": diff,
        }
        if iron.violated and cfg.tdd.strict:
            new_state["blocked"] = True
            new_state["block_reason"] = f"TDD Iron Law violated (strict mode): {iron.reason}"
        checkpointer.save("execute_complete", new_state)
        return new_state

    # ── Phase G: TDD Red-Green-Refactor nodes ─────────────────────────────────

    def tdd_red_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        step = _current_step()
        if step is None:
            console.print("  [dim]No atomic steps left — TDD cycle complete.[/dim]")
            return {**state, "tdd_status": "ALL_DONE", "current_step_id": ""}

        console.print(f"  [red]RED[/red] step={step.id} — {step.behavior[:60]}")
        result = run_tdd_red(
            client=client, plan=locked_plan, step=step,
            project_root=Path(state["project_root"]),
            model=_route("executor"),
            shell_allowlist=cfg.tools.shell_allowlist,
            shell_timeout=cfg.tools.shell_timeout,
        )
        if result.completion:
            budget.record(result.completion, f"red_{i}_{step.id}")

        status = parse_red_status(result.final_text)
        store.append_decision(state["task_id"], DecisionEntry(
            iter=i, phase="tdd_red",
            reasoning=result.final_text[:500],
            next_strategy="", verdict_source=status,
        ))
        console.print(f"    → [bold]{status}[/bold]")
        new_state = {
            **state,
            "current_step_id": step.id,
            "red_summary": result.final_text,
            "tdd_status": status,
        }
        checkpointer.save("tdd_red_complete", new_state)
        return new_state

    def tdd_green_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        step = next((s for s in locked_plan.atomic_steps if s.id == state["current_step_id"]), None)
        if step is None:
            return {**state, "tdd_status": "NO_STEP"}

        console.print(f"  [green]GREEN[/green] step={step.id}")
        result = run_tdd_green(
            client=client, plan=locked_plan, step=step,
            red_summary=state["red_summary"],
            project_root=Path(state["project_root"]),
            model=_route("executor"),
            shell_allowlist=cfg.tools.shell_allowlist,
            shell_timeout=cfg.tools.shell_timeout,
        )
        if result.completion:
            budget.record(result.completion, f"green_{i}_{step.id}")

        status = parse_green_status(result.final_text)
        store.append_decision(state["task_id"], DecisionEntry(
            iter=i, phase="tdd_green",
            reasoning=result.final_text[:500],
            next_strategy="", verdict_source=status,
        ))
        console.print(f"    → [bold]{status}[/bold]")

        if status == "GREEN_CONFIRMED":
            locked_plan.mark_step_completed(step.id)

        new_state = {
            **state,
            "green_summary": result.final_text,
            "tdd_status": status,
            "execution_summary": f"[RED]\n{state['red_summary']}\n\n[GREEN]\n{result.final_text}",
            "test_output": _extract_test_output(result.tool_calls),
            "diff": _get_diff(Path(state["project_root"])),
        }
        store.save_iter_diff(state["task_id"], i, new_state["diff"])
        checkpointer.save("tdd_green_complete", new_state)
        return new_state

    def tdd_refactor_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        step = next((s for s in locked_plan.atomic_steps if s.id == state["current_step_id"]), None)
        if step is None:
            return {**state, "tdd_status": "NO_STEP"}

        console.print(f"  [cyan]REFACTOR[/cyan] step={step.id}")
        result = run_tdd_refactor(
            client=client, plan=locked_plan, step=step,
            green_summary=state["green_summary"],
            project_root=Path(state["project_root"]),
            model=_route("executor"),
            shell_allowlist=cfg.tools.shell_allowlist,
            shell_timeout=cfg.tools.shell_timeout,
            allow_skip=cfg.tdd.allow_refactor_skip,
        )
        if result.completion:
            budget.record(result.completion, f"refactor_{i}_{step.id}")

        status = parse_refactor_status(result.final_text)
        store.append_decision(state["task_id"], DecisionEntry(
            iter=i, phase="tdd_refactor",
            reasoning=result.final_text[:500],
            next_strategy="", verdict_source=status,
        ))
        console.print(f"    → [bold]{status}[/bold]")

        new_state = {
            **state,
            "refactor_summary": result.final_text,
            "tdd_status": status,
        }
        checkpointer.save("tdd_refactor_complete", new_state)
        return new_state

    def verify_node(state: GraphState) -> GraphState:
        """Deterministic evidence gate — no LLM."""
        console.print("  [dim]Verifying (fresh evidence)...[/dim]")
        report = verify_checklist(
            checklist=locked_plan.goal_checklist,
            project_root=Path(state["project_root"]),
            pytest_bin="pytest",
            timeout=120,
        )
        console.print(
            f"  [green]✓ Verify[/green] suite={'PASS' if report.full_suite_passed else 'FAIL'}  "
            f"items={sum(1 for e in report.evidence if e.passed)}/{len(report.evidence)}"
        )
        summary = report.summary()
        return {
            **state,
            "verification_report": summary,
            "test_output": report.full_suite_tail or state.get("test_output", ""),
        }

    def review_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        console.print("  [dim]Reviewing...[/dim]")

        verdict, result = run_reviewer(
            client=client,
            plan=locked_plan,
            execution_summary=state["execution_summary"],
            test_output=state["test_output"],
            diff=state["diff"],
            model=_route("reviewer"),
        )
        if result.completion:
            budget.record(result.completion, f"review_{i}")

        store.append_decision(state["task_id"], DecisionEntry(
            iter=i, phase="review",
            reasoning=result.final_text[:500],
            next_strategy="",
            verdict_source="reviewer",
        ))

        console.print(f"  [bold]Reviewer: {_verdict_color(verdict)}[/bold]")
        new_state = {
            **state,
            "verdict": verdict.value,
            "reviewer_feedback": result.final_text,
            "redteam_feedback": "",
        }
        checkpointer.save("review_complete", new_state)
        return new_state

    def redteam_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        console.print("  [dim]Red-team attack...[/dim]")

        survived, result = run_redteam(
            client=client,
            plan=locked_plan,
            execution_summary=state["execution_summary"],
            test_output=state["test_output"],
            diff=state["diff"],
            model=_route("redteam"),
        )
        if result.completion:
            budget.record(result.completion, f"redteam_{i}")

        verdict_str = "PASS" if survived else "RETRY"
        console.print(f"  [bold]Red-team: {'[green]SURVIVED[/green]' if survived else '[red]BROKEN[/red]'}[/bold]")

        store.append_decision(state["task_id"], DecisionEntry(
            iter=i, phase="redteam",
            reasoning=result.final_text[:500],
            next_strategy="" if survived else result.final_text[:300],
            verdict_source="redteam",
        ))

        if not survived:
            # Override verdict back to RETRY with redteam feedback
            return {
                **state,
                "verdict": ReviewVerdict.retry.value,
                "redteam_feedback": result.final_text,
                "reviewer_feedback": state["reviewer_feedback"] + "\n\n[Red-team] " + result.final_text[:300],
            }
        return {**state, "redteam_feedback": result.final_text}

    def reflect_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        console.print("  [dim]Reflecting (systematic RCA)...[/dim]" if cfg.tdd.systematic_debug else "  [dim]Reflecting...[/dim]")

        history_lines = [
            f"Iter {rec['n']}: verdict={rec.get('verdict','?')}"
            for rec in state["history"]
        ]

        if cfg.tdd.systematic_debug:
            reflect_json, result = run_systematic_debug(
                client=client,
                reviewer_feedback=state["reviewer_feedback"],
                execution_summary=state["execution_summary"],
                test_output=state["test_output"],
                iteration=i,
                history_summary="\n".join(history_lines),
                consecutive_failures=state.get("consecutive_failures", 1),
                model=_route("reflect"),
            )
        else:
            reflect_json, result = run_reflect(
                client=client,
                reviewer_feedback=state["reviewer_feedback"],
                execution_summary=state["execution_summary"],
                iteration=i,
                history_summary="\n".join(history_lines),
                model=_route("reflect"),
            )
        if result.completion:
            budget.record(result.completion, f"reflect_{i}")

        store.append_decision(state["task_id"], DecisionEntry(
            iter=i, phase="reflect",
            reasoning=reflect_json.get("root_cause", ""),
            next_strategy=reflect_json.get("next_strategy", ""),
            verdict_source="reflect",
        ))

        # Auto-promote high-risk learning
        if reflect_json.get("risk") == "HIGH" and reflect_json.get("learning"):
            _auto_promote_learning(store, state["task_id"], i, reflect_json["learning"])

        # Track consecutive failures for RCA escalation
        consec = state.get("consecutive_failures", 0) + 1

        new_state = {
            **state,
            "reflect_json": reflect_json,
            "iteration": i + 1,
            "consecutive_failures": consec,
        }

        # Escalate after 3 same-symptom failures
        if reflect_json.get("escalate") or consec >= 3:
            new_state["blocked"] = True
            new_state["block_reason"] = (
                f"Systematic debug escalates: {consec} consecutive failures on same symptom — "
                f"architecture may need rework. Run `agentboard rethink {state['goal_id']}`."
            )
            console.print(f"  [bold red]ESCALATE[/bold red]: {consec} consecutive failures")

        checkpointer.save("reflect_complete", new_state)
        return new_state

    def commit_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        verdict = state["verdict"]

        rec = IterationRecord(
            n=i,
            plan_text=state["plan_text"],
            execution_summary=state["execution_summary"],
            test_output=state["test_output"],
            diff=state["diff"],
            verdict=verdict,
            reviewer_feedback=state["reviewer_feedback"],
            reflect_json=state["reflect_json"],
        )
        history = list(state["history"]) + [vars(rec)]
        _local_commit(Path(state["project_root"]), state["task_id"], i, verdict)

        is_pass = verdict == ReviewVerdict.pass_.value
        new_state = {
            **state,
            "history": history,
            "prev_diff": state["diff"],
            "converged": is_pass,
        }
        checkpointer.save("iteration_complete", new_state)

        if is_pass:
            final = {**new_state, "tokens_used": budget.tokens_used, "cost_usd": budget.cost_usd}
            checkpointer.save("converged", final)
            console.print(
                f"\n[bold green]✓ Converged at iteration {i}[/bold green]  "
                f"[dim]{budget.tokens_used:,} tokens | ${budget.cost_usd:.4f}[/dim]"
            )
        return new_state

    # ── Routing ───────────────────────────────────────────────────────────────

    def cso_node(state: GraphState) -> GraphState:
        i = state["iteration"]
        console.print("  [dim]CSO (security review)...[/dim]")

        secure, result = run_cso(
            client=client,
            plan=locked_plan,
            execution_summary=state["execution_summary"],
            diff=state["diff"],
            test_output=state["test_output"],
            model=_route("reviewer"),
        )
        if result.completion:
            budget.record(result.completion, f"cso_{i}")

        verdict_label = "SECURE" if secure else "VULNERABLE"
        console.print(f"  [bold]CSO: {'[green]SECURE[/green]' if secure else '[red]VULNERABLE[/red]'}[/bold]")

        store.append_decision(state["task_id"], DecisionEntry(
            iter=i, phase="cso",
            reasoning=result.final_text[:500],
            next_strategy="" if secure else result.final_text[:300],
            verdict_source=verdict_label,
        ))

        new_state = {**state, "cso_feedback": result.final_text}
        if not secure:
            # Downgrade reviewer's PASS — security findings require a fix
            new_state["verdict"] = ReviewVerdict.retry.value
            new_state["reviewer_feedback"] = (
                state["reviewer_feedback"] + "\n\n[CSO] " + result.final_text[:400]
            )
        checkpointer.save("cso_complete", new_state)
        return new_state

    def _should_cso(state: GraphState) -> bool:
        return (
            enable_cso
            and not budget.over_budget
            and diff_is_security_sensitive(state.get("diff", ""))
        )

    def route_after_review(state: GraphState) -> Literal["cso", "redteam", "reflect", "commit", "blocked"]:
        verdict = state["verdict"]
        i = state["iteration"]

        if verdict == ReviewVerdict.pass_.value:
            # PASS → CSO (if diff is security-sensitive) → redteam → commit
            if _should_cso(state):
                return "cso"
            return "redteam" if enable_redteam and not budget.over_budget else "commit"
        if verdict == ReviewVerdict.replan.value:
            return "blocked"
        if i >= state["max_iterations"] or budget.over_budget:
            return "blocked"
        return "reflect"

    def route_after_cso(state: GraphState) -> Literal["redteam", "commit", "reflect", "blocked"]:
        verdict = state["verdict"]
        i = state["iteration"]
        if verdict == ReviewVerdict.pass_.value:
            return "redteam" if enable_redteam and not budget.over_budget else "commit"
        # CSO downgraded to RETRY
        if i >= state["max_iterations"] or budget.over_budget:
            return "blocked"
        return "reflect"

    def route_after_redteam(state: GraphState) -> Literal["commit", "reflect", "blocked"]:
        verdict = state["verdict"]
        i = state["iteration"]
        if verdict == ReviewVerdict.pass_.value:
            return "commit"
        if i >= state["max_iterations"] or budget.over_budget:
            return "blocked"
        return "reflect"

    def route_after_commit(state: GraphState) -> Literal["plan", "__end__"]:
        return "__end__" if state["converged"] else "plan"

    def blocked_node(state: GraphState) -> GraphState:
        verdict = state["verdict"]
        i = state["iteration"]
        # Preserve an existing block_reason (Iron Law strict halt, RCA escalation, etc.)
        existing = state.get("block_reason", "")
        if existing:
            reason = existing
        elif verdict == ReviewVerdict.replan.value:
            reason = f"REPLAN at iteration {i}"
        elif budget.over_budget:
            reason = f"Token budget exhausted ({budget.tokens_used:,}/{budget.token_ceiling:,})"
        else:
            reason = f"Max iterations ({state['max_iterations']}) reached"

        new_state = {
            **state,
            "blocked": True,
            "block_reason": reason,
            "tokens_used": budget.tokens_used,
            "cost_usd": budget.cost_usd,
        }
        checkpointer.save("blocked", new_state)
        console.print(f"\n[bold red]✗ Loop blocked:[/bold red] {reason}")
        return new_state

    # ── Additional routing for TDD path ──────────────────────────────────────

    def route_after_red(state: GraphState) -> Literal["green", "reflect", "blocked"]:
        status = state.get("tdd_status", "")
        if status == "RED_CONFIRMED":
            return "green"
        if status == "ALL_DONE":
            # No more atomic steps — fall through to review for final verification
            return "reflect" if False else "green"  # defer to verify/review via green
        if state["iteration"] >= state["max_iterations"] or budget.over_budget:
            return "blocked"
        return "reflect"

    def route_after_green(state: GraphState) -> Literal["refactor", "verify", "reflect", "blocked"]:
        status = state.get("tdd_status", "")
        if status == "GREEN_CONFIRMED":
            return "refactor" if cfg.tdd.enabled and not cfg.tdd.allow_refactor_skip is False else "refactor"
        if state["iteration"] >= state["max_iterations"] or budget.over_budget:
            return "blocked"
        return "reflect"

    def route_after_refactor(state: GraphState) -> Literal["verify", "blocked"]:
        status = state.get("tdd_status", "")
        if status == "REGRESSED":
            # Regressions in refactor = critical
            if state["iteration"] >= state["max_iterations"] or budget.over_budget:
                return "blocked"
        return "verify"

    def route_after_verify(state: GraphState) -> Literal["tdd_red", "review"]:
        # If more atomic steps remain and suite is green, do another RED cycle
        next_step = locked_plan.next_step()
        if next_step is not None and "PASS" in state.get("verification_report", ""):
            return "tdd_red"
        return "review"

    # ── Build graph ───────────────────────────────────────────────────────────

    g = StateGraph(GraphState)
    g.add_node("plan", plan_node)
    g.add_node("execute", execute_node)
    g.add_node("tdd_red", tdd_red_node)
    g.add_node("tdd_green", tdd_green_node)
    g.add_node("tdd_refactor", tdd_refactor_node)
    g.add_node("verify", verify_node)
    g.add_node("review", review_node)
    g.add_node("cso", cso_node)
    g.add_node("redteam", redteam_node)
    g.add_node("reflect", reflect_node)
    g.add_node("commit", commit_node)
    g.add_node("blocked", blocked_node)

    g.set_entry_point("plan")

    if tdd_enabled:
        # Plan → RED → GREEN → REFACTOR → VERIFY → (back to RED | review)
        g.add_edge("plan", "tdd_red")
        g.add_conditional_edges("tdd_red", route_after_red, {
            "green": "tdd_green", "reflect": "reflect", "blocked": "blocked",
        })
        g.add_conditional_edges("tdd_green", route_after_green, {
            "refactor": "tdd_refactor", "verify": "verify",
            "reflect": "reflect", "blocked": "blocked",
        })
        g.add_conditional_edges("tdd_refactor", route_after_refactor, {
            "verify": "verify", "blocked": "blocked",
        })
        g.add_conditional_edges("verify", route_after_verify, {
            "tdd_red": "tdd_red", "review": "review",
        })
    else:
        # Legacy single-shot executor path
        def route_after_execute(state: GraphState) -> Literal["verify", "review", "blocked"]:
            if state.get("blocked"):  # Iron Law strict halt
                return "blocked"
            return "verify" if cfg.tdd.verify_with_evidence else "review"

        g.add_edge("plan", "execute")
        g.add_conditional_edges("execute", route_after_execute, {
            "verify": "verify", "review": "review", "blocked": "blocked",
        })
        g.add_edge("verify", "review")

    g.add_conditional_edges("review", route_after_review, {
        "cso": "cso",
        "redteam": "redteam",
        "commit": "commit",
        "reflect": "reflect",
        "blocked": "blocked",
    })
    g.add_conditional_edges("cso", route_after_cso, {
        "redteam": "redteam",
        "commit": "commit",
        "reflect": "reflect",
        "blocked": "blocked",
    })
    g.add_conditional_edges("redteam", route_after_redteam, {
        "commit": "commit",
        "reflect": "reflect",
        "blocked": "blocked",
    })
    def route_after_reflect(state: GraphState) -> Literal["plan", "blocked"]:
        return "blocked" if state.get("blocked") else "plan"

    g.add_conditional_edges("reflect", route_after_reflect, {
        "plan": "plan",
        "blocked": "blocked",
    })
    g.add_conditional_edges("commit", route_after_commit, {
        "plan": "plan",
        "__end__": END,
    })
    g.add_edge("blocked", END)
    return g


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_test_output(tool_calls) -> str:
    for tc in reversed(tool_calls):
        if tc.tool_name == "shell" and ("pytest" in str(tc.tool_input) or "test" in str(tc.tool_input)):
            return tc.result
    return ""


def _get_diff(project_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=str(project_root), timeout=10,
        )
        return result.stdout
    except Exception:
        return ""


def _local_commit(project_root: Path, task_id: str, iteration: int, verdict: str) -> None:
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(project_root), timeout=10, capture_output=True)
        msg = f"agentboard: task {task_id} iter {iteration} [{verdict}]"
        subprocess.run(["git", "commit", "-m", msg], cwd=str(project_root), timeout=15, capture_output=True)
    except Exception:
        pass


def _auto_promote_learning(store: FileStore, task_id: str, iteration: int, learning: str) -> None:
    try:
        from agentboard.memory.retriever import promote_learning
        name = f"auto_{task_id[:8]}_iter{iteration}"
        promote_learning(store, name, learning, auto=True)
    except Exception:
        pass


def _verdict_color(verdict: ReviewVerdict) -> str:
    colors = {
        ReviewVerdict.pass_: "[green]PASS[/green]",
        ReviewVerdict.retry: "[yellow]RETRY[/yellow]",
        ReviewVerdict.replan: "[red]REPLAN[/red]",
    }
    return colors.get(verdict, verdict.value)
