"""事件重排共享辅助函数。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.utils.delivery_prediction import build_commitment_changes, compute_delivery_predictions


def job_completion_map(schedule_data: List[Dict[str, Any]]) -> Dict[int, float]:
    comp: Dict[int, float] = {}
    for op in schedule_data or []:
        jid = int(op["job_id"])
        comp[jid] = max(float(op["end"]), comp.get(jid, 0.0))
    return comp


def merge_repaired_schedule(
    frozen_ops: List[Dict[str, Any]],
    repaired_ops: List[Dict[str, Any]],
    residual_index_to_job_id: Dict[int, int],
) -> List[Dict[str, Any]]:
    merged = [dict(op) for op in frozen_ops]
    for op in repaired_ops:
        item = dict(op)
        residual_idx = int(item["job_id"])
        item["job_id"] = int(residual_index_to_job_id.get(residual_idx, residual_idx))
        merged.append(item)
    merged.sort(
        key=lambda x: (
            float(x.get("start", 0)),
            int(x.get("job_id", 0)),
            int(x.get("operation_id", 0)),
        )
    )
    return merged


def attach_delivery_predictions(
    results: Dict[str, Any],
    problem: Any,
    job_name_map: Dict[int, str],
) -> None:
    for res in results.values():
        cv = (res.get("metrics") or {}).get("machine_busy_cv")
        res["delivery_predictions"] = compute_delivery_predictions(
            res.get("gantt_data", []),
            problem,
            job_name_map=job_name_map,
            machine_busy_cv=cv,
        )


def build_delay_impact_report(
    *,
    baseline_completion: Dict[int, float],
    new_completion: Dict[int, float],
    job_name_map: Dict[int, str],
    before_pred: List[Dict[str, Any]],
    after_pred: List[Dict[str, Any]],
    baseline_solver: str,
    rescheduled_solver: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    delays = []
    for jid, old_end in baseline_completion.items():
        new_end = new_completion.get(jid, old_end)
        delays.append(
            {
                "job_id": jid,
                "job_name": job_name_map.get(jid, f"Job-{jid}"),
                "old_completion": old_end,
                "new_completion": new_end,
                "delta": round(float(new_end - old_end), 4),
            }
        )
    delayed = [x for x in delays if x["delta"] > 1e-9]
    report: Dict[str, Any] = {
        "baseline_solver": baseline_solver,
        "rescheduled_solver": rescheduled_solver,
        "affected_jobs": len(delayed),
        "max_delay": max([x["delta"] for x in delayed], default=0.0),
        "delay_details": sorted(delays, key=lambda x: x["delta"], reverse=True),
        "commitment_changes": build_commitment_changes(before_pred, after_pred),
    }
    if extra:
        report.update(extra)
    return report
