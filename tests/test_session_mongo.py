"""Session / HITL Mongo 后端（Mock collection）。"""

import time
from unittest.mock import MagicMock

from metaforge.orchestrator import session_mongo
from metaforge.orchestrator.session import (
    clear_all_sessions,
    configure_mongo_store,
    create_session,
    get_session,
    persist_after_run,
)
from metaforge.services import persist_store
from metaforge.services import persist_store_mongo


def setup_function():
    clear_all_sessions()
    persist_store.clear_pending_store()
    session_mongo.configure(None)
    persist_store_mongo.configure(None)


def test_session_mongo_roundtrip():
    coll = MagicMock()
    store = {}

    def replace_one(filter_doc, doc, upsert=False):
        store[filter_doc["_id"]] = dict(doc)

    def find_one(query):
        sid = query.get("_id")
        doc = store.get(sid)
        if not doc:
            return None
        if doc.get("expires_at_ts", 0) <= time.time():
            return None
        return doc

    coll.replace_one = replace_one
    coll.find_one = find_one
    coll.delete_many = lambda q: None

    configure_mongo_store(coll)
    import os

    os.environ["SESSION_STORE"] = "mongo"

    sid = create_session(initial_artifacts={"interpretation": {"strategy_id": "delivery"}})
    assert get_session(sid) is not None

    new_sid = persist_after_run(
        sid,
        agent_id="scheduling",
        request_context={},
        response={"artifacts": {"schedule_results": {"spt": {}}}},
    )
    assert new_sid == sid
    s = get_session(sid)
    assert "schedule_results" in (s.get("artifacts") or {})

    os.environ["SESSION_STORE"] = "memory"


def test_persist_mongo_pop():
    coll = MagicMock()
    store = {}

    def replace_one(filter_doc, doc, upsert=False):
        store[filter_doc["_id"]] = dict(doc)

    def find_one_and_delete(query):
        return store.pop(query["_id"], None)

    def find_one(query):
        return store.get(query.get("_id"))

    coll.replace_one = replace_one
    coll.find_one_and_delete = find_one_and_delete
    coll.find_one = find_one
    coll.delete_many = lambda q: None

    persist_store.configure_mongo_persist(coll)
    import os

    os.environ["SESSION_STORE"] = "mongo"

    data = persist_store.propose_persist(
        plan_id="507f1f77bcf86cd799439011",
        schedule_result={"id": "spt", "metrics": {"makespan": 1}},
    )
    token = data["confirm_token"]
    assert persist_store.get_pending(token) is not None
    popped = persist_store.pop_pending(token)
    assert popped is not None
    assert persist_store.get_pending(token) is None

    os.environ["SESSION_STORE"] = "memory"
