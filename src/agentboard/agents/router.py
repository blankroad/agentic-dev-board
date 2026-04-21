from __future__ import annotations

from agentboard.config import LLMConfig
from agentboard.llm.client import BudgetTracker


# Budget thresholds for automatic model downgrade
_DOWNGRADE_AT = 0.70   # below 30% remaining → downgrade planners to sonnet
_EMERGENCY_AT = 0.90   # below 10% remaining → downgrade everything to haiku


def route(role: str, config: LLMConfig, budget: BudgetTracker | None = None) -> str:
    """Return model ID for a given role, with cost-aware downgrade when budget is low."""
    base = _base_model(role, config)
    if budget is None:
        return base
    return _apply_budget_policy(base, budget, config)


def _base_model(role: str, config: LLMConfig) -> str:
    mapping = {
        "planner": config.planner_model,
        "executor": config.executor_model,
        "reviewer": config.reviewer_model,
        "redteam": config.reviewer_model,   # same tier as reviewer
        "reflect": config.executor_model,   # sonnet is fine for reflect
        "gauntlet": config.gauntlet_model,
        "haiku": config.haiku_model,
    }
    return mapping.get(role, config.executor_model)


def _apply_budget_policy(model: str, budget: BudgetTracker, config: LLMConfig) -> str:
    if budget.token_ceiling == 0:
        return model
    used_fraction = budget.tokens_used / budget.token_ceiling

    if used_fraction >= _EMERGENCY_AT:
        # Emergency: everything → haiku
        return config.haiku_model

    if used_fraction >= _DOWNGRADE_AT:
        # Downgrade: opus → sonnet
        if model == config.planner_model and "opus" in model:
            return config.executor_model
        if model == config.reviewer_model and "opus" in model:
            return config.executor_model

    return model


def budget_tier(budget: BudgetTracker) -> str:
    """Human-readable budget tier label."""
    if budget.token_ceiling == 0:
        return "unlimited"
    frac = budget.tokens_used / budget.token_ceiling
    if frac >= _EMERGENCY_AT:
        return "emergency"
    if frac >= _DOWNGRADE_AT:
        return "reduced"
    return "normal"
