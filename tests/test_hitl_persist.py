"""HITL 落库 store / API 测试。"""

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from metaforge.services import persist_store
from metaforge.services import persist_store_mongo


@pytest.fixture(autouse=True)
def clear_store():
    os.environ["SESSION_STORE"] = "memory"
    persist_store_mongo.configure(None)
    persist_store.clear_pending_store()
    yield
    persist_store_mongo.configure(None)
    persist_store.clear_pending_store()


def test_propose_and_get_pending():
    result = persist_store.propose_persist(
        plan_id="507f1f77bcf86cd799439011",
        schedule_result={"id": "spt", "best_score": 10.0, "metrics": {"makespan": 12.0}},
        plan_name="测试计划",
    )
    assert result["confirm_token"]
    assert result["preview"]["plan_name"] == "测试计划"
    entry = persist_store.get_pending(result["confirm_token"])
    assert entry is not None


def test_confirm_rejects_invalid_token():
    import asyncio

    coll = MagicMock()
    coll.update_one = AsyncMock()
    result = asyncio.run(persist_store.confirm_and_persist("bad-token", coll))
    assert result["error"] == "invalid_or_expired_token"
    coll.update_one.assert_not_called()


def test_confirm_expired_token():
    import asyncio

    data = persist_store.propose_persist(
        plan_id="507f1f77bcf86cd799439011",
        schedule_result={"id": "spt", "metrics": {"makespan": 1}},
    )
    token = data["confirm_token"]
    persist_store._pending[token]["expires_at_ts"] = time.time() - 1

    coll = MagicMock()
    coll.update_one = AsyncMock()
    result = asyncio.run(persist_store.confirm_and_persist(token, coll))
    assert result["error"] == "invalid_or_expired_token"


def test_confirm_success_writes_db():
    import asyncio

    plan_id = "507f1f77bcf86cd799439011"
    data = persist_store.propose_persist(
        plan_id=plan_id,
        schedule_result={"id": "spt", "best_score": 5.0, "metrics": {"makespan": 8.0}},
        schedule_results={"spt": {"id": "spt", "best_score": 5.0, "metrics": {"makespan": 8.0}}},
        delivery_assessment={"overall": "met", "jobs": []},
        jobs=[{"name": "J1", "due_date": 20.0, "tasks": []}],
        impact_summary={"summary_zh": "test"},
        has_existing_schedule=True,
        previous_schedule={"makespan": 10.0, "best_solver": "ts"},
    )
    coll = MagicMock()
    coll.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))

    result = asyncio.run(persist_store.confirm_and_persist(data["confirm_token"], coll))
    assert result["status"] == "success"
    coll.update_one.assert_called_once()
    call_doc = coll.update_one.call_args[0][1]["$set"]
    assert call_doc.get("jobs")
    assert call_doc.get("impact_summary")
    assert persist_store.get_pending(data["confirm_token"]) is None


def test_hitl_routes_registered():
    from main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/db/propose_save" in paths
    assert "/api/db/confirm_save" in paths
    assert "/api/db/propose_schedule" in paths
