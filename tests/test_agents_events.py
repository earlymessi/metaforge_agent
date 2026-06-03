"""events Agent 测试。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.events import EventsAgentRunner
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


def test_events_default_reschedule_uses_rule_plan_without_llm(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PLAN_ENABLED", "1")
    agent = EventsAgentRunner()
    req = AgentRequest(message="3号机坏了4小时，帮我重排")
    steps, planner = agent.build_plan_with_planner(req)
    assert planner == "rule"
    assert [s.tool for s in steps][1] == "events.parse_event"


def test_events_build_plan_merge_when_insert_pending():
    agent = EventsAgentRunner()
    req = AgentRequest(
        message="2道工序：3号机5h + 4号机3h",
        context={
            "artifacts": {
                "insert_job_intake": {
                    "status": "need_input",
                    "draft": {"name": "急单", "priority": 100, "tasks": []},
                },
                "event_envelope": {
                    "event_type": "insert_order",
                    "params": {"freeze_time": 20.0, "insert_job": {"name": "急单", "tasks": []}},
                },
            }
        },
    )
    steps = agent.build_plan(req)
    tools = [s.tool for s in steps]
    assert tools[0] == "events.merge_insert_job"
    assert "events.parse_event" not in tools
    assert getattr(agent, "_plan_planner", "") == "rule"


def test_events_agent_plan_has_reschedule_chain():
    agent = EventsAgentRunner()
    req = AgentRequest(message="工单A优先级调高")
    steps = agent.build_plan(req)
    tools = [s.tool for s in steps]
    assert "events.parse_event" in tools
    assert "events.reschedule" in tools
    assert "delivery.explain_impact" in tools


def test_events_agent_run_skip_parse():
    agent = EventsAgentRunner()
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
    impact = resp.artifacts.get("impact_report", {})
    assert "delay_details" in impact
    assert "commitment_changes" in impact
