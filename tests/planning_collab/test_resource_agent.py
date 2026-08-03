from metaforge.planning_collab.agents.resource import run_resource_agent
from metaforge.planning_collab.protocol import AgentTask


def test_resource_agent_marks_bottleneck():
    task = AgentTask(
        task_id="1",
        agent_id="resource",
        objective="分析资源",
        inputs={
            "jobs": [
                {
                    "job_id": "A",
                    "tasks": [
                        {"machine_id": 0, "duration": 5},
                        {"machine_id": 1, "duration": 1},
                    ],
                },
                {
                    "job_id": "B",
                    "tasks": [{"machine_id": 0, "duration": 4}],
                },
            ],
            "machines": ["0", "1"],
        },
    )
    result = run_resource_agent(task)
    assert result.status == "success"
    load = result.artifacts["machine_load"]
    assert load["0"] == 9
    assert load["1"] == 1
    assert "0" in result.artifacts["bottleneck_machines"]
    assert result.reasoning_summary is None


def test_resource_agent_empty_without_tasks():
    task = AgentTask(
        task_id="2",
        agent_id="resource",
        objective="分析资源",
        inputs={"jobs": [{"job_id": "A"}]},
    )
    result = run_resource_agent(task)
    assert result.status == "success"
    assert result.artifacts["machine_load"] == {}
    assert result.artifacts["bottleneck_machines"] == []
    assert result.warnings
