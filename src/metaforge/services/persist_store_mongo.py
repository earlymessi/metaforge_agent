"""HITL confirm token 的 MongoDB 持久化。"""

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


def put(token: str, entry: Dict[str, Any]) -> None:
    if _collection is None:
        return
    doc = to_bson_safe({"_id": token, **entry})
    _collection.replace_one({"_id": token}, doc, upsert=True)


def get(token: str) -> Optional[Dict[str, Any]]:
    if _collection is None:
        return None
    purge_expired()
    doc = _collection.find_one({"_id": token, "expires_at_ts": {"$gt": time.time()}})
    if not doc:
        return None
    out = dict(doc)
    out.pop("_id", None)
    return out


def pop(token: str) -> Optional[Dict[str, Any]]:
    if _collection is None:
        return None
    purge_expired()
    doc = _collection.find_one_and_delete({"_id": token, "expires_at_ts": {"$gt": time.time()}})
    if not doc:
        return None
    out = dict(doc)
    out.pop("_id", None)
    return out


def clear_all() -> None:
    if _collection is None:
        return
    _collection.delete_many({})
