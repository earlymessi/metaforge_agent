from metaforge.tools.base import ToolContext
from metaforge.tools.load_all import load_all_tools
from metaforge.tools.registry import get_tool, list_tools, run_tool


def test_planning_tools_registered():
    load_all_tools()
    names = {t["name"] for t in list_tools()}
    assert "planning.strategy_generate" in names
    assert "planning.strategy_validate" in names
    assert "planning.strategy_evaluate" in names
    assert "planning.run" in names
    gen = get_tool("planning.strategy_generate")
    assert getattr(gen, "risk_level", None) == "ask"


def test_planning_run_tool_skip_hitl(monkeypatch):
    load_all_tools()

    def fake_run_planning(**kwargs):
        return {
            "status": "COMPLETED",
            "package": {"recommended_schedule_id": "ts"},
            "run_id": "r1",
        }

    monkeypatch.setattr("metaforge.tools.planning.run.run_planning", fake_run_planning)
    result = run_tool(
        "planning.run",
        {
            "user_goal": "平衡",
            "jobs": [{"job_id": "A"}],
            "machines": ["M01"],
            "skip_strategy_hitl": True,
        },
        ToolContext(),
    )
    assert result.ok
    assert result.data["status"] == "COMPLETED"
    assert result.data["package"]["recommended_schedule_id"] == "ts"
