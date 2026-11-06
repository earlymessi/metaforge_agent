"""Supervisor dispatches analysis agents via AgentRuntime."""

from __future__ import annotations

from metaforge.planning_collab.supervisor import run_collab_analyze


def test_analyze_returns_run_events_from_harness():
    out = run_collab_analyze(
        user_goal="保证关键订单按期",
        jobs=[{"job_id": "J1", "due_date": 10, "priority": 1}],
        machines=[{"machine_id": "M1"}],
        parallel=False,
        llm_client=None,
    )
    assert out["status"] in ("ANALYZED", "FAILED")
    assert out.get("context_hash")
    events = out.get("run_events") or []
    types = [e["type"] for e in events]
    assert "supervisor.start" in types
    assert "supervisor.end" in types
    assert "agent.start" in types
    assert "agent.end" in types
    assert any(e.get("agent_id") == "order" for e in events)
