"""Diffusion p-batch construct: same-family batches with sync start/end."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


def _furnace_caps(fab_meta: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    machines = list((fab_meta or {}).get("batch_machines") or [])
    if machines:
        return machines
    return [{"id": "F1", "machine_index": 0, "max_batch_size": 4}]


def construct_batches(
    jobs: List[Dict[str, Any]],
    fab_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    """
    Greedy: group by family_id, pack into furnace capacity, schedule batches
    sequentially on round-robin furnaces. Returns (fab_batches, notes, gantt).
    """
    notes: List[str] = []
    furnaces = _furnace_caps(fab_meta)
    if not furnaces:
        furnaces = [{"id": "F1", "machine_index": 0, "max_batch_size": 4}]

    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for job in jobs:
        fam = str(job.get("family_id") or "default")
        by_family.setdefault(fam, []).append(job)

    batches: List[Dict[str, Any]] = []
    gantt: List[Dict[str, Any]] = []
    furnace_ready = {int(f.get("machine_index") or 0): 0.0 for f in furnaces}
    fi = 0

    for fam, lots in sorted(by_family.items()):
        lots_sorted = sorted(lots, key=lambda j: float(j.get("material_arrival") or 0))
        cap_default = int(furnaces[0].get("max_batch_size") or 4)
        i = 0
        while i < len(lots_sorted):
            furn = furnaces[fi % len(furnaces)]
            fi += 1
            mid = int(furn.get("machine_index") if furn.get("machine_index") is not None else 0)
            cap = int(furn.get("max_batch_size") or cap_default)
            group = lots_sorted[i : i + cap]
            i += len(group)

            release = max(float(j.get("material_arrival") or 0) for j in group)
            start = max(furnace_ready.get(mid, 0.0), release)
            # duration from first task
            duration = 1.0
            for j in group:
                tasks = j.get("tasks") or []
                if tasks and isinstance(tasks[0], dict):
                    duration = max(duration, float(tasks[0].get("duration") or 1))
            end = start + duration
            furnace_ready[mid] = end

            lot_ids = [str(j.get("job_id") or j.get("name")) for j in group]
            batch = {
                "lot_ids": lot_ids,
                "family_id": fam,
                "machine_id": mid,
                "machine_index": mid,
                "max_batch_size": cap,
                "starts": [start] * len(group),
                "ends": [end] * len(group),
                "start": start,
                "end": end,
            }
            batches.append(batch)
            notes.append(
                f"batch family={fam} size={len(group)}/{cap} machine={mid} "
                f"[{start:.1f},{end:.1f}] lots={lot_ids}"
            )

            # one gantt bar per lot (same interval = synchronized)
            for j in group:
                # job_id index resolved later; use name for now, solve.py remaps
                gantt.append(
                    {
                        "job_id": str(j.get("job_id") or j.get("name")),
                        "job_name": str(j.get("job_id") or j.get("name")),
                        "operation_id": 0,
                        "operation_name": (j.get("tasks") or [{}])[0].get("name")
                        if j.get("tasks")
                        else "diffusion",
                        "machine_id": mid,
                        "start": start,
                        "end": end,
                        "family_id": fam,
                    }
                )

    return batches, notes, gantt


def run_batch_construct(
    jobs: List[Dict[str, Any]],
    *,
    fab_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    jobs = deepcopy(jobs)
    batches, notes, gantt = construct_batches(jobs, fab_meta)

    # map job names → indices for evaluator (sorted like problem builder)
    sorted_jobs = sorted(
        jobs,
        key=lambda x: int(x.get("priority") or 10),
        reverse=True,
    )
    name_to_idx = {
        str(j.get("job_id") or j.get("name")): idx for idx, j in enumerate(sorted_jobs)
    }
    for item in gantt:
        key = str(item.get("job_id"))
        if key in name_to_idx:
            item["job_id"] = name_to_idx[key]

    makespan = max((float(b.get("end") or 0) for b in batches), default=0.0)
    return {
        "jobs": sorted_jobs,
        "gantt_data": gantt,
        "fab_batches": batches,
        "metrics": {"makespan": makespan},
        "batch_notes": notes,
        "schedule_id": "batch_construct",
    }
