"""Orchestrator Session 的 MongoDB 持久化。"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from metaforge.utils.bson_safe import to_bson_safe

_collection: Any = None


def configure(collection) -> None:
    global _collection
    _collection = collection


def is_configured() -> bool:
    return _collection is not None


def purge_expired() -> None:
    if _collection is None:
        return
    _collection.delete_many({"expires_at_ts": {"$lte": time.time()}})


def get(session_id: str) -> Optional[Dict[str, Any]]:
    if _collection is None:
        return None
    purge_expired()
    doc = _collection.find_one({"_id": session_id, "expires_at_ts": {"$gt": time.time()}})
    if not doc:
        return None
    out = dict(doc)
    out.pop("_id", None)
    out["session_id"] = session_id
    return out


def upsert(session_id: str, payload: Dict[str, Any]) -> None:
    if _collection is None:
        return
    doc = to_bson_safe({"_id": session_id, **payload})
    _collection.replace_one({"_id": session_id}, doc, upsert=True)


def delete(session_id: str) -> None:
    if _collection is None:
        return
    _collection.delete_one({"_id": session_id})


def clear_all() -> None:
    if _collection is None:
        return
    _collection.delete_many({})
