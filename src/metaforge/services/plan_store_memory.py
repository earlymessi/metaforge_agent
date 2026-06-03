"""E2E / 离线用内存计划库（PyMongo Collection 最小子集）。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId


class _InsertResult:
    def __init__(self, inserted_id: ObjectId):
        self.inserted_id = inserted_id


class _UpdateResult:
    def __init__(self, matched: int, modified: int = 0):
        self.matched_count = matched
        self.modified_count = modified


class _DeleteResult:
    def __init__(self, deleted: int):
        self.deleted_count = deleted


class _MemoryCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)

    def sort(self, key: str, direction: int = -1):
        reverse = direction == -1

        def _key(d: Dict[str, Any]):
            v = d.get(key)
            return v if v is not None else ""

        self._docs.sort(key=_key, reverse=reverse)
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class InMemoryPlanCollection:
    """供 plan_store.configure_plan_store 使用的内存 work_orders 集合。"""

    def __init__(self) -> None:
        self._by_id: Dict[ObjectId, Dict[str, Any]] = {}

    def insert_one(self, doc: Dict[str, Any]) -> _InsertResult:
        oid = ObjectId()
        stored = deepcopy(doc)
        stored["_id"] = oid
        self._by_id[oid] = stored
        return _InsertResult(oid)

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if "_id" in query:
            oid = query["_id"]
            if not isinstance(oid, ObjectId):
                try:
                    oid = ObjectId(str(oid))
                except Exception:
                    return None
            doc = self._by_id.get(oid)
            return deepcopy(doc) if doc else None
        for doc in self._by_id.values():
            if all(doc.get(k) == v for k, v in query.items()):
                return deepcopy(doc)
        return None

    def find(self, query: Optional[Dict[str, Any]] = None) -> _MemoryCursor:
        query = query or {}
        docs = [deepcopy(d) for d in self._by_id.values()]
        if not query:
            return _MemoryCursor(docs)
        out = []
        for doc in docs:
            if all(doc.get(k) == v for k, v in query.items()):
                out.append(doc)
        return _MemoryCursor(out)

    def delete_one(self, query: Dict[str, Any]) -> _DeleteResult:
        doc = self.find_one(query)
        if not doc or "_id" not in doc:
            return _DeleteResult(0)
        oid = doc["_id"]
        if oid in self._by_id:
            del self._by_id[oid]
            return _DeleteResult(1)
        return _DeleteResult(0)

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> _UpdateResult:
        doc = self.find_one(query)
        if not doc or "_id" not in doc:
            return _UpdateResult(0)
        oid = doc["_id"]
        target = self._by_id.get(oid)
        if not target:
            return _UpdateResult(0)
        sets = update.get("$set") or {}
        for k, v in sets.items():
            target[k] = deepcopy(v)
        return _UpdateResult(1, len(sets))


def seed_default_e2e_plans(jobs: Optional[List[Any]] = None) -> Dict[str, str]:
    """写入常用计划名 → plan_id，供落库 / bind 类用例。"""
    from metaforge.services import plan_store

    if not plan_store.is_configured():
        return {}
    job_list = list(jobs or [])
    names = [
        "演示-A",
        "E2E-试产01",
        "试产01",
        "E2E-Persist-Base",
        "春季批次",
        "计划 A",
        "旧版",
        "benchmark_a",
    ]
    out: Dict[str, str] = {}
    for name in names:
        existing, _ = plan_store.find_by_query(name)
        if isinstance(existing, dict) and existing.get("id"):
            out[name] = str(existing["id"])
            continue
        doc, err = plan_store.create_plan(plan_name=name, jobs=job_list)
        if doc and doc.get("id"):
            out[name] = str(doc["id"])
    return out
