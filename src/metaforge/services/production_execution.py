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


SUPPORTED_SCHEDULED_EVENTS = frozenset(
    {
        "machine_breakdown",
        "insert_order",
        "due_date_change",
        "planned_downtime",
        "material_delay",
        "priority_change",
        "order_cancel",
        "quantity_change",
    }
)

EVENT_LABELS_ZH = {
    "machine_breakdown": "设备故障",
    "insert_order": "插单",
    "due_date_change": "改交期",
    "planned_downtime": "计划停机",
    "material_delay": "物料晚到",
    "priority_change": "调整优先级",
    "order_cancel": "撤单",
    "quantity_change": "数量变更",
}


async def get_state(execution_coll) -> Dict[str, Any]:
    doc = await get_active(execution_coll)
    if not doc:
        return idle_state()
    if doc.get("status") == "running":
        doc = await tick_sim_time(execution_coll, doc)
        doc = await maybe_fire_scheduled_event(execution_coll, doc)
    out = dict(doc)
    out["time_unit"] = "h"
    # 兼容旧前端：把 scheduled_event 镜像成 scheduled_breakdown（仅故障）
    se = out.get("scheduled_event")
    if isinstance(se, dict) and se.get("event_type") == "machine_breakdown":
        params = se.get("params") or {}
        out["scheduled_breakdown"] = {
            "machine_id": params.get("machine_id"),
            "breakdown_start": se.get("trigger_at", params.get("breakdown_start")),
            "breakdown_duration": params.get("breakdown_duration"),
            "status": se.get("status"),
            "summary_zh": se.get("summary_zh"),
            "error": se.get("error"),
            "fired_at_sim": se.get("fired_at_sim"),
        }
    return out


def _legacy_breakdown_as_event(sb: Dict[str, Any]) -> Dict[str, Any]:
    """旧 scheduled_breakdown → scheduled_event。"""
    start = sb.get("breakdown_start")
    return {
        "event_type": "machine_breakdown",
        "trigger_at": start,
        "params": {
            "machine_id": sb.get("machine_id"),
            "breakdown_start": start,
            "breakdown_duration": sb.get("breakdown_duration"),
        },
        "status": sb.get("status") or "pending",
        "summary_zh": sb.get("summary_zh"),
        "error": sb.get("error"),
        "fired_at_sim": sb.get("fired_at_sim"),
    }


def get_scheduled_event(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    se = doc.get("scheduled_event")
    if isinstance(se, dict) and se.get("event_type"):
        return se
    sb = doc.get("scheduled_breakdown")
    if isinstance(sb, dict) and sb.get("status"):
        return _legacy_breakdown_as_event(sb)
    return None


def _scheduled_event_ready(doc: Dict[str, Any]) -> bool:
    se = get_scheduled_event(doc)
    if not se or se.get("status") != "pending":
        return False
    if doc.get("status") != "running":
        return False
    try:
        trigger = float(se.get("trigger_at"))
        sim = float(doc.get("sim_time") or 0)
    except (TypeError, ValueError):
        return False
    return sim + 1e-9 >= trigger


def _validate_scheduled_params(event_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(params or {})
    if event_type == "machine_breakdown":
        if p.get("machine_id") is None:
            raise ValueError("machine_breakdown requires machine_id")
        if p.get("breakdown_duration") is None:
            raise ValueError("machine_breakdown requires breakdown_duration")
        if float(p["breakdown_duration"]) <= 0:
            raise ValueError("breakdown_duration must be > 0")
        p["machine_id"] = int(p["machine_id"])
        p["breakdown_duration"] = float(p["breakdown_duration"])
    elif event_type == "insert_order":
        if not isinstance(p.get("insert_job"), dict):
            raise ValueError("insert_order requires insert_job")
        p.setdefault("mode", "local_repair")
    elif event_type == "due_date_change":
        if not p.get("due_date_changes"):
            raise ValueError("due_date_change requires due_date_changes")
    elif event_type == "planned_downtime":
        if not p.get("downtime_blocks"):
            raise ValueError("planned_downtime requires downtime_blocks")
    elif event_type == "material_delay":
        if not p.get("job_name"):
            raise ValueError("material_delay requires job_name")
        p["delay_hours"] = float(p.get("delay_hours") or 0)
    elif event_type == "priority_change":
        if not p.get("changes"):
            raise ValueError("priority_change requires changes")
    elif event_type == "order_cancel":
        if not p.get("job_names"):
            raise ValueError("order_cancel requires job_names")
    elif event_type == "quantity_change":
        if not p.get("changes"):
            raise ValueError("quantity_change requires changes")
    return p


def _enrich_params_at_fire(
    event_type: str,
    params: Dict[str, Any],
    *,
    trigger_at: float,
    sim_time: float,
) -> Dict[str, Any]:
    p = dict(params or {})
    if event_type == "machine_breakdown":
        p.setdefault("breakdown_start", trigger_at)
        p.setdefault("freeze_time", sim_time)
    elif event_type == "insert_order":
        p.setdefault("freeze_time", sim_time)
    elif event_type == "planned_downtime":
        blocks = list(p.get("downtime_blocks") or [])
        for b in blocks:
            if isinstance(b, dict):
                b.setdefault("start", trigger_at)
                if b.get("end") is None and b.get("duration") is not None:
                    b["end"] = float(b["start"]) + float(b["duration"])
        p["downtime_blocks"] = blocks
    return p


def _summary_for_schedule(event_type: str, trigger_at: float, params: Dict[str, Any]) -> str:
    label = EVENT_LABELS_ZH.get(event_type, event_type)
    if event_type == "machine_breakdown":
        mid = params.get("machine_id")
        dur = params.get("breakdown_duration")
        return f"已预约：{label}（{mid}号机，{dur:g}h）@ {trigger_at:g}h，仿真到达后自动重排"
    if event_type == "material_delay":
        return f"已预约：{label}（{params.get('job_name')}）@ {trigger_at:g}h"
    if event_type == "insert_order":
        name = (params.get("insert_job") or {}).get("name") or "急单"
        return f"已预约：{label}「{name}」@ {trigger_at:g}h"
    return f"已预约：{label} @ {trigger_at:g}h，仿真到达后自动重排"


async def schedule_event(
    execution_coll,
    *,
    event_type: str,
    trigger_at: float,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """预约动态事件：仿真时钟到达 trigger_at 时自动重排（非 Agent，事件注入器）。"""
    et = str(event_type or "").strip()
    if et not in SUPPORTED_SCHEDULED_EVENTS:
        raise ValueError(f"unsupported event_type: {et}")
    doc = await get_active(execution_coll)
    if not doc or doc.get("status") not in ("running", "paused"):
        raise ValueError("no active execution; start MES first")
    start = float(trigger_at)
    if start < 0:
        raise ValueError("trigger_at must be >= 0")
    validated = _validate_scheduled_params(et, params or {})
    if et == "machine_breakdown":
        validated.setdefault("breakdown_start", start)

    summary = _summary_for_schedule(et, start, validated)
    se = {
        "event_type": et,
        "trigger_at": start,
        "params": validated,
        "status": "pending",
        "summary_zh": summary,
        "error": None,
    }
    doc = copy.deepcopy(doc)
    doc["scheduled_event"] = se
    # 故障时双写旧字段，兼容未刷新的前端
    if et == "machine_breakdown":
        doc["scheduled_breakdown"] = {
            "machine_id": validated.get("machine_id"),
            "breakdown_start": start,
            "breakdown_duration": validated.get("breakdown_duration"),
            "status": "pending",
            "summary_zh": summary,
            "error": None,
        }
    else:
        doc.pop("scheduled_breakdown", None)
    doc.pop("auto_reschedule_notify", None)
    doc["updated_at_wall"] = datetime.now(timezone.utc).isoformat()
    await execution_coll.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    out = dict(doc)
    out["time_unit"] = "h"
    return out


async def schedule_breakdown(
    execution_coll,
    *,
    machine_id: int,
    breakdown_start: float,
    breakdown_duration: float,
) -> Dict[str, Any]:
    """兼容旧 API：预约设备故障。"""
    return await schedule_event(
        execution_coll,
        event_type="machine_breakdown",
        trigger_at=float(breakdown_start),
        params={
            "machine_id": int(machine_id),
            "breakdown_start": float(breakdown_start),
            "breakdown_duration": float(breakdown_duration),
        },
    )


async def cancel_scheduled_event(execution_coll) -> Dict[str, Any]:
    doc = await get_active(execution_coll)
    if not doc or doc.get("status") == "idle":
        raise ValueError("no active execution")
    doc = copy.deepcopy(doc)
    se = doc.get("scheduled_event")
    if isinstance(se, dict) and se.get("status") == "pending":
        doc["scheduled_event"] = {**se, "status": "cancelled"}
    sb = doc.get("scheduled_breakdown")
    if isinstance(sb, dict) and sb.get("status") == "pending":
        doc["scheduled_breakdown"] = {**sb, "status": "cancelled"}
    doc["updated_at_wall"] = datetime.now(timezone.utc).isoformat()
    await execution_coll.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    out = dict(doc)
    out["time_unit"] = "h"
    return out


async def cancel_scheduled_breakdown(execution_coll) -> Dict[str, Any]:
    return await cancel_scheduled_event(execution_coll)


async def ack_auto_reschedule(execution_coll) -> Dict[str, Any]:
    """前端已消费自动重排通知后清除，防止轮询重复弹窗。"""
    doc = await get_active(execution_coll)
    if not doc:
        return idle_state()
    doc = copy.deepcopy(doc)
    notify = doc.get("auto_reschedule_notify")
    if isinstance(notify, dict):
        notify = {**notify, "acked": True}
        doc["auto_reschedule_notify"] = notify
    doc["updated_at_wall"] = datetime.now(timezone.utc).isoformat()
    await execution_coll.replace_one({"_id": ACTIVE_ID}, doc, upsert=True)
    out = dict(doc)
    out["time_unit"] = "h"
    return out


async def _claim_scheduled_event(execution_coll, trigger_at: float) -> Optional[Dict[str, Any]]:
    """CAS：pending → firing，避免并发 get_state 双触发。"""
    from pymongo import ReturnDocument

    # 优先认领 scheduled_event；兼容仅有旧 scheduled_breakdown 的文档
    claimed = await execution_coll.find_one_and_update(
        {
            "_id": ACTIVE_ID,
            "status": "running",
            "scheduled_event.status": "pending",
            "sim_time": {"$gte": float(trigger_at) - 1e-9},
        },
        {
            "$set": {
                "scheduled_event.status": "firing",
                "updated_at_wall": datetime.now(timezone.utc).isoformat(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if claimed:
        return claimed

    return await execution_coll.find_one_and_update(
        {
            "_id": ACTIVE_ID,
            "status": "running",
            "scheduled_breakdown.status": "pending",
            "sim_time": {"$gte": float(trigger_at) - 1e-9},
        },
        {
            "$set": {
                "scheduled_breakdown.status": "firing",
                "updated_at_wall": datetime.now(timezone.utc).isoformat(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )


async def maybe_fire_scheduled_event(execution_coll, doc: Dict[str, Any]) -> Dict[str, Any]:
    """仿真时刻越过预约事件 → 自动 dispatch 重排并暂停等待 HITL。"""
    if not _scheduled_event_ready(doc):
        return doc

    se0 = get_scheduled_event(doc) or {}
    try:
        trigger_at = float(se0.get("trigger_at"))
    except (TypeError, ValueError):
        return doc

    claimed = await _claim_scheduled_event(execution_coll, trigger_at)
    if not claimed:
        fresh = await get_active(execution_coll)
        return fresh or doc

    se = get_scheduled_event(claimed) or dict(se0)
    et = str(se.get("event_type") or "machine_breakdown")
    label = EVENT_LABELS_ZH.get(et, et)
    sim = float(claimed.get("sim_time") or trigger_at)
    params = _enrich_params_at_fire(
        et,
        se.get("params") or {},
        trigger_at=trigger_at,
        sim_time=sim,
    )

    try:
        from metaforge.services.event_reschedule import dispatch_event_reschedule
        from metaforge.utils.bson_safe import to_bson_safe

        envelope = {
            "event_type": et,
            "base_jobs": list(claimed.get("jobs_snapshot") or []),
            "params": params,
            "reschedule_options": {
                "solvers": [claimed["baseline_solver"]] if claimed.get("baseline_solver") else None,
                "weights": claimed.get("weights"),
                "baseline_gantt": claimed.get("baseline_gantt"),
                "baseline_solver": claimed.get("baseline_solver"),
                "freeze_time": sim,
                "mode": params.get("mode"),
            },
            "production_execution": claimed,
        }
        raw = dispatch_event_reschedule(envelope)
        if raw.get("error"):
            raise RuntimeError(str(raw.get("error")))

        data = raw.get("data") or {}
        await sync_execution_after_event_reschedule(execution_coll, data, envelope)

        fresh = await get_active(execution_coll)
        if not fresh:
            return claimed
        fresh = copy.deepcopy(fresh)
        now_iso = datetime.now(timezone.utc).isoformat()
        if fresh.get("status") == "running":
            fresh["status"] = "paused"
            fresh["sim_time_frozen"] = float(fresh.get("sim_time") or sim)
            fresh["paused_at_wall"] = now_iso

        fired_at = float(fresh.get("sim_time") or sim)
        se_done = {
            **se,
            "params": params,
            "status": "fired",
            "fired_at_sim": fired_at,
            "summary_zh": f"{label}已自动触发重排（@{fired_at:.1f}h）",
            "error": None,
        }
        summary = (
            f"系统注入：{label} @ 仿真 {trigger_at:g}h，"
            f"已自动完成重排并暂停执行，请确认是否落库。"
        )
        fresh["scheduled_event"] = se_done
        if et == "machine_breakdown":
            fresh["scheduled_breakdown"] = {
                "machine_id": params.get("machine_id"),
                "breakdown_start": trigger_at,
                "breakdown_duration": params.get("breakdown_duration"),
                "status": "fired",
                "fired_at_sim": fired_at,
                "summary_zh": se_done["summary_zh"],
                "error": None,
            }
        fresh["auto_reschedule_notify"] = to_bson_safe(
            {
                "event_type": et,
                "source": "scheduled_event",
                "acked": False,
                "fired_at_sim": fired_at,
                "summary_zh": summary,
                "result": raw,
            }
        )
        fresh["updated_at_wall"] = now_iso
        await execution_coll.replace_one({"_id": ACTIVE_ID}, fresh, upsert=True)
        out = dict(fresh)
        out["time_unit"] = "h"
        return out
    except Exception as exc:  # noqa: BLE001
        fresh = await get_active(execution_coll) or claimed
        fresh = copy.deepcopy(fresh)
        failed = {
            **se,
            "status": "failed",
            "error": str(exc),
            "summary_zh": f"预约{label}自动重排失败：{exc}",
        }
        fresh["scheduled_event"] = failed
        if et == "machine_breakdown":
            fresh["scheduled_breakdown"] = {
                **(fresh.get("scheduled_breakdown") or {}),
                "status": "failed",
                "error": str(exc),
                "summary_zh": failed["summary_zh"],
            }
        fresh["updated_at_wall"] = datetime.now(timezone.utc).isoformat()
        await execution_coll.replace_one({"_id": ACTIVE_ID}, fresh, upsert=True)
        out = dict(fresh)
        out["time_unit"] = "h"
        return out


# 旧名别名（测试/外部引用）
_scheduled_breakdown_ready = _scheduled_event_ready
maybe_fire_scheduled_breakdown = maybe_fire_scheduled_event


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
