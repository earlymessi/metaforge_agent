"""智能排程 Agent 解析测试。"""

from metaforge.agent.scheduling_agent import SchedulingAgent, fast_compare_solvers
from metaforge.scheduling.intent_types import RL_EXCLUDED_FAMILIES
from metaforge.utils.solver_registry import SOLVER_REGISTRY


def test_agent_parse_tabu_delivery():
    agent = SchedulingAgent()
    intent = agent.parse("用禁忌搜索，交付优先，对工单排程")
    assert "ts" in intent.solvers
    assert intent.strategy_id == "delivery"
    assert intent.enforce_material is True
    assert intent.is_fast_mode is False


def test_agent_parse_compare_mode():
    agent = SchedulingAgent()
    intent = agent.parse("对比一下遗传算法和模拟退火")
    assert "ga" in intent.solvers
    assert "sa" in intent.solvers


def test_agent_parse_benchmark():
    agent = SchedulingAgent()
    intent = agent.parse("跑一下 ft06 算例，吞吐优先")
    assert intent.benchmark_file == "ft06.txt"
    assert intent.strategy_id == "throughput"


def test_agent_capabilities():
    cap = SchedulingAgent.capabilities()
    assert cap["id"] == "scheduling"
    assert cap["endpoint"] == "/api/agent/schedule"


def test_agent_route_registered():
    from main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/agent/schedule" in paths
    assert "/api/agent/info" in paths


def test_agent_parse_fast_compare_non_rl():
    agent = SchedulingAgent()
    intent = agent.parse("快速先出个结果")
    assert intent.is_fast_mode is True
    assert len(intent.solvers) <= 6
    for sid in intent.solvers:
        assert SOLVER_REGISTRY[sid].family not in RL_EXCLUDED_FAMILIES
    assert "spt" in intent.solvers


def test_agent_parse_ga_fast_keeps_ga():
    agent = SchedulingAgent()
    intent = agent.parse("用遗传算法快速排一下")
    assert intent.solvers == ["ga"]
    assert intent.is_fast_mode is True
    assert intent.strategy_id == "balanced"
    assert intent.weights["makespan"] > 1.0


def test_fast_compare_solvers_order():
    solvers = fast_compare_solvers()
    assert len(solvers) <= 6
    families = [SOLVER_REGISTRY[s].family for s in solvers]
    assert families.index("rule") < families.index("metaheuristic")

