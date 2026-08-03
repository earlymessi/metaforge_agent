"""planning.strategy_evaluate — 评估候选排程方案。"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.strategy.evaluator import evaluate_candidates
from metaforge.strategy.models import SchedulingStrategy
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "strategy": {"type": "object", "description": "SchedulingStrategy JSON"},
        "candidates": {"type": "array", "description": "候选排程列表"},
        "jobs": {"type": "array"},
    },
    "required": ["strategy", "candidates"],
}

_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommended_schedule_id": {"type": ["string", "null"]},
        "ranking": {"type": "array"},
        "hard_violations": {"type": "array"},
        "soft_penalties": {"type": "array"},
        "recommendation_reason": {"type": "string"},
        "warnings": {"type": "array"},
    },
}


def _handle_strategy_evaluate(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    raw = params.get("strategy")
    if not isinstance(raw, dict):
        return ToolResult(ok=False, error="strategy must be an object")

    candidates: List[Dict[str, Any]] = list(params.get("candidates") or [])
    jobs = params.get("jobs") or ctx.extras.get("jobs") or []

    strategy = SchedulingStrategy.from_dict(raw)
    evaluation = evaluate_candidates(strategy, candidates, jobs=jobs)
    return ToolResult(ok=True, data=evaluation)


def register_strategy_evaluate_tool() -> None:
    name = "planning.strategy_evaluate"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="对候选排程方案做硬约束检查与软惩罚评分",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            handler=_handle_strategy_evaluate,
        )
    )
