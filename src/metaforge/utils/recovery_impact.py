"""故障恢复三场景对比 R0/R1/R2。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from metaforge.utils.event_helpers import job_completion_map
from metaforge.utils.machine_labels import machine_label_zh
from metaforge.utils.metrics import compute_schedule_metrics


def _op_key(op: Dict[str, Any]) -> Tuple[int, int]:
    return (
        int(op.get("job_id", 0)),
        int(op.get("operation_id", op.get("id", 0))),
    )


def _scenario_metrics(gantt: List[Dict[str, Any]], problem: Any, resource_config: Any) -> Dict[str, float]:
    m = compute_schedule_metrics(gantt, problem, resource_config=resource_config)
    return {
        "makespan": float(m.get("makespan") or 0),
        "weighted_tardiness_total": float(m.get("weighted_tardiness_total") or 0),
    }


def _rescheduled_keys(r0: List[Dict[str, Any]], r2: List[Dict[str, Any]]) -> List[str]:
    r0_map = {_op_key(op): op for op in r0}
    keys: List[str] = []
    for op in r2:
        k = _op_key(op)
        prev = r0_map.get(k)
        if not prev:
            keys.append(f"{k[0]}:{k[1]}")
            continue
        if (
            abs(float(prev.get("start", 0)) - float(op.get("start", 0))) > 1e-6
            or abs(float(prev.get("end", 0)) - float(op.get("end", 0))) > 1e-6
            or int(prev.get("machine_id", -1)) != int(op.get("machine_id", -1))
        ):
            keys.append(f"{k[0]}:{k[1]}")
    return keys


def build_recovery_impact_report(
    *,
    r0_gantt: List[Dict[str, Any]],
    r1_gantt: List[Dict[str, Any]],
    r2_gantt: List[Dict[str, Any]],
    problem: Any,
    job_name_map: Dict[int, str],
    baseline_solver: str,
    rescheduled_solver: str,
    machine_id: int,
    breakdown_start: float,
    breakdown_end: float,
    freeze_time: float,
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

    improvement = {
        "makespan_delta": round(r2_m["makespan"] - r1_m["makespan"], 4),
        "tardiness_delta": round(
            r2_m["weighted_tardiness_total"] - r1_m["weighted_tardiness_total"], 4
        ),
    }

    report: Dict[str, Any] = {
        "event_type": "machine_breakdown",
        "machine_id": int(machine_id),
        "machine_label_zh": machine_label_zh(machine_id),
        "breakdown_start": float(breakdown_start),
        "breakdown_end": float(breakdown_end),
        "freeze_time": float(freeze_time),
        "baseline_solver": baseline_solver,
        "rescheduled_solver": rescheduled_solver,
        "scenarios": {
            "r0": {**r0_m, "label": "原计划"},
            "r1": {**r1_m, "label": "故障不重排"},
            "r2": {**r2_m, "label": "原算法重排"},
        },
        "improvement_vs_r1": improvement,
        "delay_details": delay_details,
        "gantt_layers": {
            "frozen_ops": frozen_keys,
            "breakdown_window": {
                "machine_id": int(machine_id),
                "start": float(breakdown_start),
                "end": float(breakdown_end),
            },
            "rescheduled_op_keys": _rescheduled_keys(r0_gantt, r2_gantt),
        },
        "r0_gantt": r0_gantt,
        "r1_gantt": r1_gantt,
        "r2_gantt": r2_gantt,
    }

    if r2_m["makespan"] > r1_m["makespan"] + 1e-6:
        report["warning"] = "reschedule_makespan_worse_than_r1"
        report["warning_zh"] = (
            f"原算法重排完工 {r2_m['makespan']:.1f}h 劣于故障推演 {r1_m['makespan']:.1f}h；"
            "请确认故障/冻结时刻是否应对齐 MES 当前仿真时刻（避免 freeze=0 导致整厂重排）。"
        )
    return report
