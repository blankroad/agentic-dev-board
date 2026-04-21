from __future__ import annotations

import re

from agentboard.llm.client import CompletionResult, LLMClient, load_prompt


def needs_brainstorm(goal_description: str) -> bool:
    """Heuristic: ambiguous goal triggers Socratic clarification.

    Signals of ambiguity:
    - Very short (< 30 chars of meaningful content)
    - Contains vague words ("something like", "kinda", "maybe", "etc")
    - No concrete verbs
    """
    stripped = goal_description.strip()
    if len(stripped) < 30:
        return True
    vague = ["something like", "kinda", "maybe", "sort of", "i guess", " etc", "anything"]
    lower = stripped.lower()
    if any(v in lower for v in vague):
        return True
    return False


def run_brainstorm(
    client: LLMClient,
    goal_description: str,
    model: str | None = None,
) -> tuple[str, CompletionResult]:
    system = load_prompt("gauntlet/brainstorm")
    user = f"## Goal\n{goal_description}\n\nIs this goal statement clear, or do you need clarification?"
    model = model or "claude-sonnet-4-6"
    result = client.complete(
        messages=[{"role": "user", "content": user}],
        system=system,
        model=model,
        thinking=False,
    )
    return result.text, result


def parse_questions(text: str) -> list[str]:
    if "CLEAR" in text.upper() and "NO QUESTIONS" in text.upper():
        return []
    questions = []
    for line in text.splitlines():
        m = re.match(r"^\s*\d+\.\s+(?:\*\*[^*]+\*\*:\s*)?(.+?)\s*$", line)
        if m:
            q = m.group(1).strip()
            if q and "?" in q:
                questions.append(q)
    return questions
