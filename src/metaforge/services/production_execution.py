"""MES 产线执行态：当前计划、基准甘特、仿真时钟。"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from metaforge.services.schedule_summary import normalize_schedule_results, resolve_plan_schedule_map
from metaforge.utils.solver_registry import resolve_solver_id, try_resolve_solver_id

ACTIVE_ID = "active"
DEFAULT_SIM_SPEED = 60.0  # 1 墙钟分 = 1 排程 h


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_sim_time(
    *,
    started_at_wall: str,
    sim_speed: float,
    makespan: float,
    status: str,
    paused_accum_sec: float = 0.0,
    sim_time_frozen: Optional[float] = None,
) -> float:
    """墙钟推进仿真时间；paused 时返回 sim_time_frozen。"""
    if status == "paused" and sim_time_frozen is not None:
        return float(min(makespan, sim_time_frozen))
    if status not in ("running", "paused"):
        return 0.0
    started = _parse_iso(started_at_wall)
    now = datetime.now(timezone.utc)
    elapsed = max(0.0, (now - started).total_seconds() - float(paused_accum_sec or 0))
    sim_h = elapsed / 3600.0 * float(sim_speed)
    return float(min(makespan, sim_h))


def gantt_makespan(gantt: List[Dict[str, Any]]) -> float:
    if not gantt:
        return 0.0
    return float(max(float(op.get("end") or 0) for op in gantt))


def _normalized_solver_map(schedule_map: Any) -> Dict[str, Any]:
    if not schedule_map or not isinstance(schedule_map, dict):
        return {}
    if any(isinstance(v, dict) and "gantt_data" in v for v in schedule_map.values()):
        return schedule_map
    return normalize_schedule_results(schedule_map)


def _match_schedule_key(sr: Dict[str, Any], solver_ref: str) -> Optional[str]:
    """在 schedule_result 键中匹配 solver_ref（支持 sa / 模拟退火 等等价名）。"""
    ref = (solver_ref or "").strip()
    if not ref:
        return None
    want = try_resolve_solver_id(ref, default=ref.lower())
    if ref in sr:
        return ref
    for key in sr:
        if try_resolve_solver_id(key, default=key.lower()) == want:
            return key
    return None


def resolve_solver_entry(schedule_map: Any, solver_id: str) -> Tuple[str, Dict[str, Any]]:
    """返回规范 solver id 与结果条目（schedule_map 键可为 id 或中文展示名）。"""
    sr = _normalized_solver_map(schedule_map)
    if not sr:
        raise ValueError("schedule_result missing")
    matched = _match_schedule_key(sr, solver_id)
    if matched:
        entry = sr[matched]
        if isinstance(entry, dict) and not entry.get("error"):
            return resolve_solver_id(matched), entry
    valid = [k for k, v in sr.items() if isinstance(v, dict) and not v.get("error")]
    if len(valid) == 1:
        only = valid[0]
        return resolve_solver_id(only), sr[only]
    raise ValueError(f"solver {solver_id!r} not in schedule_result or has no valid result")


def extract_solver_result(schedule_map: Any, solver_id: str) -> Dict[str, Any]:
    """从已归一化的 {solver_id: entry} 映射中取出指定算法结果。"""
    _, entry = resolve_solver_entry(schedule_map, solver_id)
    return entry


def build_execution_doc(
    order_doc: Dict[str, Any],
    solver_id: str,
    *,
    sim_speed: float = DEFAULT_SIM_SPEED,
) -> Dict[str, Any]:
    sr_map = resolve_plan_schedule_map(order_doc)
    if not sr_map:
        raise ValueError("plan has no schedule_result")
    resolved_sid, entry = resolve_solver_entry(sr_map, solver_id)
    gantt = list(entry.get("gantt_data") or [])
    if not gantt:
        raise ValueError("solver result has no gantt_data")
    ms = gantt_makespan(gantt)
    if ms <= 0:
        bs = entry.get("best_score")
        if bs is not None:
            ms = float(bs)

    interp = order_doc.get("interpretation") or {}
    weights = interp.get("weights") or order_doc.get("weights")
    strategy_id = interp.get("strategy_id") or order_doc.get("strategy_id") or "balanced"

    now_iso = datetime.now(timezone.utc).isoformat()
    jobs = order_doc.get("jobs") or []
    return {
        "_id": ACTIVE_ID,
        "status": "running",
        "plan_id": str(order_doc.get("_id", "")),
        "plan_name": order_doc.get("plan_name") or "未命名计划",
        "baseline_solver": resolved_sid,
        "baseline_gantt": copy.deepcopy(gantt),
        "strategy_id": strategy_id,
        "weights": copy.deepcopy(weights) if weights else None,
        "jobs_snapshot": copy.deepcopy(jobs),
        "makespan": ms,
        "sim_time": 0.0,
        "sim_speed": float(sim_speed),
        "started_at_wall": now_iso,
        "updated_at_wall": now_iso,
        "paused_accum_sec": 0.0,
        "sim_time_frozen": None,
        "paused_at_wall": None,
    }


def idle_state() -> Dict[str, Any]:
    return {"status": "idle", "sim_speed": DEFAULT_SIM_SPEED, "time_unit": "h"}


async def get_active(collection) -> Optional[Dict[str, Any]]:
    return await collection.find_one({"_id": ACTIVE_ID})


async def tick_sim_time(collection, doc: Dict[str, Any]) -> Dict[str, Any]:
    """运行中重算 sim_time 并写库。"""
    if doc.get("status") != "running":
        return doc
    frozen = doc.get("sim_time_frozen")
    sim = compute_sim_time(
        started_at_wall=str(doc["started_at_wall"]),
        sim_speed=float(doc.get("sim_speed") or DEFAULT_SIM_SPEED),
        makespan=float(doc.get("makespan") or 0),
        status=str(doc.get("status")),
        paused_accum_sec=float(doc.get("paused_accum_sec") or 0),
        sim_time_frozen=frozen if doc.get("status") == "paused" else None,
    )
    doc = {**doc, "sim_time": sim, "updated_at_wall": datetime.now(timezone.utc).isoformat()}
    await collection.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    return doc


async def start_execution(
    execution_coll,
    orders_coll,
    *,
    plan_id: str,
    solver_id: str,
    sim_speed: float = DEFAULT_SIM_SPEED,
) -> Dict[str, Any]:
    from bson import ObjectId

    oid = ObjectId(plan_id)
    order = await orders_coll.find_one({"_id": oid})
    if not order:
        raise ValueError("plan not found")
    doc = build_execution_doc(order, solver_id, sim_speed=sim_speed)
    await execution_coll.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    return doc


async def pause_execution(execution_coll) -> Dict[str, Any]:
    doc = await get_active(execution_coll)
    if not doc or doc.get("status") != "running":
        raise ValueError("no running execution")
    doc = await tick_sim_time(execution_coll, doc)
    now_iso = datetime.now(timezone.utc).isoformat()
    doc["status"] = "paused"
    doc["sim_time_frozen"] = float(doc.get("sim_time") or 0)
    doc["paused_at_wall"] = now_iso
    doc["updated_at_wall"] = now_iso
    await execution_coll.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    return doc


async def resume_execution(execution_coll) -> Dict[str, Any]:
    doc = await get_active(execution_coll)
    if not doc or doc.get("status") != "paused":
        raise ValueError("execution not paused")
    paused_at = doc.get("paused_at_wall")
    if paused_at:
        started = _parse_iso(str(doc["started_at_wall"]))
        pause_start = _parse_iso(str(paused_at))
        now = datetime.now(timezone.utc)
        extra = max(0.0, (now - pause_start).total_seconds())
        doc["paused_accum_sec"] = float(doc.get("paused_accum_sec") or 0) + extra
    doc["status"] = "running"
    doc["sim_time_frozen"] = None
    doc["paused_at_wall"] = None
    doc["started_at_wall"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at_wall"] = doc["started_at_wall"]
    await execution_coll.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    return await tick_sim_time(execution_coll, doc)


async def reset_execution(execution_coll) -> None:
    await execution_coll.delete_one({"_id": ACTIVE_ID})


async def get_state(execution_coll) -> Dict[str, Any]:
    doc = await get_active(execution_coll)
    if not doc:
        return idle_state()
    if doc.get("status") == "running":
        doc = await tick_sim_time(execution_coll, doc)
    out = dict(doc)
    out["time_unit"] = "h"
    return out


async def sync_execution_after_event_reschedule(
    execution_coll,
    data: Dict[str, Any],
    envelope: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """与生产看板 REST 重排一致：将 R2 甘特写回 MES，避免轮询还原为计划库旧数据。"""
    exec_doc = envelope.get("production_execution") or {}
    if exec_doc.get("status") not in ("running", "paused"):
        return None

    impact = data.get("impact_report") or {}
    results = data.get("results") or {}
    solver = impact.get("rescheduled_solver") or impact.get("baseline_solver")
    gantt = impact.get("r2_gantt")
    if not gantt and solver:
        gantt = (results.get(solver) or {}).get("gantt_data")

    jobs = data.get("updated_jobs")
    if jobs is None:
        jobs = list(envelope.get("base_jobs") or [])
        if envelope.get("event_type") == "insert_order":
            ins = (envelope.get("params") or {}).get("insert_job")
            if ins:
                jobs = jobs + [ins]

    if not gantt:
        return None
    from metaforge.services.plan_schedule import build_impact_summary_payload

    impact_summary = build_impact_summary_payload(impact)
    updated = await apply_reschedule_to_execution(
        execution_coll,
        gantt=gantt,
        jobs_snapshot=jobs,
        solver_id=solver,
        impact_summary=impact_summary,
        reschedule_results=results if results else None,
    )
    if updated:
        data["production_execution"] = updated
    return updated


async def apply_reschedule_to_execution(
    execution_coll,
    *,
    gantt: List[Dict[str, Any]],
    jobs_snapshot: Optional[List[Dict[str, Any]]] = None,
    solver_id: Optional[str] = None,
    impact_summary: Optional[Dict[str, Any]] = None,
    reschedule_results: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """事件重排后更新 MES 基准甘特与工单快照（插单/故障恢复）。"""
    doc = await get_active(execution_coll)
    if not doc or doc.get("status") not in ("running", "paused"):
        return None
    if not gantt:
        return doc

    doc = copy.deepcopy(doc)
    doc["baseline_gantt"] = copy.deepcopy(gantt)
    doc["makespan"] = gantt_makespan(gantt)
    if jobs_snapshot is not None:
        doc["jobs_snapshot"] = copy.deepcopy(jobs_snapshot)
    if solver_id:
        doc["baseline_solver"] = str(solver_id)
    if impact_summary is not None:
        doc["last_impact_summary"] = copy.deepcopy(impact_summary)
        inner = (impact_summary or {}).get("impact_report") or impact_summary
        if isinstance(inner, dict):
            doc["last_impact_gantt"] = {
                "r0": inner.get("r0_gantt"),
                "r1": inner.get("r1_gantt"),
                "r2": inner.get("r2_gantt"),
            }
    if reschedule_results is not None:
        doc["last_reschedule_results"] = copy.deepcopy(reschedule_results)

    sim = min(float(doc.get("sim_time") or 0), doc["makespan"])
    doc["sim_time"] = sim
    if doc.get("sim_time_frozen") is not None:
        doc["sim_time_frozen"] = min(float(doc["sim_time_frozen"]), doc["makespan"])
    doc["updated_at_wall"] = datetime.now(timezone.utc).isoformat()
    await execution_coll.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    if doc.get("status") == "running":
        doc = await tick_sim_time(execution_coll, doc)
    out = dict(doc)
    out["time_unit"] = "h"
    return out
