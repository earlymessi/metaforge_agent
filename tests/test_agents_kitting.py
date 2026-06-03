"""kitting Agent 测试。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.kitting import KittingAgentRunner
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def _jobs_with_bom():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "bom": [{"material_id": "MAT_A", "quantity_per_unit": 1.0, "consume_mode": "job_start"}],
            "tasks": [{"machine_id": 0, "duration": 2}],
        }
    ]


def test_kitting_agent_check_only_plan():
    agent = KittingAgentRunner()
    req = AgentRequest(params={"mode": "check_only"})
    steps = agent.build_plan(req)
    assert [s.tool for s in steps] == [
        "material.check_static",
        "material.compute_delays",
        "kitting.build_report",
    ]


def test_kitting_agent_check_only_run():
    agent = KittingAgentRunner()
    req = AgentRequest(
        params={"mode": "check_only"},
        context={
            "custom_data": _jobs_with_bom(),
            "extras": {
                "inventory": {"MAT_A": 100.0},
                "material_names": {"MAT_A": "物料A"},
            },
        },
    )
    resp = agent.run(req)
    assert resp.status == "success"
    assert resp.artifacts.get("kitting_report", {}).get("can_start_all") is True
