"""scheduling Agent 排程落库（原 pipeline）测试。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.scheduling import SchedulingAgentRunner
from metaforge.services import persist_store
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def teardown_module():
    persist_store.clear_pending_store()


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 15.0,
            "tasks": [{"machine_id": 0, "duration": 2}, {"machine_id": 1, "duration": 2}],
        },
    ]


def test_scheduling_persist_pending_confirm():
    persist_store.clear_pending_store()
    agent = SchedulingAgentRunner()
    req = AgentRequest(
        message="排程并落库",
        params={"solvers": ["spt"], "persist_after": True},
        context={
            "custom_data": _jobs(),
            "extras": {
                "loaded_plan_id": "507f1f77bcf86cd799439011",
                "plan_name": "单元测试计划",
            },
        },
    )
    resp = agent.run(req)
    assert resp.status == "pending_confirm"
    assert resp.pending_action.get("confirm_token")
    assert resp.artifacts.get("pending_persist")
