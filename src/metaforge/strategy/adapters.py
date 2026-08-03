from __future__ import annotations

from typing import Any, Dict, Tuple

from metaforge.strategy.models import SchedulingStrategy

_WEIGHT_KEYS = frozenset(
    {"makespan", "weighted_tardiness_total", "energy_cost", "machine_busy_cv"}
)


def _downtime_block_from_constraint(params: Dict[str, Any]) -> Dict[str, Any] | None:
    machine_id = params.get("machine_id")
    end = params.get("end")
    if machine_id is None or end is None:
        return None
    return {
        "machine_id": machine_id,
        "start": float(params.get("start", 0)),
        "end": float(end),
        "label": params.get("label", "machine_unavailable"),
    }


def strategy_to_solver_inputs(strategy: SchedulingStrategy) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Map SchedulingStrategy to solver weights and resource hints."""
    weights = {
        key: float(value)
        for key, value in strategy.objectives.items()
        if key in _WEIGHT_KEYS
    }

    hints: Dict[str, Any] = {}
    extra_objectives = {
        key: float(value)
        for key, value in strategy.objectives.items()
        if key not in _WEIGHT_KEYS
    }
    if extra_objectives:
        hints["extra_objectives"] = extra_objectives

    downtime_blocks = []
    for constraint in strategy.hard_constraints:
        if constraint.type != "machine_unavailable":
            continue
        block = _downtime_block_from_constraint(constraint.params)
        if block is not None:
            downtime_blocks.append(block)

    if downtime_blocks:
        hints["resource_config_patch"] = {"downtime_blocks": downtime_blocks}

    return weights, hints
