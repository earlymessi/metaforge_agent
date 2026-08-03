from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from metaforge.strategy.guardrails import validate_strategy
from metaforge.strategy.models import SchedulingStrategy
from metaforge.strategy.run_state import get_run, update_run


def _require_run(run_id: str) -> Dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise KeyError(f"run not found: {run_id!r}")
    return run


def approve_strategy(run_id: str) -> Dict[str, Any]:
    run = _require_run(run_id)
    draft = run.get("strategy_draft")
    if draft is None:
        return update_run(
            run_id,
            status="FAILED",
            error="no strategy_draft to approve",
        )
    return update_run(
        run_id,
        status="RUNNING",
        stage="solve",
        strategy_approved=dict(draft),
    )


def reject_strategy(run_id: str, *, reason: str = "") -> Dict[str, Any]:
    _require_run(run_id)
    return update_run(
        run_id,
        status="CANCELLED",
        stage="hitl_strategy",
        error=reason or "rejected by user",
    )


def edit_and_approve(
    run_id: str,
    strategy_dict: Dict[str, Any],
    *,
    jobs: Iterable[Any] = (),
    machines: Iterable[Any] = (),
    workers: Optional[Iterable[Any]] = None,
    tools: Optional[Iterable[Any]] = None,
    allow_simulated: bool = True,
) -> Dict[str, Any]:
    _require_run(run_id)
    strategy = SchedulingStrategy.from_dict(strategy_dict)
    ok, errors, fixed = validate_strategy(
        strategy,
        jobs=jobs,
        machines=machines,
        workers=workers,
        tools=tools,
        allow_simulated=allow_simulated,
    )
    if not ok:
        return update_run(
            run_id,
            status="WAITING_APPROVAL",
            stage="hitl_strategy",
            strategy_draft=strategy_dict,
            validation_errors=errors,
        )
    approved = fixed.to_dict()
    return update_run(
        run_id,
        status="RUNNING",
        stage="solve",
        strategy_draft=approved,
        strategy_approved=approved,
        validation_errors=[],
    )
