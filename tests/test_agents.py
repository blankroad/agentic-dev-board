from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentboard.agents.base import AgentResult, run_agent, _extract_tool_uses, _build_assistant_content
from agentboard.agents.reviewer import parse_verdict
from agentboard.llm.client import CompletionResult
from agentboard.models import ReviewVerdict
from agentboard.tools.base import ToolRegistry


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_result(text: str, raw_content=None) -> CompletionResult:
    r = CompletionResult(
        text=text, thinking="", input_tokens=10, output_tokens=5,
        model="claude-sonnet-4-6", cached_tokens=0,
    )
    r._raw_content = raw_content or []
    return r


# ── parse_verdict ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("### Verdict: PASS\nAll good.", ReviewVerdict.pass_),
    ("**Verdict: RETRY**\nMissing test.", ReviewVerdict.retry),
    ("Verdict: REPLAN\nWrong approach.", ReviewVerdict.replan),
    ("No verdict found here.", ReviewVerdict.retry),  # default
])
def test_parse_verdict(text, expected):
    assert parse_verdict(text) == expected


# ── run_agent: no tool use ────────────────────────────────────────────────────

def test_run_agent_no_tools():
    mock_client = MagicMock()
    mock_client.complete.return_value = _mock_result("Final answer")

    registry = ToolRegistry()
    result = run_agent(
        client=mock_client,
        system="You are a helpful assistant.",
        user_message="What is 2+2?",
        registry=registry,
    )

    assert isinstance(result, AgentResult)
    assert result.final_text == "Final answer"
    assert result.tool_calls == []
    assert result.iterations == 1


# ── run_agent: with tool use ─────────────────────────────────────────────────

class _FakeToolUseBlock:
    def __init__(self, id_, name, input_):
        self.type = "tool_use"
        self.id = id_
        self.name = name
        self.input = input_


def test_run_agent_with_tool_use():
    mock_client = MagicMock()

    # First call: returns a tool_use block
    r1 = _mock_result("Let me check.", raw_content=[
        _FakeToolUseBlock("tu_1", "my_tool", {"arg": "hello"}),
    ])
    # Second call: no more tool use
    r2 = _mock_result("Done.")

    mock_client.complete.side_effect = [r1, r2]

    registry = ToolRegistry()

    def my_tool(arg: str) -> str:
        return f"result:{arg}"

    from agentboard.tools.base import ToolDef
    registry.register(
        ToolDef("my_tool", "test tool", {
            "type": "object",
            "properties": {"arg": {"type": "string"}},
            "required": ["arg"],
        }),
        my_tool,
    )

    result = run_agent(
        client=mock_client,
        system="sys",
        user_message="go",
        registry=registry,
    )

    assert result.final_text == "Done."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "my_tool"
    assert result.tool_calls[0].result == "result:hello"
    assert not result.tool_calls[0].error


# ── _extract_tool_uses ────────────────────────────────────────────────────────

def test_extract_tool_uses_empty():
    result = _mock_result("text")
    assert _extract_tool_uses(result) == []


def test_extract_tool_uses_with_blocks():
    result = _mock_result("text", raw_content=[
        _FakeToolUseBlock("id1", "fs_read", {"path": "x.py"}),
    ])
    uses = _extract_tool_uses(result)
    assert len(uses) == 1
    assert uses[0]["name"] == "fs_read"
    assert uses[0]["input"] == {"path": "x.py"}
