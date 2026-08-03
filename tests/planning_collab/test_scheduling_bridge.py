from metaforge.agents.base import AgentRequest
from metaforge.orchestrator.router import get_agent


def test_get_agent_scheduling_uses_collab_bridge():
    agent = get_agent("scheduling")
    assert agent.__class__.__name__ == "SchedulingCollabBridge"


def test_get_agent_scheduling_ignores_flag_off(monkeypatch):
    monkeypatch.setenv("PLANNING_COLLAB_V1", "0")
    agent = get_agent("scheduling")
    assert agent.__class__.__name__ == "SchedulingCollabBridge"


def test_bridge_run_calls_collab(monkeypatch):
    def fake_collab(**kwargs):
        assert kwargs["user_goal"] == "保证A按期"
        return {
            "status": "COMPLETED",
            "run_id": "p1",
            "package": {"recommended_schedule_id": "edd"},
            "artifacts": {
                "order_analysis": {"critical_orders": ["A"]},
                "constraint_analysis": {},
                "resource_analysis": {},
            },
        }

    monkeypatch.setattr(
        "metaforge.agents.scheduling_collab_bridge.run_collab", fake_collab
    )
    agent = get_agent("scheduling")
    resp = agent.run(
        AgentRequest(
            message="保证A按期",
            params={"jobs": [{"job_id": "A"}], "machines": ["0"]},
        )
    )
    assert resp.status == "success"
    assert resp.plan_planner == "planning_collab"
    assert resp.artifacts["package"]["recommended_schedule_id"] == "edd"
    assert agent.build_plan(AgentRequest(message="x"))[0].tool == "planning.collab.run"
