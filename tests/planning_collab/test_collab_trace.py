from metaforge.planning_collab.protocol import AgentResult
from metaforge.planning_collab.trace import build_collab_trace


def test_build_collab_trace_includes_agents_and_strategy():
    results = {
        "order": AgentResult(
            agent_id="order",
            status="success",
            summary="订单分析: critical=1",
            artifacts={"critical_orders": ["A"]},
            reasoning_summary=None,
        ),
        "constraint": AgentResult(
            agent_id="constraint",
            status="success",
            summary="约束分析",
            artifacts={"hard_constraints": []},
        ),
        "resource": AgentResult(
            agent_id="resource",
            status="success",
            summary="资源分析",
            artifacts={"bottleneck_machines": ["0"]},
        ),
    }
    planning = {
        "run_id": "p1",
        "status": "COMPLETED",
        "stages": ["generate", "validate", "solve", "evaluate"],
        "strategy_approved": {"generated_by": "rule_fallback"},
        "solver_policy": {"primary_solvers": ["edd"], "fallback_solver": "spt"},
        "evaluation": {"recommended_schedule_id": "edd"},
        "package": {"recommended_schedule_id": "edd"},
        "warnings": [],
    }
    trace = build_collab_trace(
        collab_run_id="c1",
        stage="done",
        status="COMPLETED",
        agent_results=results,
        planning_run=planning,
    )
    assert trace["type"] == "collab_trace"
    assert [a["agent_id"] for a in trace["agents"]] == [
        "order",
        "constraint",
        "resource",
    ]
    assert trace["strategy_trace"]["recommended_schedule_id"] == "edd"
