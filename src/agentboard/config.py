from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    planner_model: str = "claude-opus-4-7"
    executor_model: str = "claude-sonnet-4-6"
    reviewer_model: str = "claude-opus-4-7"
    gauntlet_model: str = "claude-opus-4-7"
    haiku_model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 8192
    thinking_budget: int = 5000


class ToolConfig(BaseModel):
    shell_allowlist: list[str] = Field(
        default_factory=lambda: [
            "python", "pytest", "pip", "uv", "npm", "node",
            "make", "cargo", "go", "ruff", "mypy",
            "git", "gh", "ls", "cat", "head", "tail",
            "echo", "mkdir", "cp", "mv", "find", "grep",
        ]
    )
    shell_timeout: int = 60
    sandbox_enabled: bool = False


class TDDConfig(BaseModel):
    """Phase G — TDD discipline & systematic process toggles (Superpowers-inspired)."""
    enabled: bool = True                # Red-Green-Refactor loop active
    strict: bool = False                # Iron Law violation halts loop (True) vs warns (False)
    verify_with_evidence: bool = True   # Fresh-command evidence gate before review
    systematic_debug: bool = True       # 4-phase RCA in reflect
    require_atomic_steps: bool = False  # Require Gauntlet to emit atomic_steps
    allow_refactor_skip: bool = True    # LLM may skip refactor step if nothing to clean


class AgentBoardConfig(BaseModel):
    max_iterations: int = 10
    token_ceiling: int = 500_000
    git_push_policy: str = "squash"  # squash | semantic | preserve | interactive
    dry_run: bool = False
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    tdd: TDDConfig = Field(default_factory=TDDConfig)


_config: AgentBoardConfig | None = None
_agentboard_root: Path | None = None


def find_agentboard_root(start: Path | None = None) -> Path | None:
    """Walk up from start looking for .agentboard directory."""
    path = start or Path.cwd()
    for parent in [path, *path.parents]:
        candidate = parent / ".agentboard"
        if candidate.is_dir():
            return parent
    return None


def get_agentboard_dir(root: Path | None = None) -> Path:
    r = root or find_agentboard_root() or Path.cwd()
    return r / ".agentboard"


def load_config(root: Path | None = None) -> AgentBoardConfig:
    global _config
    if _config is not None:
        return _config

    config_path = get_agentboard_dir(root) / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        _config = AgentBoardConfig.model_validate(data)
    else:
        _config = AgentBoardConfig()

    return _config


def save_config(config: AgentBoardConfig, root: Path | None = None) -> None:
    config_path = get_agentboard_dir(root) / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, allow_unicode=True)


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Run: export ANTHROPIC_API_KEY=your_key"
        )
    return key
