"""whatif Agent 测试。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.whatif import WhatifAgentRunner
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def _jobs():
    return [
        {
            "name": "工单A",
            "priority": 10,
            "due_date": 18.0,
            "tasks": [{"machine_id": 0, "duration": 2}, {"machine_id": 1, "duration": 2}],
        },
    ]


def test_whatif_agent_default_strategies():
    agent = WhatifAgentRunner()
    req = AgentRequest(
        params={"solvers": ["spt"], "strategy_ids": ["delivery", "throughput"]},
        context={"custom_data": _jobs()},
    )
    resp = agent.run(req)
    assert resp.status == "success"
    assert resp.artifacts.get("what_if", {}).get("recommendation")
