"""事件重排共享辅助函数。"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from metaforge.utils.delivery_prediction import build_commitment_changes, compute_delivery_predictions


def _op_key(op: Dict[str, Any]) -> Tuple[int, int]:
    return (
        int(op.get("job_id", 0)),
        int(op.get("operation_id", op.get("id", 0))),
    )


def rescheduled_op_keys(r0: List[Dict[str, Any]], r2: List[Dict[str, Any]]) -> List[str]:
    r0_map = {_op_key(op): op for op in r0 or []}
    keys: List[str] = []
    for op in r2 or []:
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


def _gantt_makespan(gantt: List[Dict[str, Any]]) -> float:
    ends = [float(op.get("end") or 0) for op in (gantt or [])]
    return max(ends) if ends else 0.0


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
    baseline_gantt: Optional[List[Dict[str, Any]]] = None,
    new_gantt: Optional[List[Dict[str, Any]]] = None,
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

    # 扩展事件也带对比甘特：左=原计划，右=重排（无独立 R1 扰动态时 r1=r0）
    if baseline_gantt is not None and new_gantt is not None:
        r0 = copy.deepcopy(baseline_gantt)
        r2 = copy.deepcopy(new_gantt)
        r0_ms = _gantt_makespan(r0)
        r2_ms = _gantt_makespan(r2)
        report["r0_gantt"] = r0
        report["r1_gantt"] = copy.deepcopy(r0)
        report["r2_gantt"] = r2
        report["scenarios"] = {
            "r0": {"label": "原计划", "makespan": r0_ms},
            "r1": {"label": "原计划", "makespan": r0_ms},
            "r2": {"label": "重排后", "makespan": r2_ms},
        }
        layers = dict(report.get("gantt_layers") or {})
        layers["rescheduled_op_keys"] = rescheduled_op_keys(r0, r2)
        blocks = (extra or {}).get("downtime_blocks") or report.get("downtime_blocks") or []
        if blocks:
            windows = []
            for b in blocks:
                if not isinstance(b, dict) or b.get("machine_id") is None:
                    continue
                windows.append(
                    {
                        "machine_id": int(b["machine_id"]),
                        "start": float(b.get("start", 0)),
                        "end": float(b.get("end", 0)),
                        "label": str(b.get("label") or "停机"),
                    }
                )
            if windows:
                layers["downtime_windows"] = windows
                # 复用故障窗渲染：取第一段
                layers["breakdown_window"] = {
                    "machine_id": windows[0]["machine_id"],
                    "start": windows[0]["start"],
                    "end": windows[0]["end"],
                    "label": windows[0].get("label") or "停机",
                }
        report["gantt_layers"] = layers
    return report
