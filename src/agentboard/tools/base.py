from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict

    def to_anthropic(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ToolCall:
    tool_name: str
    tool_input: dict
    result: str
    error: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, ToolDef] = {}
        self._fns: dict[str, Callable[..., str]] = {}

    def register(self, defn: ToolDef, fn: Callable[..., str]) -> None:
        self._defs[defn.name] = defn
        self._fns[defn.name] = fn

    def definitions(self) -> list[dict]:
        return [d.to_anthropic() for d in self._defs.values()]

    def execute(self, name: str, inputs: dict) -> str:
        if name not in self._fns:
            return f"ERROR: Unknown tool '{name}'"
        try:
            return self._fns[name](**inputs)
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"
