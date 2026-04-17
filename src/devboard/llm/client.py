from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from devboard.config import LLMConfig, get_api_key


@dataclass
class CompletionResult:
    text: str
    thinking: str
    input_tokens: int
    output_tokens: int
    model: str
    cached_tokens: int = 0
    _raw_content: list = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_estimate_usd(self) -> float:
        prices = {
            "claude-opus-4-7": (0.000015, 0.000075),
            "claude-sonnet-4-6": (0.000003, 0.000015),
            "claude-haiku-4-5-20251001": (0.0000008, 0.000004),
        }
        in_price, out_price = prices.get(self.model, (0.000015, 0.000075))
        cached_discount = self.cached_tokens * in_price * 0.1
        effective_input = (self.input_tokens - self.cached_tokens) * in_price
        return effective_input + cached_discount + self.output_tokens * out_price


@dataclass
class BudgetTracker:
    goal_id: str
    token_ceiling: int
    tokens_used: int = 0
    cost_usd: float = 0.0
    calls: list[dict] = field(default_factory=list)

    def record(self, result: CompletionResult, step: str) -> None:
        self.tokens_used += result.total_tokens
        self.cost_usd += result.cost_estimate_usd
        self.calls.append({
            "step": step,
            "model": result.model,
            "input": result.input_tokens,
            "output": result.output_tokens,
            "cached": result.cached_tokens,
        })

    @property
    def remaining(self) -> int:
        return max(0, self.token_ceiling - self.tokens_used)

    @property
    def over_budget(self) -> bool:
        return self.tokens_used >= self.token_ceiling


class LLMClient:
    def __init__(self, config: LLMConfig | None = None, api_key: str | None = None) -> None:
        self._config = config or LLMConfig()
        self._api_key = api_key or get_api_key()
        self._client = anthropic.Anthropic(api_key=self._api_key)

    def complete(
        self,
        messages: list[dict],
        system: str | list[dict],
        model: str | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
        max_tokens: int | None = None,
        cache_system: bool = True,
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        model = model or self._config.planner_model
        max_tokens = max_tokens or self._config.max_tokens
        thinking_budget = thinking_budget or self._config.thinking_budget

        system_blocks = self._build_system(system, cache=cache_system)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
        }

        if thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            kwargs["max_tokens"] = max(max_tokens, thinking_budget + 4096)
            kwargs["betas"] = ["interleaved-thinking-2025-05-14"]

        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        text = ""
        thinking_text = ""
        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    text += block.text
                elif block.type == "thinking":
                    thinking_text += getattr(block, "thinking", "")

        cached = getattr(response.usage, "cache_read_input_tokens", 0) or 0

        result = CompletionResult(
            text=text,
            thinking=thinking_text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
            cached_tokens=cached,
        )
        result._raw_content = response.content
        return result

    def _build_system(self, system: str | list[dict], cache: bool) -> list[dict]:
        if isinstance(system, str):
            block: dict = {"type": "text", "text": system}
            if cache:
                block["cache_control"] = {"type": "ephemeral"}
            return [block]
        blocks = list(system)
        if cache and blocks:
            last = dict(blocks[-1])
            last["cache_control"] = {"type": "ephemeral"}
            blocks[-1] = last
        return blocks


def load_prompt(name: str) -> str:
    """Load a prompt template from llm/prompts/."""
    base = Path(__file__).parent / "prompts"
    parts = name.split("/")
    path = base.joinpath(*parts)
    if not path.suffix:
        path = path.with_suffix(".md")
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text()
