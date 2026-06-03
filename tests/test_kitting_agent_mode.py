from metaforge.agents.base import AgentRequest
from metaforge.agents.kitting import KittingAgentRunner


def test_kitting_default_mode_check_only_for_shortage_question():
    agent = KittingAgentRunner()
    req = AgentRequest(message="缺料会导致哪些工单延期？", params={}, context={})
    _ = agent.build_plan(req)
    assert req.params.get("mode") == "check_only"


def test_kitting_mode_schedule_then_predict_when_explicit_predict_wording():
    agent = KittingAgentRunner()
    req = AgentRequest(message="先排程再预测物料风险", params={}, context={})
    _ = agent.build_plan(req)
    assert req.params.get("mode") == "schedule_then_predict"
