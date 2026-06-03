"""R1：故障下沿用原计划 — 序不变，阻塞右移。"""

from __future__ import annotations

import copy
from typing import Any, Dict, List


def _op_duration(op: Dict[str, Any]) -> float:
    s, e = float(op.get("start", 0)), float(op.get("end", 0))
    if e > s:
        return e - s
    return max(1.0, float(op.get("duration", 1) or 1))


def _overlaps_breakdown(start: float, end: float, b0: float, b1: float) -> bool:
    return start < b1 and end > b0


def propagate_breakdown_on_gantt(
    gantt: List[Dict[str, Any]],
    *,
    machine_id: int,
    breakdown_start: float,
    breakdown_duration: float,
) -> List[Dict[str, Any]]:
    """
    保持工序相对顺序，以原计划时间为参考；故障机台在故障窗内不可加工则右移。
    """
    if not gantt:
        return []

    b0 = float(breakdown_start)
    b1 = b0 + float(breakdown_duration)
    machine_id = int(machine_id)

    ordered = sorted(
        [copy.deepcopy(op) for op in gantt],
        key=lambda x: (
            float(x.get("start", 0)),
            int(x.get("job_id", 0)),
            int(x.get("operation_id", x.get("id", 0))),
        ),
    )

    machine_available: Dict[int, float] = {}
    job_ready: Dict[int, float] = {}
    out: List[Dict[str, Any]] = []

    for op in ordered:
        jid = int(op.get("job_id", 0))
        mid = int(op.get("machine_id", op.get("machine", 0)))
        dur = _op_duration(op)
        orig_start = float(op.get("start", 0))

        start = max(orig_start, job_ready.get(jid, 0.0), machine_available.get(mid, 0.0))
        end = start + dur

        if mid == machine_id and _overlaps_breakdown(start, end, b0, b1):
            start = b1
            end = start + dur

        # 链式：后续工序不得早于本工序结束
        op["start"] = start
        op["end"] = end
        machine_available[mid] = end
        job_ready[jid] = end
        out.append(op)

    out.sort(
        key=lambda x: (
            float(x.get("start", 0)),
            int(x.get("job_id", 0)),
            int(x.get("operation_id", x.get("id", 0))),
        )
    )
    return out
