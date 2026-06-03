"""HITL 落库：内存或 MongoDB confirm token（15 分钟有效，一次性）。"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from metaforge.services import persist_store_mongo

TTL_SECONDS = 15 * 60
_pending: Dict[str, Dict[str, Any]] = {}


def persist_store_mode() -> str:
    return os.getenv("SESSION_STORE", "memory").strip().lower()


def use_mongo_persist() -> bool:
    return persist_store_mode() == "mongo" and persist_store_mongo.is_configured()


def configure_mongo_persist(collection) -> None:
    """注入 hitl_pending collection。"""
    persist_store_mongo.configure(collection)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _purge_expired() -> None:
    now = time.time()
    if use_mongo_persist():
        persist_store_mongo.purge_expired()
    expired = [k for k, v in _pending.items() if v.get("expires_at_ts", 0) <= now]
    for k in expired:
        _pending.pop(k, None)


def _pick_best_schedule(schedule_results: Dict[str, Any]) -> tuple:
    best_sid = None
    best_entry: Dict[str, Any] = {}
    best_score = float("inf")
    for sid, entry in (schedule_results or {}).items():
        if entry.get("error"):
            continue
        sc = float(entry.get("best_score") or entry.get("score") or 0)
        if sc > 0 and sc < best_score:
            best_score = sc
            best_sid = sid
            best_entry = entry
    if best_sid is None and schedule_results:
        best_sid = next(iter(schedule_results.keys()))
        best_entry = schedule_results[best_sid]
    return best_sid, best_entry


def build_preview(
    *,
    plan_id: str,
    plan_name: str,
    schedule_result: Dict[str, Any],
    delivery_assessment: Optional[Dict[str, Any]] = None,
    has_existing_schedule: bool = False,
    previous_schedule: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    metrics = schedule_result.get("metrics") or {}
    high_risk: List[Dict[str, Any]] = []
    if delivery_assessment:
        for j in delivery_assessment.get("jobs") or []:
            if j.get("risk_level") in ("high", "critical"):
                high_risk.append(
                    {
                        "job_name": j.get("job_name"),
                        "risk_level": j.get("risk_level"),
                        "predicted_completion": j.get("predicted_completion"),
                        "due_date": j.get("due_date"),
                    }
                )
    preview: Dict[str, Any] = {
        "plan_id": plan_id,
        "plan_name": plan_name,
        "best_solver": schedule_result.get("id") or schedule_result.get("name"),
        "makespan": metrics.get("makespan"),
        "best_score": schedule_result.get("best_score"),
        "high_risk_jobs": high_risk[:10],
        "high_risk_count": len(high_risk),
        "delivery_overall": (delivery_assessment or {}).get("overall"),
        "summary_zh": (delivery_assessment or {}).get("summary_zh", ""),
        "has_existing_schedule": has_existing_schedule,
        "action_zh": "覆盖已有排程" if has_existing_schedule else "首次落库",
    }
    if previous_schedule:
        preview["previous_makespan"] = previous_schedule.get("makespan")
        preview["previous_best_solver"] = previous_schedule.get("best_solver")
        preview["previous_best_score"] = previous_schedule.get("best_score")
    if jobs is not None:
        preview["jobs_update_count"] = len(jobs)
    return preview


def propose_persist(
    *,
    plan_id: str,
    schedule_result: Dict[str, Any],
    schedule_results: Optional[Dict[str, Any]] = None,
    delivery_assessment: Optional[Dict[str, Any]] = None,
    plan_name: Optional[str] = None,
    interpretation: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Any]] = None,
    impact_summary: Optional[Dict[str, Any]] = None,
    has_existing_schedule: bool = False,
    previous_schedule: Optional[Dict[str, Any]] = None,
    persist_status: str = "done",
) -> Dict[str, Any]:
    _purge_expired()
    token = uuid.uuid4().hex
    expires_at = _utc_now() + timedelta(seconds=TTL_SECONDS)
    preview = build_preview(
        plan_id=plan_id,
        plan_name=plan_name or plan_id,
        schedule_result=schedule_result,
        delivery_assessment=delivery_assessment,
        has_existing_schedule=has_existing_schedule,
        previous_schedule=previous_schedule,
        jobs=jobs,
    )
    entry = {
        "plan_id": plan_id,
        "plan_name": plan_name or plan_id,
        "schedule_result": schedule_result,
        "schedule_results": schedule_results or {},
        "delivery_assessment": delivery_assessment,
        "interpretation": interpretation,
        "jobs": jobs,
        "impact_summary": impact_summary,
        "persist_status": persist_status,
        "preview": preview,
        "created_at": _utc_now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "expires_at_ts": expires_at.timestamp(),
    }
    if use_mongo_persist():
        persist_store_mongo.put(token, entry)
    else:
        _pending[token] = entry
    return {
        "confirm_token": token,
        "expires_at": expires_at.isoformat(),
        "preview": preview,
    }


def get_pending(token: str) -> Optional[Dict[str, Any]]:
    _purge_expired()
    if use_mongo_persist():
        entry = persist_store_mongo.get(token)
        if entry:
            return entry
    return _pending.get(token)


def pop_pending(token: str) -> Optional[Dict[str, Any]]:
    _purge_expired()
    if use_mongo_persist():
        entry = persist_store_mongo.pop(token)
        _pending.pop(token, None)
        if entry:
            return entry
    entry = _pending.pop(token, None)
    if not entry:
        return None
    if entry.get("expires_at_ts", 0) <= time.time():
        return None
    return entry


def clear_pending_store() -> None:
    """测试用：清空 pending。"""
    _pending.clear()
    if persist_store_mongo.is_configured():
        persist_store_mongo.clear_all()


async def confirm_and_persist(token: str, orders_collection) -> Dict[str, Any]:
    entry = pop_pending(token)
    if not entry:
        return {"error": "invalid_or_expired_token"}

    from bson import ObjectId

    try:
        oid = ObjectId(entry["plan_id"])
    except Exception:
        return {"error": "invalid_plan_id"}

    from metaforge.services.plan_schedule import build_schedule_update_doc

    sr_multi = entry.get("schedule_results")
    persist_status = entry.get("persist_status") or "done"
    if sr_multi:
        update_doc = build_schedule_update_doc(
            sr_multi,
            delivery_assessment=entry.get("delivery_assessment"),
            interpretation=entry.get("interpretation"),
            impact_summary=entry.get("impact_summary"),
            jobs=entry.get("jobs"),
            status=persist_status,
        )
    else:
        update_doc = {
            "schedule_result": entry["schedule_result"],
            "status": persist_status,
        }
        if entry.get("delivery_assessment"):
            update_doc["delivery_assessment"] = entry["delivery_assessment"]
        if entry.get("interpretation"):
            update_doc["interpretation"] = entry["interpretation"]
        if entry.get("impact_summary"):
            update_doc["impact_summary"] = entry["impact_summary"]
        if entry.get("jobs") is not None:
            update_doc["jobs"] = entry["jobs"]

    result = await orders_collection.update_one({"_id": oid}, {"$set": update_doc})
    if result.matched_count == 0:
        return {"error": "plan_not_found"}

    return {
        "status": "success",
        "plan_id": entry["plan_id"],
        "preview": entry.get("preview"),
        "modified": result.modified_count,
    }
