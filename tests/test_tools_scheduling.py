"""scheduling Tool 测试。"""

from metaforge.problems.jobshop import Job, JobShopProblem, Task
from metaforge.tools.base import ToolContext
from metaforge.tools.load_all import load_all_tools
from metaforge.tools.registry import list_tools, run_tool


def setup_module():
    load_all_tools()


def test_scheduling_parse_intent_registered():
    names = {t["name"] for t in list_tools()}
    assert "scheduling.parse_intent" in names
    assert "scheduling.run" in names


def test_scheduling_parse_intent_tabu_delivery():
    ctx = ToolContext()
    r = run_tool(
        "scheduling.parse_intent",
        {"message": "禁忌搜索，交付优先"},
        ctx,
    )
    assert r.ok, r.error
    assert "ts" in r.data["solvers"]
    assert r.data["strategy_id"] == "delivery"
    assert ctx.artifacts.get("interpretation") is not None


def test_scheduling_run_spt():
    jobs = [Job(tasks=[Task(machine_id=0, duration=3, id=0)], id=0)]
    problem = JobShopProblem(jobs, instance_name="t")
    ctx = ToolContext(
        extras={"problem": problem},
    )
    r = run_tool(
        "scheduling.run",
        {
            "solvers": ["spt"],
            "weights": {
                "makespan": 1.0,
                "weighted_tardiness_total": 0.5,
                "energy_cost": 0.0,
                "machine_busy_cv": 5.0,
            },
        },
        ctx,
    )
    assert r.ok, r.error
    assert "spt" in r.data["results"]
    assert r.data["results"]["spt"]["gantt_data"]
    assert "schedule_results" in ctx.artifacts
