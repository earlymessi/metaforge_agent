"""AgentRuntime + RunEvent basics."""

from __future__ import annotations

from metaforge.harness.runtime import AgentRuntime
from metaforge.planning_collab.protocol import AgentResult, AgentTask


def test_run_agent_emits_start_and_end_events():
    runtime = AgentRuntime()

    def ok_runner(task: AgentTask) -> AgentResult:
        return AgentResult(
            agent_id=task.agent_id,
            status="success",
            summary="done",
            artifacts={"n": 1},
        )

    task = AgentTask(
        task_id="t1",
        agent_id="order",
        objective="分析订单",
        inputs={"jobs": []},
    )
    result = runtime.run_agent(task, ok_runner)
    assert result.status == "success"
    assert result.artifacts["n"] == 1

    events = runtime.events
    types = [e.type for e in events]
    assert "agent.start" in types
    assert "agent.end" in types
    assert any(e.agent_id == "order" for e in events)


def test_run_agent_captures_exception_as_failed():
    runtime = AgentRuntime()

    def boom(_task: AgentTask) -> AgentResult:
        raise RuntimeError("agent exploded")

    task = AgentTask(
        task_id="t2",
        agent_id="constraint",
        objective="约束",
        inputs={},
    )
    result = runtime.run_agent(task, boom)
    assert result.status == "failed"
    assert "exploded" in (result.summary or "")
    assert any(e.type == "agent.error" for e in runtime.events)
