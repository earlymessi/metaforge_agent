"""FAB hard-constraint checks. Only used when domain == 'fab'.

Batch constraints require candidate['fab_batches'] (or fab_meta batches).
Without that structure, batch_* types are skipped (no false all-illegal on classic decoders).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from metaforge.fab.catalog import FAB_HARD_CONSTRAINT_TYPES
from metaforge.strategy.models import SchedulingStrategy


def _jobs_list(jobs: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for j in jobs or []:
        if isinstance(j, dict):
            out.append(j)
    return out


def _job_key(job: Dict[str, Any], index: int) -> List[str]:
    keys = {str(index)}
    for k in ("job_id", "id", "name"):
        if job.get(k) is not None and job.get(k) != "":
            keys.add(str(job[k]))
    return sorted(keys)


def _resolve_job(
    jobs: List[Dict[str, Any]],
    gantt_job_id: Any,
) -> Optional[Dict[str, Any]]:
    if not jobs:
        return None
    key = str(gantt_job_id)
    # numeric index into jobs list (JobShop gantt default)
    try:
        idx = int(gantt_job_id)
        if 0 <= idx < len(jobs):
            return jobs[idx]
    except (TypeError, ValueError):
        pass
    for i, job in enumerate(jobs):
        if key in _job_key(job, i):
            return job
    return None


def _task_is_photo(task: Dict[str, Any]) -> bool:
    area = str(task.get("process_area") or "").lower()
    if area in ("photo", "photolithography"):
        return True
    name = str(task.get("name") or "").lower()
    return "photo" in name


def _gantt_ops_for_job(gantt: Iterable[Any], job_keys: List[str]) -> List[Dict[str, Any]]:
    keys = set(job_keys)
    ops: List[Dict[str, Any]] = []
    for op in gantt or []:
        if not isinstance(op, dict):
            continue
        jid = op.get("job_id", op.get("job"))
        if jid is None:
            continue
        if str(jid) in keys:
            ops.append(op)
            continue
        try:
            if str(int(jid)) in keys:
                ops.append(op)
        except (TypeError, ValueError):
            pass
    return ops


def _check_photo_dedication(
    candidate: Dict[str, Any],
    jobs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    gantt = candidate.get("gantt_data") or []
    violations: List[Dict[str, Any]] = []

    for idx, job in enumerate(jobs):
        tasks = [t for t in (job.get("tasks") or []) if isinstance(t, dict)]
        photo_tasks = [t for t in tasks if _task_is_photo(t)]
        if len(photo_tasks) < 2:
            continue
        mark = next((t for t in photo_tasks if t.get("is_dedication_mark")), photo_tasks[0])
        mark_name = str(mark.get("name") or "")
        job_keys = _job_key(job, idx)
        ops = _gantt_ops_for_job(gantt, job_keys)
        if not ops:
            continue

        by_name = {
            str(op.get("operation_name") or op.get("name") or ""): op
            for op in ops
        }
        mark_op = by_name.get(mark_name)
        if mark_op is None:
            # fall back: first photo-named op in schedule order
            for op in ops:
                oname = str(op.get("operation_name") or op.get("name") or "").lower()
                if "photo" in oname:
                    mark_op = op
                    break
        if mark_op is None:
            continue
        dedicated = mark_op.get("machine_id")
        if dedicated is None:
            continue

        for t in photo_tasks:
            tname = str(t.get("name") or "")
            op = by_name.get(tname)
            if op is None:
                continue
            mid = op.get("machine_id")
            if mid is None:
                continue
            if int(mid) != int(dedicated):
                jid = job.get("job_id") or job.get("name") or idx
                violations.append(
                    {
                        "type": "photo_machine_dedication",
                        "job_id": str(jid),
                        "operation": tname,
                        "machine_id": mid,
                        "dedicated_machine_id": dedicated,
                        "message": (
                            f"photo_machine_dedication: job {jid!r} op {tname!r} "
                            f"on machine {mid} != dedicated {dedicated}"
                        ),
                    }
                )
    return violations


def _timelink_specs(
    strategy: SchedulingStrategy,
    fab_meta: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for c in strategy.hard_constraints:
        if c.type != "max_lag_between_ops":
            continue
        specs.append(
            {
                "from_op": c.params.get("from_op"),
                "to_op": c.params.get("to_op"),
                "max_lag": c.params.get("max_lag", c.params.get("max_lag_hours")),
            }
        )
    for tl in (fab_meta or {}).get("timelinks") or []:
        if isinstance(tl, dict):
            specs.append(
                {
                    "from_op": tl.get("from_op"),
                    "to_op": tl.get("to_op"),
                    "max_lag": tl.get("max_lag", tl.get("max_lag_hours")),
                }
            )
    # dedupe
    seen = set()
    out: List[Dict[str, Any]] = []
    for s in specs:
        key = (str(s.get("from_op")), str(s.get("to_op")), s.get("max_lag"))
        if key in seen or s.get("from_op") is None or s.get("to_op") is None or s.get("max_lag") is None:
            continue
        seen.add(key)
        out.append(s)
    return out


def _check_max_lag(
    strategy: SchedulingStrategy,
    candidate: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    fab_meta: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    specs = _timelink_specs(strategy, fab_meta)
    if not specs:
        return []
    gantt = candidate.get("gantt_data") or []
    violations: List[Dict[str, Any]] = []

    for idx, job in enumerate(jobs):
        job_keys = _job_key(job, idx)
        ops = _gantt_ops_for_job(gantt, job_keys)
        by_name = {
            str(op.get("operation_name") or op.get("name") or ""): op
            for op in ops
        }
        jid = job.get("job_id") or job.get("name") or idx
        for spec in specs:
            from_op = str(spec["from_op"])
            to_op = str(spec["to_op"])
            max_lag = float(spec["max_lag"])
            a = by_name.get(from_op)
            b = by_name.get(to_op)
            if not a or not b:
                continue
            end_a = a.get("end", a.get("finish"))
            start_b = b.get("start")
            if end_a is None or start_b is None:
                continue
            lag = float(start_b) - float(end_a)
            if lag > max_lag + 1e-9:
                violations.append(
                    {
                        "type": "max_lag_between_ops",
                        "job_id": str(jid),
                        "from_op": from_op,
                        "to_op": to_op,
                        "lag": lag,
                        "max_lag": max_lag,
                        "message": (
                            f"max_lag_between_ops: job {jid!r} {from_op}->{to_op} "
                            f"lag={lag} > max_lag={max_lag}"
                        ),
                    }
                )
    return violations


def _batch_list(candidate: Dict[str, Any], fab_meta: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for key in ("fab_batches", "batches"):
        raw = candidate.get(key)
        if isinstance(raw, list) and raw:
            return [b for b in raw if isinstance(b, dict)]
    raw = (fab_meta or {}).get("fab_batches")
    if isinstance(raw, list):
        return [b for b in raw if isinstance(b, dict)]
    return []


def _check_batches(
    strategy: SchedulingStrategy,
    candidate: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    fab_meta: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    needed = {c.type for c in strategy.hard_constraints} & {
        "batch_same_family",
        "batch_capacity",
        "batch_synchronized",
    }
    if not needed:
        return []
    batches = _batch_list(candidate, fab_meta)
    if not batches:
        # classic JSSP decoder has no batch structure — skip (not illegal)
        return []

    family_by_lot: Dict[str, Any] = {}
    for job in jobs:
        lid = str(job.get("job_id") or job.get("name") or "")
        if lid:
            family_by_lot[lid] = job.get("family_id")

    cap_by_machine: Dict[str, Any] = {}
    for m in (fab_meta or {}).get("batch_machines") or []:
        if isinstance(m, dict):
            for key in (m.get("machine_index"), m.get("id")):
                if key is not None:
                    cap_by_machine[str(key)] = m.get("max_batch_size")

    violations: List[Dict[str, Any]] = []
    for bi, batch in enumerate(batches):
        lots = [str(x) for x in (batch.get("lot_ids") or batch.get("jobs") or [])]
        if "batch_same_family" in needed and lots:
            families = {family_by_lot.get(lid) for lid in lots}
            families.discard(None)
            if len(families) > 1:
                violations.append(
                    {
                        "type": "batch_same_family",
                        "batch_index": bi,
                        "message": f"batch_same_family: mixed families {sorted(str(f) for f in families)}",
                    }
                )
        if "batch_capacity" in needed:
            mid = batch.get("machine_id", batch.get("machine_index"))
            cap = batch.get("max_batch_size")
            if cap is None and mid is not None:
                cap = cap_by_machine.get(str(mid))
            if cap is not None and len(lots) > int(cap):
                violations.append(
                    {
                        "type": "batch_capacity",
                        "batch_index": bi,
                        "size": len(lots),
                        "max_batch_size": int(cap),
                        "message": f"batch_capacity: size {len(lots)} > max {cap}",
                    }
                )
        if "batch_synchronized" in needed:
            starts = batch.get("starts") or batch.get("start_times")
            ends = batch.get("ends") or batch.get("end_times")
            if isinstance(starts, list) and len(set(float(x) for x in starts)) > 1:
                violations.append(
                    {
                        "type": "batch_synchronized",
                        "batch_index": bi,
                        "message": "batch_synchronized: start times differ within batch",
                    }
                )
            if isinstance(ends, list) and len(set(float(x) for x in ends)) > 1:
                violations.append(
                    {
                        "type": "batch_synchronized",
                        "batch_index": bi,
                        "message": "batch_synchronized: end times differ within batch",
                    }
                )
    return violations


def check_hard(
    strategy: SchedulingStrategy,
    candidate: Dict[str, Any],
    *,
    fab_meta: Optional[Dict[str, Any]] = None,
    jobs: Optional[Iterable[Any]] = None,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Return (ok, violations) for FAB hard constraints present on strategy."""
    active = {c.type for c in strategy.hard_constraints} & FAB_HARD_CONSTRAINT_TYPES
    if not active:
        return True, []

    job_list = _jobs_list(jobs)
    violations: List[Dict[str, Any]] = []

    if "photo_machine_dedication" in active:
        violations.extend(_check_photo_dedication(candidate, job_list))
    if "max_lag_between_ops" in active:
        violations.extend(_check_max_lag(strategy, candidate, job_list, fab_meta))
    if active & {"batch_same_family", "batch_capacity", "batch_synchronized"}:
        violations.extend(_check_batches(strategy, candidate, job_list, fab_meta))

    return len(violations) == 0, violations
