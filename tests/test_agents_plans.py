"""plans Agent 测试（collab 主路径）。"""

from metaforge.agents.base import AgentRequest
from metaforge.agents.plans_collab_bridge import PlansCollabBridge
from metaforge.orchestrator.router import get_agent
from metaforge.plans.intent import parse_plan_intent
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def test_parse_plan_intent_create():
    p = parse_plan_intent("帮我新建计划a")
    assert p["action"] == "create"
    assert p["plan_name"] == "a"


def test_plans_agent_create_plan_steps():
    agent = PlansCollabBridge()
    steps = agent.build_rule_plan(AgentRequest(message="新建计划试产01"))
    assert len(steps) == 1
    assert steps[0].tool == "data.create_plan"
    assert agent._plan_planner == "plans_collab"


def test_plans_agent_list_steps():
    agent = PlansCollabBridge()
    steps = agent.build_rule_plan(AgentRequest(message="列出计划"))
    assert steps[0].tool == "data.list_plans"


def test_get_agent_plans_returns_collab_bridge():
    assert isinstance(get_agent("plans"), PlansCollabBridge)
