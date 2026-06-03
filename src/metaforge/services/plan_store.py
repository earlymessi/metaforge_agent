"""计划工单 MongoDB 访问（供 data.* Tool 同步调用）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from metaforge.utils.bson_safe import to_bson_safe

_coll = None


def configure_plan_store(collection) -> None:
    global _coll
    _coll = collection


def is_configured() -> bool:
    return _coll is not None


def _fix_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if doc and "_id" in doc:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
    return doc


def wrap_plan_api_response(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """API 成功响应：operation status 不得被计划字段 status(pending/done) 覆盖。"""
    if not doc:
        return {"status": "success"}
    out = dict(doc)
    plan_status = out.pop("status", None)
    if plan_status is not None:
        out["plan_status"] = plan_status
    return {"status": "success", **out}


def list_plans(*, limit: int = 30) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if _coll is None:
        return [], "plan_store not configured"
    cursor = _coll.find().sort("created_at", -1).limit(limit)
    return [_fix_id(d) for d in cursor], None


def get_plan(plan_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if _coll is None:
        return None, "plan_store not configured"
    try:
        oid = ObjectId(plan_id)
    except Exception:
        return None, "invalid plan_id"
    doc = _coll.find_one({"_id": oid})
    if not doc:
        return None, "plan not found"
    return _fix_id(doc), None


def find_by_query(query: str) -> Tuple[Optional[Any], Optional[str]]:
    """返回单条 plan dict、{ambiguous, matches} 或 None。"""
    plans, err = list_plans(limit=200)
    if err:
        return None, err
    q = (query or "").strip().lower()
    if not q:
        return None, "empty query"
    exact = next(
        (
            p
            for p in plans
            if str(p.get("id", "")).lower() == q or str(p.get("plan_name", "")).lower() == q
        ),
        None,
    )
    if exact:
        return exact, None
    partial = [
        p
        for p in plans
        if q in str(p.get("plan_name", "")).lower() or q in str(p.get("id", "")).lower()
    ]
    if len(partial) == 1:
        return partial[0], None
    if len(partial) > 1:
        return {"ambiguous": True, "matches": partial}, None
    return None, None


def create_plan(*, plan_name: str, jobs: Optional[List[Any]] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if _coll is None:
        return None, "plan_store not configured"
    name = (plan_name or "").strip()
    if not name:
        return None, "plan_name required"
    doc = {
        "plan_name": name,
        "jobs": to_bson_safe(list(jobs or [])),
        "status": "pending",
        "created_at": datetime.now(),
    }
    ins = _coll.insert_one(doc)
    doc["id"] = str(ins.inserted_id)
    return doc, None


def delete_plan(*, plan_id: str) -> Tuple[bool, Optional[str]]:
    if _coll is None:
        return False, "plan_store not configured"
    try:
        oid = ObjectId(plan_id)
    except Exception:
        return False, "invalid plan_id"
    r = _coll.delete_one({"_id": oid})
    if r.deleted_count != 1:
        return False, "plan not found"
    return True, None


def rename_plan(*, plan_id: str, new_name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if _coll is None:
        return None, "plan_store not configured"
    name = (new_name or "").strip()
    if not name:
        return None, "new_name required"
    try:
        oid = ObjectId(plan_id)
    except Exception:
        return None, "invalid plan_id"
    r = _coll.update_one({"_id": oid}, {"$set": {"plan_name": name}})
    if r.matched_count != 1:
        return None, "plan not found"
    return get_plan(plan_id)


def duplicate_plan(*, plan_id: str, new_name: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if _coll is None:
        return None, "plan_store not configured"
    doc, err = get_plan(plan_id)
    if err or not doc:
        return None, err or "plan not found"
    base = str(doc.get("plan_name") or "计划")
    name = (new_name or "").strip() or f"{base}（副本）"
    return create_plan(plan_name=name, jobs=list(doc.get("jobs") or []))


def update_plan(
    *,
    plan_id: str,
    plan_name: Optional[str] = None,
    jobs: Optional[List[Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if _coll is None:
        return None, "plan_store not configured"
    try:
        oid = ObjectId(plan_id)
    except Exception:
        return None, "invalid plan_id"
    fields: Dict[str, Any] = {}
    if plan_name is not None:
        name = (plan_name or "").strip()
        if not name:
            return None, "plan_name required"
        fields["plan_name"] = name
    if jobs is not None:
        fields["jobs"] = to_bson_safe(list(jobs))
    if not fields:
        return get_plan(plan_id)
    r = _coll.update_one({"_id": oid}, {"$set": fields})
    if r.matched_count != 1:
        return None, "plan not found"
    return get_plan(plan_id)


def apply_plan_fields(
    plan_id: str, fields: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """按 plan_id 合并写入任意字段（供排程结果等扩展字段）。"""
    if _coll is None:
        return None, "plan_store not configured"
    if not fields:
        return get_plan(plan_id)
    try:
        oid = ObjectId(plan_id)
    except Exception:
        return None, "invalid plan_id"
    r = _coll.update_one({"_id": oid}, {"$set": fields})
    if r.matched_count != 1:
        return None, "plan not found"
    return get_plan(plan_id)


def update_status(*, plan_id: str, status: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if _coll is None:
        return None, "plan_store not configured"
    st = (status or "").strip().lower()
    if st not in ("pending", "done", "archived"):
        return None, "status must be pending, done, or archived"
    try:
        oid = ObjectId(plan_id)
    except Exception:
        return None, "invalid plan_id"
    r = _coll.update_one({"_id": oid}, {"$set": {"status": st}})
    if r.matched_count != 1:
        return None, "plan not found"
    return get_plan(plan_id)
