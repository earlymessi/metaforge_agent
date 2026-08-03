from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_strategy_trace(run: dict) -> dict:
    """Build an SSE-mergeable strategy trace block from a planning run."""
    strategy = run.get("strategy_approved") or run.get("strategy_draft") or {}
    policy = run.get("solver_policy") or {}
    evaluation = run.get("evaluation") or {}
    package = run.get("package") or {}

    stages: List[str] = list(run.get("stages") or [])
    if not stages:
        status = run.get("status", "")
        stage = run.get("stage", "")
        if status == "WAITING_APPROVAL":
            stages = ["generate", "validate", "hitl_strategy"]
        elif status == "COMPLETED":
            stages = ["generate", "validate", "solve", "evaluate"]
        elif stage:
            stages = [stage]

    warnings: List[str] = list(run.get("warnings") or [])
    eval_warnings = evaluation.get("warnings")
    if eval_warnings:
        warnings.extend(eval_warnings)

    recommended = (
        evaluation.get("recommended_schedule_id")
        or package.get("recommended_schedule_id")
    )

    return {
        "type": "strategy_trace",
        "kind": "strategy_trace",
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "stages": stages,
        "generated_by": strategy.get("generated_by"),
        "solver_policy": {
            "primary_solvers": policy.get("primary_solvers"),
            "fallback_solver": policy.get("fallback_solver"),
            "time_budget_seconds": policy.get("time_budget_seconds"),
            "max_candidates": policy.get("max_candidates"),
            "reason": policy.get("reason"),
        },
        "recommended_schedule_id": recommended,
        "recommendation_reason": evaluation.get("recommendation_reason"),
        "failed_solvers": package.get("failed_solvers") or run.get("failed_solvers") or [],
        "warnings": warnings,
    }
