"""scheduling Agent 测试。"""

from metaforge.agents.scheduling import SchedulingAgentRunner
from metaforge.agents.base import AgentRequest
from metaforge.problems.jobshop import Job, JobShopProblem, Task
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def test_scheduling_agent_parse_only_plan():
    agent = SchedulingAgentRunner()
    req = AgentRequest(
        message="禁忌搜索，交付优先",
        params={"skip_parse": False},
    )
    steps = agent.build_plan(req)
    assert len(steps) == 2
    assert steps[0].tool == "scheduling.parse_intent"


def test_scheduling_agent_run_with_problem():
    jobs = [Job(tasks=[Task(machine_id=0, duration=2, id=0)], id=0)]
    problem = JobShopProblem(jobs, instance_name="agent")
    agent = SchedulingAgentRunner()
    req = AgentRequest(
        params={"skip_parse": True, "solvers": ["spt"]},
        context={
            "extras": {"problem": problem},
        },
    )
    resp = agent.run(req)
    assert resp.status == "success"
    assert "spt" in resp.artifacts.get("schedule_results", {})
