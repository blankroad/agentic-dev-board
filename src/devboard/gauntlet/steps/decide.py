from __future__ import annotations

from devboard.llm.client import LLMClient, CompletionResult, load_prompt
from devboard.gauntlet.lock import parse_decide_output


def run_decide(
    client: LLMClient,
    goal_description: str,
    frame_output: str,
    scope_output: str,
    arch_output: str,
    challenge_output: str,
) -> tuple[dict, CompletionResult]:
    """Synthesize all steps into a locked plan JSON dict."""
    system = load_prompt("gauntlet/decide")

    content = f"""## Original Goal
{goal_description}

## Step 1: Frame
{frame_output}

## Step 2: Scope
{scope_output}

## Step 3: Architecture
{arch_output}

## Step 4: Challenge
{challenge_output}

Synthesize into the locked plan JSON. Output ONLY the JSON object."""

    messages = [{"role": "user", "content": content}]

    result = client.complete(
        messages=messages,
        system=system,
        model=client._config.gauntlet_model.replace("opus", "sonnet").replace("4-7", "4-6"),
        thinking=False,
        max_tokens=4096,
    )

    plan_dict = parse_decide_output(result.text)
    return plan_dict, result
