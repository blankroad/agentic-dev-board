from __future__ import annotations

from devboard.llm.client import LLMClient, CompletionResult, load_prompt


def run_challenge(
    client: LLMClient,
    goal_description: str,
    frame_output: str,
    scope_output: str,
    arch_output: str,
) -> tuple[str, CompletionResult]:
    system = load_prompt("gauntlet/challenge")

    content = f"""## Goal
{goal_description}

## Frame
{frame_output}

## Scope
{scope_output}

## Architecture
{arch_output}

Find every way this plan will fail. Be specific and harsh."""

    messages = [{"role": "user", "content": content}]

    result = client.complete(
        messages=messages,
        system=system,
        model=client._config.gauntlet_model,
        thinking=False,
    )
    return result.text, result
