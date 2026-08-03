from metaforge.planning_collab.agents.constraint import run_constraint_agent
from metaforge.planning_collab.protocol import AgentTask


def test_constraint_agent_soft_changeover_from_goal():
    task = AgentTask(
        task_id="1",
        agent_id="constraint",
        objective="分析约束",
        inputs={
            "user_goal": "减少换型，综合平衡",
            "jobs": [{"job_id": "A", "due_date": 10}],
        },
    )
    result = run_constraint_agent(task)
    assert result.status == "success"
    soft_types = [c["type"] for c in result.artifacts["soft_constraints"]]
    assert "reduce_changeover" in soft_types
    assert result.reasoning_summary is None


def test_constraint_agent_order_on_time_from_order_analysis():
    task = AgentTask(
        task_id="2",
        agent_id="constraint",
        objective="分析约束",
        inputs={
            "user_goal": "保证交期",
            "jobs": [{"job_id": "A", "due_date": 10}, {"job_id": "B", "due_date": 20}],
            "order_analysis": {"critical_orders": ["A"]},
        },
    )
    result = run_constraint_agent(task)
    hard = result.artifacts["hard_constraints"]
    assert any(c["type"] == "order_on_time" and c.get("job_id") == "A" for c in hard)


def test_constraint_agent_drops_unknown_types():
    task = AgentTask(
        task_id="3",
        agent_id="constraint",
        objective="分析约束",
        inputs={
            "user_goal": "",
            "jobs": [],
            "proposed_hard": [{"type": "not_a_real_constraint"}],
            "proposed_soft": [{"type": "also_fake"}],
        },
    )
    result = run_constraint_agent(task)
    assert result.artifacts["hard_constraints"] == []
    assert result.artifacts["soft_constraints"] == []
    assert any("not_a_real_constraint" in w for w in result.warnings)
