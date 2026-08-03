from metaforge.planning_collab.agents.order import run_order_agent
from metaforge.planning_collab.protocol import AgentTask


def test_order_agent_marks_critical_from_goal():
    task = AgentTask(
        task_id="1",
        agent_id="order",
        objective="分析",
        inputs={
            "user_goal": "优先保证客户A按期",
            "jobs": [
                {"job_id": "A", "customer": "A", "due_date": 10, "priority": 5},
                {"job_id": "B", "due_date": 100, "priority": 1},
            ],
        },
    )
    result = run_order_agent(task)
    assert result.status == "success"
    assert "A" in result.artifacts["critical_orders"]


def test_order_agent_marks_early_due_as_due_risk():
    task = AgentTask(
        task_id="2",
        agent_id="order",
        objective="分析",
        inputs={
            "user_goal": "",
            "jobs": [
                {"job_id": "X", "due_date": 5, "priority": 1},
                {"job_id": "Y", "due_date": 80, "priority": 1},
            ],
        },
    )
    result = run_order_agent(task)
    assert result.status == "success"
    assert "X" in result.artifacts["due_risk_orders"]
    assert "Y" not in result.artifacts["due_risk_orders"]


def test_order_agent_boosts_high_priority():
    task = AgentTask(
        task_id="3",
        agent_id="order",
        objective="分析",
        inputs={
            "user_goal": "",
            "jobs": [
                {"job_id": "P", "due_date": 50, "priority": 9},
                {"job_id": "Q", "due_date": 50, "priority": 2},
            ],
        },
    )
    result = run_order_agent(task)
    assert result.status == "success"
    assert "P" in result.artifacts["priority_adjustments"]
    assert result.reasoning_summary is None
