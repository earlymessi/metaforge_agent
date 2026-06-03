"""
工单 BOM 与库存约束：预检、排程后仿真、按优先级推算物料就绪时间。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


def _job_quantity(job: Any) -> int:
    q = getattr(job, "quantity", None)
    if q is None and isinstance(job, dict):
        q = job.get("quantity")
    try:
        return max(1, int(q or 1))
    except (TypeError, ValueError):
        return 1


def job_bom_demand(job: Any) -> Dict[str, float]:
    """单工单各物料总需求量（quantity_per_unit × 工单数量）。"""
    bom = getattr(job, "bom", None)
    if bom is None and isinstance(job, dict):
        bom = job.get("bom")
    if not bom:
        return {}

    qty = _job_quantity(job)
    demand: Dict[str, float] = {}
    for line in bom:
        if isinstance(line, dict):
            mid = str(line.get("material_id", "")).strip()
            qpu = float(line.get("quantity_per_unit", 1.0) or 1.0)
            mode = line.get("consume_mode", "job_start")
        else:
            mid = str(getattr(line, "material_id", "")).strip()
            qpu = float(getattr(line, "quantity_per_unit", 1.0) or 1.0)
            mode = getattr(line, "consume_mode", "job_start")
        if not mid:
            continue
        need = max(0.0, qpu) * qty
        if mode == "per_hour":
            # per_hour 在排程仿真中按工时扣减；静态预检按总工时估算
            total_dur = sum(
                int(getattr(t, "duration", 0) or (t.get("duration", 0) if isinstance(t, dict) else 0))
                for t in (getattr(job, "tasks", None) or (job.get("tasks", []) if isinstance(job, dict) else []))
            )
            need = need * max(1, total_dur)
        demand[mid] = demand.get(mid, 0.0) + need
    return demand


def check_jobs_material_static(
    jobs: List[Any],
    inventory: Dict[str, float],
    *,
    material_names: Optional[Dict[str, str]] = None,
    safe_levels: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """汇总 BOM 总需求与当前库存，不依赖排程结果。"""
    total_demand: Dict[str, float] = {}
    per_job: List[Dict[str, Any]] = []

    for i, job in enumerate(jobs):
        demand = job_bom_demand(job)
        name = getattr(job, "name", None) or (job.get("name") if isinstance(job, dict) else f"Job-{i}")
        lines = []
        feasible = True
        for mid, need in demand.items():
            total_demand[mid] = total_demand.get(mid, 0.0) + need
            have = float(inventory.get(mid, 0.0))
            ok = have >= need - 1e-9
            if not ok:
                feasible = False
            lines.append(
                {
                    "material_id": mid,
                    "material_name": (material_names or {}).get(mid, mid),
                    "required": round(need, 4),
                    "available": round(have, 4),
                    "shortage": round(max(0.0, need - have), 4),
                    "feasible": ok,
                }
            )
        per_job.append(
            {
                "job_index": i,
                "job_name": name,
                "feasible": feasible if lines else True,
                "lines": lines,
            }
        )

    global_lines = []
    globally_feasible = True
    for mid, need in total_demand.items():
        have = float(inventory.get(mid, 0.0))
        ok = have >= need - 1e-9
        if not ok:
            globally_feasible = False
        safe = float((safe_levels or {}).get(mid, 0.0))
        global_lines.append(
            {
                "material_id": mid,
                "material_name": (material_names or {}).get(mid, mid),
                "required_total": round(need, 4),
                "available": round(have, 4),
                "shortage": round(max(0.0, need - have), 4),
                "safe_level": safe,
                "feasible": ok,
            }
        )

    return {
        "feasible": globally_feasible and all(j["feasible"] for j in per_job),
        "total_demand": {k: round(v, 4) for k, v in total_demand.items()},
        "per_job": per_job,
        "summary": global_lines,
    }


def compute_material_arrival_delays(
    jobs: List[Any],
    inventory: Dict[str, float],
) -> Tuple[List[float], List[Dict[str, Any]]]:
    """
    按优先级顺序模拟「开工时扣料」(job_start)，为库存不足的工单推算物料就绪延迟。
    返回与 jobs 等长的 arrival 增量（小时）及说明。
    """
    n = len(jobs)
    delays = [0.0] * n
    notes: List[Dict[str, Any]] = []
    stock = deepcopy(inventory)

    order = sorted(range(n), key=lambda i: (-_job_priority(jobs[i]), i))

    for idx in order:
        job = jobs[idx]
        demand = job_bom_demand(job)
        if not demand:
            continue

        mode_start_only = True
        bom = getattr(job, "bom", None) or (job.get("bom") if isinstance(job, dict) else []) or []
        for line in bom:
            cm = line.get("consume_mode", "job_start") if isinstance(line, dict) else getattr(line, "consume_mode", "job_start")
            if cm == "per_hour":
                mode_start_only = False
                break

        if not mode_start_only:
            continue

        ok = all(stock.get(m, 0.0) >= q - 1e-9 for m, q in demand.items())
        if ok:
            for m, q in demand.items():
                stock[m] = stock.get(m, 0.0) - q
            continue

        pos = {j: i for i, j in enumerate(order)}
        wait = sum(
            sum(
                int(getattr(t, "duration", 0) or (t.get("duration", 0) if isinstance(t, dict) else 0))
                for t in (getattr(jobs[j], "tasks", None) or [])
            )
            for j in order
            if pos.get(j, 0) < pos[idx] and job_bom_demand(jobs[j])
        )
        delays[idx] = float(max(1, wait))
        name = getattr(job, "name", f"Job-{idx}")
        notes.append(
            {
                "job_index": idx,
                "job_name": name,
                "delay": delays[idx],
                "reason": "库存不足，按优先级延后开工",
                "demand": {k: round(v, 4) for k, v in demand.items()},
            }
        )

    return delays, notes


def _job_priority(job: Any) -> int:
    p = getattr(job, "priority", None)
    if p is None and isinstance(job, dict):
        p = job.get("priority")
    try:
        return int(p or 10)
    except (TypeError, ValueError):
        return 10


def _job_bom_lines(job: Any) -> List[Dict[str, Any]]:
    bom = getattr(job, "bom", None)
    if bom is None and isinstance(job, dict):
        bom = job.get("bom")
    if not bom:
        return []
    out = []
    for line in bom:
        if isinstance(line, dict):
            out.append(line)
        else:
            out.append(
                {
                    "material_id": getattr(line, "material_id", ""),
                    "quantity_per_unit": getattr(line, "quantity_per_unit", 1.0),
                    "consume_mode": getattr(line, "consume_mode", "job_start"),
                }
            )
    return out


def simulate_schedule_materials(
    schedule: List[Dict[str, Any]],
    jobs: List[Any],
    inventory: Dict[str, float],
    *,
    material_names: Optional[Dict[str, str]] = None,
    safe_levels: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """根据甘特与 BOM 仿真库存时间线，识别缺料与安全库存预警。"""
    if not schedule:
        return {
            "timeline": [],
            "shortages": [],
            "safe_warnings": [],
            "feasible": True,
            "has_safe_warning": False,
            "per_job": [],
        }

    stock_state = deepcopy(inventory)
    safe_levels = safe_levels or {}
    max_time = int(max(float(t.get("end", 0)) for t in schedule)) + 5

    # job_id -> job
    job_by_id = {i: jobs[i] for i in range(len(jobs))}

    # 每个工单首道工序开工时刻（job_start 扣料）
    first_start: Dict[int, float] = {}
    for op in schedule:
        jid = int(op.get("job_id", -1))
        if jid < 0:
            continue
        st = float(op.get("start", 0))
        if jid not in first_start or st < first_start[jid]:
            first_start[jid] = st

    shortages: List[Dict[str, Any]] = []
    safe_warnings: List[Dict[str, Any]] = []
    shortage_keys: set = set()
    warning_keys: set = set()
    per_job_events: List[Dict[str, Any]] = []

    timeline: List[Dict[str, Any]] = []

    def _append_shortage(
        *,
        mid: str,
        t: int,
        jid: int,
        job: Any,
        left: float,
        limit: float,
        consume_mode: str,
    ) -> None:
        key = (mid, t, "shortage")
        if key in shortage_keys:
            return
        shortage_keys.add(key)
        shortages.append(
            {
                "event_type": "shortage",
                "mat_id": mid,
                "name": (material_names or {}).get(mid, mid),
                "time": t,
                "left": round(left, 4),
                "limit": limit,
                "job_id": jid,
                "job_name": getattr(job, "name", f"Job-{jid}"),
                "consume_mode": consume_mode,
            }
        )

    def _append_safe_warning(
        *,
        mid: str,
        t: int,
        jid: int,
        job: Any,
        left: float,
        safe: float,
        consume_mode: str,
    ) -> None:
        key = (mid, t, "safe_warning")
        if key in warning_keys:
            return
        warning_keys.add(key)
        safe_warnings.append(
            {
                "event_type": "safe_warning",
                "mat_id": mid,
                "name": (material_names or {}).get(mid, mid),
                "time": t,
                "left": round(left, 4),
                "limit": round(safe, 4),
                "safe_level": round(safe, 4),
                "job_id": jid,
                "job_name": getattr(job, "name", f"Job-{jid}"),
                "consume_mode": consume_mode,
            }
        )

    for t in range(max_time):
        # job_start：在首道工序开始时刻扣料（允许同一时刻多个）
        for jid, st in first_start.items():
            if int(st) != t:
                continue
            job = job_by_id.get(jid)
            if not job:
                continue
            for line in _job_bom_lines(job):
                if line.get("consume_mode", "job_start") != "job_start":
                    continue
                mid = str(line.get("material_id", ""))
                if not mid:
                    continue
                qty = _job_quantity(job)
                usage = float(line.get("quantity_per_unit", 1.0) or 1.0) * qty
                stock_state[mid] = stock_state.get(mid, 0.0) - usage
                per_job_events.append(
                    {
                        "job_id": jid,
                        "job_name": getattr(job, "name", f"Job-{jid}"),
                        "material_id": mid,
                        "time": t,
                        "usage": usage,
                        "mode": "job_start",
                    }
                )
                if stock_state[mid] < 0:
                    _append_shortage(
                        mid=mid,
                        t=t,
                        jid=jid,
                        job=job,
                        left=stock_state[mid],
                        limit=0.0,
                        consume_mode="job_start",
                    )

        # per_hour：该时刻正在加工的工单按小时扣料
        active = [op for op in schedule if float(op.get("start", 0)) <= t < float(op.get("end", 0))]
        for op in active:
            jid = int(op.get("job_id", -1))
            job = job_by_id.get(jid)
            if not job:
                continue
            for line in _job_bom_lines(job):
                if line.get("consume_mode", "job_start") != "per_hour":
                    continue
                mid = str(line.get("material_id", ""))
                if not mid:
                    continue
                usage = float(line.get("quantity_per_unit", 1.0) or 1.0)
                stock_state[mid] = stock_state.get(mid, 0.0) - usage
                safe = float(safe_levels.get(mid, 0.0))
                if stock_state[mid] < 0:
                    _append_shortage(
                        mid=mid,
                        t=t,
                        jid=jid,
                        job=job,
                        left=stock_state[mid],
                        limit=0.0,
                        consume_mode="per_hour",
                    )
                elif safe > 0 and stock_state[mid] < safe:
                    _append_safe_warning(
                        mid=mid,
                        t=t,
                        jid=jid,
                        job=job,
                        left=stock_state[mid],
                        safe=safe,
                        consume_mode="per_hour",
                    )

        snap = {"time": t}
        snap.update({k: round(v, 4) for k, v in stock_state.items()})
        timeline.append(snap)

    return {
        "timeline": timeline,
        "shortages": shortages,
        "safe_warnings": safe_warnings,
        "feasible": len(shortages) == 0,
        "has_safe_warning": len(safe_warnings) > 0,
        "per_job_events": per_job_events,
    }


def build_material_report_for_schedule(
    schedule: List[Dict[str, Any]],
    jobs: List[Any],
    db_materials: List[Dict[str, Any]],
) -> Dict[str, Any]:
    inventory = {m["id"]: float(m.get("current_stock", 0)) for m in db_materials}
    names = {m["id"]: m.get("name", m["id"]) for m in db_materials}
    safe = {m["id"]: float(m.get("safe_level", 0)) for m in db_materials}
    static = check_jobs_material_static(jobs, inventory, material_names=names, safe_levels=safe)
    dynamic = simulate_schedule_materials(
        schedule,
        jobs,
        inventory,
        material_names=names,
        safe_levels=safe,
    )
    return {
        "static_check": static,
        "simulation": dynamic,
        "feasible": static.get("feasible", True) and dynamic.get("feasible", True),
        "has_safe_warning": dynamic.get("has_safe_warning", False),
        "shortage_count": len(dynamic.get("shortages") or []),
        "safe_warning_count": len(dynamic.get("safe_warnings") or []),
    }
