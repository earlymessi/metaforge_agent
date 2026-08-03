"""Rule-based Resource Agent: machine load and bottleneck heuristics."""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.planning_collab.protocol import AgentResult, AgentTask


def run_resource_agent(task: AgentTask) -> AgentResult:
    """Aggregate task durations by machine_id; mark highest-load bottlenecks."""
    inputs = task.inputs or {}
    jobs: List[Dict[str, Any]] = list(inputs.get("jobs") or [])

    warnings: List[str] = []
    machine_load: Dict[str, float] = {}
    saw_task = False

    for job in jobs:
        tasks = job.get("tasks") or []
        if not isinstance(tasks, list):
            continue
        for task_item in tasks:
            if not isinstance(task_item, dict):
                continue
            machine_id = task_item.get("machine_id")
            if machine_id is None or machine_id == "":
                warnings.append("skip task without machine_id")
                continue
            mid = str(machine_id)
            duration = task_item.get("duration", 1)
            try:
                dur = float(duration)
            except (TypeError, ValueError):
                warnings.append(f"{mid}: invalid duration")
                continue
            saw_task = True
            machine_load[mid] = machine_load.get(mid, 0.0) + dur

    if not saw_task:
        warnings.append("no tasks found; machine load empty")
        return AgentResult(
            agent_id="resource",
            status="success",
            summary="资源分析: no tasks",
            artifacts={
                "machine_load": {},
                "bottleneck_machines": [],
            },
            warnings=warnings,
            reasoning_summary=None,
        )

    # Normalize numeric loads that are whole numbers to int for cleaner artifacts.
    normalized: Dict[str, Any] = {}
    for mid, load in machine_load.items():
        normalized[mid] = int(load) if float(load).is_integer() else load

    max_load = max(normalized.values())
    bottlenecks = sorted(
        mid for mid, load in normalized.items() if load == max_load
    )

    summary = (
        f"资源分析: machines={len(normalized)}, "
        f"bottleneck={','.join(bottlenecks) or '-'}"
    )

    return AgentResult(
        agent_id="resource",
        status="success",
        summary=summary,
        artifacts={
            "machine_load": normalized,
            "bottleneck_machines": bottlenecks,
        },
        warnings=warnings,
        reasoning_summary=None,
    )
