"""commitment Agent 测试。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.commitment import CommitmentAgentRunner
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 20.0,
            "tasks": [{"machine_id": 0, "duration": 3}, {"machine_id": 1, "duration": 3}],
        },
    ]


def _fake_schedule_results():
    return {
        "spt": {
            "id": "spt",
            "name": "SPT",
            "best_score": 12.0,
            "gantt_data": [
                {"job_id": 0, "job_name": "工单A", "machine_id": 0, "start": 0, "end": 3, "duration": 3},
                {"job_id": 0, "job_name": "工单A", "machine_id": 1, "start": 3, "end": 12, "duration": 3},
            ],
            "metrics": {"makespan": 12.0},
        },
    }


def test_commitment_assess_without_reschedule():
    agent = CommitmentAgentRunner()
    req = AgentRequest(
        message="交期能不能满足客户",
        context={
            "custom_data": _jobs(),
            "artifacts": {"schedule_results": _fake_schedule_results()},
        },
    )
    steps = agent.build_rule_plan(req)
    tool_names = [s.tool for s in steps]
    assert "delivery.assess" in tool_names
    assert "scheduling.run" not in tool_names

    resp = agent.run(req)
    assert resp.status in ("success", "failed")
    assert resp.artifacts.get("delivery_assessment") is not None


def test_commitment_rule_plan_includes_script_when_asked():
    agent = CommitmentAgentRunner()
    steps = agent.build_rule_plan(
        AgentRequest(message="给客户一段交期说明话术", context={"artifacts": {}})
    )
    tools = [s.tool for s in steps]
    assert "delivery.assess" in tools
    assert "delivery.customer_script" in tools
