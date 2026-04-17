from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devboard.llm.client import CompletionResult, LLMClient
from devboard.tools.base import ToolCall, ToolRegistry


@dataclass
class AgentResult:
    final_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    completion: CompletionResult | None = None
    iterations: int = 0


def run_agent(
    client: LLMClient,
    system: str,
    user_message: str,
    registry: ToolRegistry,
    model: str | None = None,
    thinking: bool = False,
    max_tool_rounds: int = 10,
) -> AgentResult:
    """Run an agentic loop: call LLM → execute tools → repeat until no tool use."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    tool_calls_made: list[ToolCall] = []
    last_result: CompletionResult | None = None

    for round_n in range(max_tool_rounds):
        result = client.complete(
            system=system,
            messages=messages,
            tools=registry.definitions(),
            model=model,
            thinking=thinking,
        )
        last_result = result

        # Parse response for tool use blocks
        raw = result.raw_response if hasattr(result, "raw_response") else None
        tool_uses = _extract_tool_uses(result)

        if not tool_uses:
            return AgentResult(
                final_text=result.text,
                tool_calls=tool_calls_made,
                completion=result,
                iterations=round_n + 1,
            )

        # Build assistant message with full content blocks
        assistant_content = _build_assistant_content(result, tool_uses)
        messages.append({"role": "assistant", "content": assistant_content})

        # Execute tools and build tool_result blocks
        tool_results = []
        for tu in tool_uses:
            tool_result = registry.execute(tu["name"], tu["input"])
            error = tool_result.startswith("ERROR:")
            tool_calls_made.append(ToolCall(
                tool_name=tu["name"],
                tool_input=tu["input"],
                result=tool_result,
                error=error,
            ))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": tool_result,
            })

        messages.append({"role": "user", "content": tool_results})

    # Exhausted rounds — return last text
    return AgentResult(
        final_text=last_result.text if last_result else "",
        tool_calls=tool_calls_made,
        completion=last_result,
        iterations=max_tool_rounds,
    )


def _extract_tool_uses(result: CompletionResult) -> list[dict]:
    """Extract tool_use blocks from raw Anthropic response."""
    if not hasattr(result, "_raw_content"):
        return []
    uses = []
    for block in result._raw_content:
        if hasattr(block, "type") and block.type == "tool_use":
            uses.append({"id": block.id, "name": block.name, "input": block.input})
    return uses


def _build_assistant_content(result: CompletionResult, tool_uses: list[dict]) -> list[dict]:
    """Reconstruct assistant content blocks for the Anthropic message format."""
    blocks: list[dict] = []
    if result.thinking:
        blocks.append({"type": "thinking", "thinking": result.thinking})
    if result.text:
        blocks.append({"type": "text", "text": result.text})
    for tu in tool_uses:
        blocks.append({"type": "tool_use", "id": tu["id"], "name": tu["name"], "input": tu["input"]})
    return blocks
