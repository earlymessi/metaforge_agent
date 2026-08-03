from metaforge.planning_collab.protocol import AgentTask, AgentResult, PlanningTaskState


def test_task_state_roundtrip():
    state = PlanningTaskState.new(user_goal="保证A按期", jobs=[{"job_id": "A"}])
    d = state.to_dict()
    assert d["user_goal"] == "保证A按期"
    assert "artifacts" in d
    task = AgentTask(task_id="t1", agent_id="order", objective="分析订单", inputs={"jobs": []})
    assert task.agent_id == "order"
    res = AgentResult(agent_id="order", status="success", summary="ok", artifacts={"critical_orders": ["A"]})
    assert res.artifacts["critical_orders"] == ["A"]
