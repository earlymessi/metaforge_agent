"""delivery Tool 测试。"""

from metaforge.problems.jobshop import Job, JobShopProblem, Task
from metaforge.tools.base import ToolContext
from metaforge.tools.load_all import load_all_tools
from metaforge.tools.registry import run_tool


def setup_module():
    load_all_tools()


def test_delivery_assess_on_time():
    jobs = [
        Job(
            tasks=[Task(machine_id=0, duration=3, id=0)],
            id=0,
            priority=10,
            due_date=100.0,
        )
    ]
    problem = JobShopProblem(jobs)
    gantt = [{"job_id": 0, "machine_id": 0, "start": 0, "end": 3, "operation_id": 0}]
    ctx = ToolContext(extras={"problem": problem})
    r = run_tool("delivery.assess", {"gantt_data": gantt}, ctx)
    assert r.ok, r.error
    assert r.data["overall"] in ("met", "partial", "unknown")
    assert len(r.data["jobs"]) == 1


def test_delivery_explain_impact():
    ctx = ToolContext()
    impact = {
        "event_type": "machine_breakdown",
        "affected_jobs": 2,
        "max_delay": 3.5,
        "commitment_changes": [
            {
                "job_name": "工单A",
                "old_completion": 10.0,
                "new_completion": 13.5,
                "delta": 3.5,
            }
        ],
    }
    r = run_tool("delivery.explain_impact", {"impact_report": impact}, ctx)
    assert r.ok
    assert "受影响" in r.data["summary_zh"]
