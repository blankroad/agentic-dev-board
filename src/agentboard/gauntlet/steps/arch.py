from __future__ import annotations

from agentboard.llm.client import LLMClient, CompletionResult, load_prompt_with_prefix


def run_arch(
    client: LLMClient,
    goal_description: str,
    frame_output: str,
    scope_output: str,
) -> tuple[str, CompletionResult]:
    system = load_prompt_with_prefix("gauntlet/arch")

    content = f"""## Original Goal
{goal_description}

## Frame
{frame_output}

## Scope Decision
{scope_output}

Design the technical architecture. Be specific about files, types, and edge cases."""

    messages = [{"role": "user", "content": content}]

    result = client.complete(
        messages=messages,
        system=system,
        model=client._config.gauntlet_model,
        thinking=True,
        thinking_budget=client._config.thinking_budget,
    )
    return result.text, result
