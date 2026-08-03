from metaforge.agents.base import AgentRequest
from metaforge.agents.events_collab_bridge import EventsCollabBridge
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 15.0,
            "tasks": [
                {"machine_id": 0, "duration": 3},
                {"machine_id": 1, "duration": 2},
            ],
        },
        {
            "name": "工单B",
            "priority": 20,
            "due_date": 20.0,
            "tasks": [
                {"machine_id": 1, "duration": 4},
                {"machine_id": 0, "duration": 2},
            ],
        },
    ]


def test_bridge_build_plan_is_fixed_collab_not_llm(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PLAN_ENABLED", "1")
    monkeypatch.setenv("LLM_PLAN_AGENTS", "scheduling,events")
    agent = EventsCollabBridge()
    steps = agent.build_plan(AgentRequest(message="工单A优先级调高"))
    tools = [s.tool for s in steps]
    assert agent._plan_planner == "events_collab"
    assert "events.parse_event" in tools
    assert "events.reschedule" in tools
    assert "delivery.explain_impact" in tools


def test_bridge_run_skip_parse_has_events_trace():
    agent = EventsCollabBridge()
    req = AgentRequest(
        params={
            "skip_parse": True,
            "event_envelope": {
                "event_type": "order_cancel",
                "base_jobs": _jobs(),
                "params": {"job_names": ["工单B"]},
                "reschedule_options": {"solvers": ["spt"]},
            },
        },
        context={"custom_data": _jobs()},
    )
    resp = agent.run(req)
    assert resp.status == "success"
    assert resp.plan_planner == "events_collab"
    assert "events_trace" in resp.artifacts
    d = resp.to_dict()
    assert isinstance(d.get("events_trace"), dict)
    assert d["events_trace"]["status"] == "success"
