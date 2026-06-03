"""改交期 R0/R1/R2 影响报告。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from metaforge.utils.event_helpers import job_completion_map
from metaforge.utils.recovery_impact import _op_key, _rescheduled_keys, _scenario_metrics


def _due_date_op_keys(gantt: List[Dict[str, Any]], job_name_map: Dict[int, str], changed_names: Set[str]) -> List[str]:
    name_to_jid = {v: k for k, v in job_name_map.items()}
    changed_jids = {int(name_to_jid[n]) for n in changed_names if n in name_to_jid}
    keys: List[str] = []
    for op in gantt:
        jid = int(op.get("job_id", -1))
        if jid in changed_jids:
            keys.append(f"{jid}:{int(op.get('operation_id', op.get('id', 0)))}")
    return sorted(set(keys))


def build_due_date_impact_report(
    *,
    r0_gantt: List[Dict[str, Any]],
    r1_gantt: List[Dict[str, Any]],
    r2_gantt: List[Dict[str, Any]],
    base_problem: Any,
    new_problem: Any,
    job_name_map: Dict[int, str],
    due_date_changes: List[Dict[str, Any]],
    baseline_solver: str,
    rescheduled_solver: str,
    resource_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    r0_m = _scenario_metrics(r0_gantt, base_problem, resource_config)
    r1_m = _scenario_metrics(r1_gantt, new_problem, resource_config)
    r2_m = _scenario_metrics(r2_gantt, new_problem, resource_config)

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

    changed_names = {str(c.get("job_name", "")) for c in due_date_changes}
    improvement = {
        "makespan_delta": round(r2_m["makespan"] - r1_m["makespan"], 4),
        "tardiness_delta": round(
            r2_m["weighted_tardiness_total"] - r1_m["weighted_tardiness_total"], 4
        ),
    }

    return {
        "event_type": "due_date_change",
        "due_date_changes": due_date_changes,
        "changed_job_names": sorted(changed_names),
        "baseline_solver": baseline_solver,
        "rescheduled_solver": rescheduled_solver,
        "scenarios": {
            "r0": {**r0_m, "label": "原计划"},
            "r1": {**r1_m, "label": "改期不重排"},
            "r2": {**r2_m, "label": "重调度后"},
        },
        "improvement_vs_r1": improvement,
        "delay_details": delay_details,
        "affected_jobs": len([x for x in delay_details if abs(x["delta"]) > 1e-9]),
        "max_delay": max([abs(x["delta"]) for x in delay_details], default=0.0),
        "gantt_layers": {
            "rescheduled_op_keys": _rescheduled_keys(r0_gantt, r2_gantt),
            "due_date_op_keys": _due_date_op_keys(r0_gantt, job_name_map, changed_names),
        },
        "r0_gantt": r0_gantt,
        "r1_gantt": r1_gantt,
        "r2_gantt": r2_gantt,
    }
