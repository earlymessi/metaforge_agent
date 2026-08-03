"""scheduling Plan 纠偏单测（不调用 GLM）。"""

from metaforge.agents.base import AgentRequest, PlanStep
from metaforge.scheduling.plan_coerce import coerce_scheduling_plan_steps


def test_coerce_compare_algorithms_from_list_catalog():
    req = AgentRequest(message="对比一下遗传算法和模拟退火")
    steps = coerce_scheduling_plan_steps(
        [PlanStep("s0", "scheduling.list_catalog", {})], req
    )
    tools = [s.tool for s in steps]
    assert "scheduling.parse_intent" in tools
    assert "scheduling.run" in tools


def test_coerce_fast_run_from_clarification():
    req = AgentRequest(message="快速先出个结果")
    steps = coerce_scheduling_plan_steps(
        [PlanStep("s0", "scheduling.ask_clarification", {})], req
    )
    tools = [s.tool for s in steps]
    assert "scheduling.parse_intent" in tools
    assert "scheduling.run" in tools


def test_explicit_schedule_intent_coerces_clarification():
    req = AgentRequest(message="排程", params={"intent": "schedule"})
    steps = coerce_scheduling_plan_steps(
        [PlanStep("s0", "scheduling.ask_clarification", {})], req
    )
    tools = [s.tool for s in steps]
    assert "scheduling.run" in tools


def test_catalog_query_keeps_list_catalog():
    req = AgentRequest(message="有哪些算法可以用？")
    steps = coerce_scheduling_plan_steps(
        [PlanStep("s0", "scheduling.list_catalog", {})], req
    )
    assert steps[0].tool == "scheduling.list_catalog"
