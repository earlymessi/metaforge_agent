"""统一 MemoryManager / 会话续聊路由。"""

import time

from metaforge.memory.manager import MemoryManager, persist_context_memory, sync_context_memory
from metaforge.memory.pending import pending_route_hint
from metaforge.orchestrator.router import resolve_agent_route
from metaforge.orchestrator.session import clear_all_sessions, create_session, get_memory_store


def setup_function():
    clear_all_sessions()


def test_working_memory_persist_and_hydrate():
    sid = create_session()
    ctx = {"session_id": sid, "artifacts": {}}
    mm = MemoryManager(sid, context=ctx)
    mm.set_working("events", "insert_job_intake", {"status": "need_input", "draft": {"name": "a"}})

    ctx2 = sync_context_memory({"session_id": sid, "artifacts": {}})
    assert ctx2["artifacts"]["insert_job_intake"]["status"] == "need_input"

    store = get_memory_store(sid)
    assert store["working"]["events:insert_job_intake"]["draft"]["name"] == "a"


def test_pending_route_events_and_scheduling():
    sid = create_session()
    ctx = {"session_id": sid, "artifacts": {}}
    mm = MemoryManager(sid, context=ctx)
    mm.set_working("events", "insert_job_intake", {"status": "need_input"})
    ctx = sync_context_memory(ctx)
    route = pending_route_hint(ctx)
    assert route and route["agent_id"] == "events"

    mm2 = MemoryManager(sid, context=ctx)
    mm2.set_scheduling(
        {
            "pending_clarification": {
                "phase": "awaiting_goal_choice",
                "expires_at_ts": time.time() + 3600,
            }
        }
    )
    mm2.set_working("events", "insert_job_intake", {})  # clear events pending
    ctx2 = {"session_id": sid, "memory_store": mm2.store}
    route2 = pending_route_hint(ctx2)
    assert route2 and route2["agent_id"] == "scheduling"


def test_resolve_agent_route_session_continue():
    ctx = {
        "artifacts": {"insert_job_intake": {"status": "need_input", "draft": {"name": "a"}}},
    }
    route = resolve_agent_route("2道工序：3号机5h", context=ctx)
    assert route["agent_id"] == "events"
    assert route["router"] == "session_continue"


def test_memory_tool_summary():
    import metaforge.tools.memory  # noqa: F401
    from metaforge.tools.registry import run_tool
    from metaforge.tools.base import ToolContext

    sid = create_session()
    mm = MemoryManager(sid)
    mm.set_working("events", "insert_job_intake", {"status": "need_input"})
    ctx = ToolContext(custom_data=None, artifacts={}, extras={"session_id": sid})
    r = run_tool("memory.run", {"action": "summary"}, ctx)
    assert r.ok
    assert "待补全插单" in (r.data or {}).get("summary_zh", "")


def test_persist_context_memory_roundtrip():
    sid = create_session()
    req = {"session_id": sid, "artifacts": {}}
    resp = {"artifacts": {"insert_job_intake": {"status": "need_input", "draft": {}}}}
    persist_context_memory(sid, req, resp)
    store = get_memory_store(sid)
    assert store["working"]["events:insert_job_intake"]["status"] == "need_input"
