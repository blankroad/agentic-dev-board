from __future__ import annotations

from devboard.llm.client import LLMClient, CompletionResult, load_prompt


def run_scope(
    client: LLMClient,
    goal_description: str,
    frame_output: str,
) -> tuple[str, CompletionResult]:
    system = load_prompt("gauntlet/scope")

    content = f"""## Original Goal
{goal_description}

## Frame Analysis
{frame_output}

Review the scope. Pick the right mode and produce the refined goal statement."""

    messages = [{"role": "user", "content": content}]

    result = client.complete(
        messages=messages,
        system=system,
        model=client._config.gauntlet_model,
        thinking=True,
        thinking_budget=client._config.thinking_budget,
    )
    return result.text, result
