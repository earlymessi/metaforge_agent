"""R1 插单场景：原计划不动，急单工序排到队尾。"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Union


def _task_duration(task: Any) -> float:
    if isinstance(task, dict):
        return max(1.0, float(task.get("duration", 1) or 1))
    return max(1.0, float(getattr(task, "duration", 1) or 1))


def _task_machine(task: Any) -> int:
    if isinstance(task, dict):
        mid = task.get("machine_id")
        opts = task.get("machine_options") or []
        if mid is not None:
            return int(mid)
        if opts:
            return int(opts[0])
        return 0
    mid = getattr(task, "machine_id", None)
    if mid is not None:
        return int(mid)
    opts = getattr(task, "machine_options", None) or []
    return int(opts[0]) if opts else 0


def defer_insert_to_tail_gantt(
    baseline_gantt: List[Dict[str, Any]],
    insert_job: Any,
    insert_job_id: int,
    *,
    freeze_time: float = 0.0,
    insert_priority: int = 100,
) -> List[Dict[str, Any]]:
    """
    不重排既有工单：保留 baseline 工序时间不变，插单工序按工单顺序接在全局队尾。
    """
    out = [copy.deepcopy(op) for op in baseline_gantt]
    if not insert_job:
        return out

    freeze_time = max(0.0, float(freeze_time or 0))
    machine_end: Dict[int, float] = {}
    global_end = freeze_time
    for op in baseline_gantt:
        mid = int(op.get("machine_id", 0))
        e = float(op.get("end", 0))
        machine_end[mid] = max(machine_end.get(mid, 0.0), e)
        global_end = max(global_end, e)

    tasks = insert_job.get("tasks", []) if isinstance(insert_job, dict) else insert_job.tasks
    ins_name = insert_job.get("name", "Insert") if isinstance(insert_job, dict) else getattr(insert_job, "name", "Insert")
    job_ready = max(global_end, freeze_time)

    for i, task in enumerate(tasks):
        mid = _task_machine(task)
        dur = _task_duration(task)
        tname = (
            task.get("name", f"Op-{i + 1}")
            if isinstance(task, dict)
            else getattr(task, "name", f"Op-{i + 1}")
        )
        start = max(job_ready, machine_end.get(mid, 0.0), freeze_time)
        end = start + dur
        out.append(
            {
                "job_id": int(insert_job_id),
                "operation_id": i,
                "machine_id": mid,
                "start": start,
                "end": end,
                "job_name": ins_name,
                "operation_name": tname,
                "priority": insert_priority,
            }
        )
        machine_end[mid] = end
        job_ready = end

    out.sort(
        key=lambda x: (
            float(x.get("start", 0)),
            int(x.get("job_id", 0)),
            int(x.get("operation_id", x.get("id", 0))),
        )
    )
    return out
