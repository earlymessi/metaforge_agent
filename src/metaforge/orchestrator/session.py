"""编排会话存储（内存 + 可选 MongoDB 持久化）。"""

from __future__ import annotations

import copy
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from metaforge.orchestrator import session_mongo
from metaforge.memory.types import empty_memory_store
from metaforge.utils.bson_safe import to_bson_safe

DEFAULT_TTL_SECONDS = 3600

_sessions: Dict[str, Dict[str, Any]] = {}

_CONTEXT_KEYS = (
    "plan_id",
    "custom_data",
    "benchmark_file",
    "weights",
    "random_seed",
    "enforce_material",
)


def session_store_mode() -> str:
    return os.getenv("SESSION_STORE", "memory").strip().lower()


def use_mongo_store() -> bool:
    return session_store_mode() == "mongo" and session_mongo.is_configured()


def configure_mongo_store(collection) -> None:
    """在应用启动时注入 MongoDB collection（orchestrator_sessions）。"""
    session_mongo.configure(collection)


def _purge_expired() -> None:
    now = time.time()
    if use_mongo_store():
        session_mongo.purge_expired()
    expired = [k for k, v in _sessions.items() if v.get("expires_at_ts", 0) <= now]
    for k in expired:
        _sessions.pop(k, None)


def clear_all_sessions() -> None:
    """测试用：清空全部会话。"""
    _sessions.clear()
    if session_mongo.is_configured():
        session_mongo.clear_all()


def _write_session(sid: str, payload: Dict[str, Any]) -> None:
    _sessions[sid] = payload
    if use_mongo_store():
        session_mongo.upsert(sid, payload)


def create_session(
    *,
    initial_context: Optional[Dict[str, Any]] = None,
    initial_artifacts: Optional[Dict[str, Any]] = None,
) -> str:
    _purge_expired()
    sid = uuid.uuid4().hex
    now = time.time()
    payload = {
        "session_id": sid,
        "created_at": now,
        "updated_at": now,
        "expires_at_ts": now + DEFAULT_TTL_SECONDS,
        "artifacts": copy.deepcopy(initial_artifacts or {}),
        "context": copy.deepcopy(initial_context or {}),
        "last_agent_id": None,
    }
    _write_session(sid, payload)
    return sid


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    _purge_expired()
    if use_mongo_store():
        doc = session_mongo.get(session_id)
        if doc:
            _sessions[session_id] = doc
            return doc
    return _sessions.get(session_id)


def get_artifacts(session_id: str) -> Dict[str, Any]:
    s = get_session(session_id)
    if not s:
        return {}
    return dict(s.get("artifacts") or {})


def set_artifacts(session_id: str, artifacts: Dict[str, Any]) -> bool:
    s = get_session(session_id)
    if not s:
        return False
    s["artifacts"] = copy.deepcopy(artifacts)
    s["updated_at"] = time.time()
    _write_session(session_id, s)
    return True


def merge_artifacts(session_id: str, artifacts: Dict[str, Any]) -> bool:
    s = get_session(session_id)
    if not s:
        return False
    store = s.setdefault("artifacts", {})
    for key, value in (artifacts or {}).items():
        if value is not None:
            store[key] = value
    s["updated_at"] = time.time()
    _write_session(session_id, s)
    return True


def get_memory_store(session_id: str) -> Dict[str, Any]:
    s = get_session(session_id)
    if not s:
        return empty_memory_store()
    raw = s.get("memory_store")
    if isinstance(raw, dict) and "working" in raw:
        out = empty_memory_store()
        out["working"] = dict(raw.get("working") or {})
        out["scheduling"] = dict(raw.get("scheduling") or {})
        out["episodic"] = list(raw.get("episodic") or [])
        return out
    out = empty_memory_store()
    legacy = s.get("scheduling_memory")
    if isinstance(legacy, dict):
        out["scheduling"] = dict(legacy)
    return out


def set_memory_store(session_id: str, store: Dict[str, Any]) -> bool:
    s = get_session(session_id)
    if not s:
        return False
    safe = to_bson_safe(copy.deepcopy(store))
    s["memory_store"] = safe
    sched = safe.get("scheduling") if isinstance(safe, dict) else None
    if isinstance(sched, dict):
        s["scheduling_memory"] = sched
    s["updated_at"] = time.time()
    _write_session(session_id, s)
    return True


def get_scheduling_memory(session_id: str) -> Optional[Dict[str, Any]]:
    store = get_memory_store(session_id)
    sched = store.get("scheduling")
    return dict(sched) if isinstance(sched, dict) and sched else None


def set_scheduling_memory(session_id: str, data: Dict[str, Any]) -> bool:
    store = get_memory_store(session_id)
    store["scheduling"] = to_bson_safe(copy.deepcopy(data))
    return set_memory_store(session_id, store)


def merge_context(session_id: str, context: Dict[str, Any]) -> bool:
    s = get_session(session_id)
    if not s:
        return False
    store = s.setdefault("context", {})
    for key in _CONTEXT_KEYS:
        if context.get(key) is not None:
            store[key] = to_bson_safe(context[key])
    s["updated_at"] = time.time()
    _write_session(session_id, s)
    return True


def apply_session_to_context(
    session_id: Optional[str],
    context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """将 session 中保存的 context/artifacts 合并进本次请求 context。"""
    ctx = copy.deepcopy(context or {})
    if not session_id:
        return ctx

    s = get_session(session_id)
    if not s:
        return ctx

    sess_ctx = s.get("context") or {}
    for key in _CONTEXT_KEYS:
        if ctx.get(key) is None and sess_ctx.get(key) is not None:
            ctx[key] = copy.deepcopy(sess_ctx[key])

    req_artifacts = ctx.get("artifacts")
    if not isinstance(req_artifacts, dict):
        req_artifacts = {}
    sess_artifacts = s.get("artifacts") or {}
    ctx["artifacts"] = {**sess_artifacts, **req_artifacts}
    ctx["session_id"] = session_id
    ctx["memory_store"] = get_memory_store(session_id)
    from metaforge.memory.manager import sync_context_memory

    return sync_context_memory(ctx)


def persist_after_run(
    session_id: Optional[str],
    *,
    agent_id: str,
    request_context: Dict[str, Any],
    response: Dict[str, Any],
) -> str:
    """运行结束后更新或创建 session，返回有效 session_id。"""
    sid = session_id if session_id and get_session(session_id) else create_session()
    merge_context(sid, request_context)
    from metaforge.memory.manager import persist_context_memory

    persist_context_memory(sid, request_context, response)
    merge_artifacts(sid, response.get("artifacts") or {})
    s = get_session(sid)
    if s is not None:
        s["last_agent_id"] = agent_id
        s["updated_at"] = time.time()
        _write_session(sid, s)
    return sid


def session_to_api_dict(session_id: str) -> Optional[Dict[str, Any]]:
    s = get_session(session_id)
    if not s:
        return None
    return {
        "session_id": session_id,
        "last_agent_id": s.get("last_agent_id"),
        "artifact_keys": list((s.get("artifacts") or {}).keys()),
        "context_keys": [k for k in _CONTEXT_KEYS if (s.get("context") or {}).get(k) is not None],
        "expires_at_ts": s.get("expires_at_ts"),
        "updated_at": s.get("updated_at"),
        "store": "mongo" if use_mongo_store() else "memory",
    }
