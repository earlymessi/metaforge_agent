"""plans Agent 测试。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.plans import PlansAgentRunner
from metaforge.plans.intent import parse_plan_intent
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def test_parse_plan_intent_create():
    p = parse_plan_intent("帮我新建计划a")
    assert p["action"] == "create"
    assert p["plan_name"] == "a"


def test_plans_agent_create_plan_steps():
    agent = PlansAgentRunner()
    steps = agent.build_rule_plan(AgentRequest(message="新建计划试产01"))
    assert len(steps) == 1
    assert steps[0].tool == "data.create_plan"


def test_plans_agent_list_steps():
    agent = PlansAgentRunner()
    steps = agent.build_rule_plan(AgentRequest(message="列出计划"))
    assert steps[0].tool == "data.list_plans"
