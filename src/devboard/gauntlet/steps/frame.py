from __future__ import annotations

from devboard.llm.client import LLMClient, CompletionResult, load_prompt


def run_frame(
    client: LLMClient,
    goal_description: str,
    learnings: str = "",
) -> tuple[str, CompletionResult]:
    system = load_prompt("gauntlet/frame")

    context_parts = [f"## Goal\n{goal_description}"]
    if learnings:
        context_parts.append(f"## Relevant Learnings\n{learnings}")

    messages = [{"role": "user", "content": "\n\n".join(context_parts)}]

    result = client.complete(
        messages=messages,
        system=system,
        model=client._config.gauntlet_model.replace("opus", "sonnet").replace("4-7", "4-6"),
        thinking=False,
    )
    return result.text, result
