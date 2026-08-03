"""scheduling Agent 测试（collab 主路径）。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.scheduling_collab_bridge import SchedulingCollabBridge
from metaforge.orchestrator.router import get_agent


def test_get_agent_scheduling_returns_collab_bridge():
    assert isinstance(get_agent("scheduling"), SchedulingCollabBridge)


def test_scheduling_bridge_build_plan_is_collab_step():
    agent = SchedulingCollabBridge()
    steps = agent.build_plan(AgentRequest(message="禁忌搜索，交付优先"))
    assert agent._plan_planner == "planning_collab"
    assert [s.tool for s in steps] == ["planning.collab.run"]


def test_scheduling_bridge_run_with_jobs(monkeypatch):
    def fake_collab(**kwargs):
        assert kwargs.get("jobs")
        return {
            "status": "COMPLETED",
            "run_id": "r1",
            "package": {"recommended_schedule_id": "spt"},
            "artifacts": {},
        }

    monkeypatch.setattr(
        "metaforge.agents.scheduling_collab_bridge.run_collab", fake_collab
    )
    agent = SchedulingCollabBridge()
    resp = agent.run(
        AgentRequest(
            message="综合平衡",
            context={
                "custom_data": [
                    {
                        "name": "A",
                        "tasks": [{"machine_id": 0, "duration": 2}],
                    }
                ]
            },
        )
    )
    assert resp.status == "success"
    assert resp.plan_planner == "planning_collab"
