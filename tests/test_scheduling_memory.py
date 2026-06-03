"""排程记忆：结构化澄清 + Orchestrator Session 持久化。"""

import os
import time
from unittest.mock import MagicMock

import pytest

from metaforge.orchestrator.session import (
    clear_all_sessions,
    configure_mongo_store,
    create_session,
    get_scheduling_memory,
)
from metaforge.scheduling.context import ContextManager, ClarificationState
from metaforge.scheduling.resolve_intent import resolve_schedule_intent


@pytest.fixture(autouse=True)
def _clean():
    ContextManager.clear_session()
    clear_all_sessions()
    os.environ.pop("SESSION_STORE", None)
    yield
    ContextManager.clear_session()
    clear_all_sessions()


def test_clarification_state_structure():
    state = ContextManager.set_clarification(
        "s-struct",
        original_message="满意度最高排程",
        question="请选目标",
        unmapped_phrase="满意度",
    )
    assert state.unmapped_phrase == "满意度"
    assert len(state.offered_options) == 4
    assert state.expires_at_ts > time.time()


def test_scheduling_memory_survives_context_reload():
    coll = MagicMock()
    store: dict = {}

    def replace_one(filter_doc, doc, upsert=False):
        store[filter_doc["_id"]] = dict(doc)

    def find_one(query):
        doc = store.get(query.get("_id"))
        if not doc:
            return None
        if doc.get("expires_at_ts", 0) <= time.time():
            return None
        return doc

    coll.replace_one = replace_one
    coll.find_one = find_one
    coll.delete_many = lambda q: None

    configure_mongo_store(coll)
    os.environ["SESSION_STORE"] = "mongo"

    sid = create_session()
    ContextManager.set_clarification(
        sid,
        original_message="满意度",
        question="选哪个",
        unmapped_phrase="满意度",
    )
    ContextManager.clear_session(sid)

    loaded = get_scheduling_memory(sid)
    assert loaded is not None
    assert loaded["pending_clarification"]["unmapped_phrase"] == "满意度"

    ctx = ContextManager.get(sid)
    assert ctx.pending_clarification is not None


def test_clarify_then_option_one_persists_goal():
    os.environ["LLM_ENABLED"] = "0"
    sid = "mem-flow"
    create_session()
    resolve_schedule_intent(
        {"message": "让用户满意度最高的排程"},
        session_id=sid,
    )
    result = resolve_schedule_intent({"message": "①"}, session_id=sid)
    assert result.get("full_compare")
    assert result["strategy_id"] == "delivery"

    ctx = ContextManager.get(sid)
    assert ctx.pending_clarification is None
    assert ctx.last_strategy_id == "delivery"
    assert any(e.get("type") == "clarification_resolved" for e in ctx.episodic_log)
