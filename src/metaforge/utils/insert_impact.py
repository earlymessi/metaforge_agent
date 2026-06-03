"""插单 R0/R1/R2 影响报告。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from metaforge.utils.event_helpers import job_completion_map
from metaforge.utils.recovery_impact import _op_key, _rescheduled_keys, _scenario_metrics


def build_insert_impact_report(
    *,
    r0_gantt: List[Dict[str, Any]],
    r1_gantt: List[Dict[str, Any]],
    r2_gantt: List[Dict[str, Any]],
    problem: Any,
    job_name_map: Dict[int, str],
    insert_job_id: int,
    insert_job_name: str,
    insert_job_snapshot: Optional[Dict[str, Any]] = None,
    baseline_solver: str,
    rescheduled_solver: str,
    freeze_time: float,
    mode: str,
    resource_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    r0_m = _scenario_metrics(r0_gantt, problem, resource_config)
    r1_m = _scenario_metrics(r1_gantt, problem, resource_config)
    r2_m = _scenario_metrics(r2_gantt, problem, resource_config)

    r1_comp = job_completion_map(r1_gantt)
    r2_comp = job_completion_map(r2_gantt)

    delay_details = []
    for jid, old_end in r1_comp.items():
        new_end = r2_comp.get(jid, old_end)
        delay_details.append(
            {
                "job_id": jid,
                "job_name": job_name_map.get(jid, f"Job-{jid}"),
                "old_completion": old_end,
                "new_completion": new_end,
                "delta": round(float(new_end - old_end), 4),
            }
        )
    delay_details.sort(key=lambda x: x["delta"], reverse=True)

    frozen_keys = [
        f"{_op_key(op)[0]}:{_op_key(op)[1]}"
        for op in r0_gantt
        if float(op.get("start", 0)) < freeze_time
    ]

    insert_keys: Set[str] = set()
    for op in r1_gantt:
        if int(op.get("job_id", -1)) == insert_job_id:
            insert_keys.add(f"{insert_job_id}:{int(op.get('operation_id', op.get('id', 0)))}")

    improvement = {
        "makespan_delta": round(r2_m["makespan"] - r1_m["makespan"], 4),
        "tardiness_delta": round(
            r2_m["weighted_tardiness_total"] - r1_m["weighted_tardiness_total"], 4
        ),
    }

    return {
        "event_type": "insert_order",
        "mode": mode,
        "freeze_time": float(freeze_time),
        "insert_job_id": int(insert_job_id),
        "insert_job_name": insert_job_name,
        "insert_job_snapshot": insert_job_snapshot,
        "baseline_solver": baseline_solver,
        "rescheduled_solver": rescheduled_solver,
        "scenarios": {
            "r0": {**r0_m, "label": "原计划"},
            "r1": {**r1_m, "label": "插单往后排"},
            "r2": {**r2_m, "label": "重调度后"},
        },
        "improvement_vs_r1": improvement,
        "delay_details": delay_details,
        "affected_jobs": len([x for x in delay_details if abs(x["delta"]) > 1e-9]),
        "max_delay": max([abs(x["delta"]) for x in delay_details], default=0.0),
        "gantt_layers": {
            "frozen_ops": frozen_keys,
            "freeze_time": float(freeze_time),
            "insert_job_id": int(insert_job_id),
            "rescheduled_op_keys": _rescheduled_keys(r0_gantt, r2_gantt),
            "insert_op_keys": sorted(insert_keys),
        },
        "r0_gantt": r0_gantt,
        "r1_gantt": r1_gantt,
        "r2_gantt": r2_gantt,
    }
