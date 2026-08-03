from metaforge.plans_collab.pipeline import run_plans
from metaforge.plans_collab.trace import build_plans_trace
from metaforge.tools.base import ToolContext, ToolResult


def test_build_plans_trace_minimal():
    tr = build_plans_trace(
        status="success", stages=["resolve_intent", "list_plans"], action="list"
    )
    assert tr["action"] == "list"


def test_clear_action_no_tools():
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        return ToolResult(ok=True, data={})

    out = run_plans(message="解绑当前计划", invoke_tool=invoke)
    assert out["plans_trace"]["action"] == "clear"
    assert calls == []
    assert out["status"] == "success"
    assert "解除绑定" in out["summary_zh"]


def test_list_plans_scripted():
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        assert name == "data.list_plans"
        summary = [{"plan_name": "演示", "job_count": 2}]
        ctx.artifacts["plan_list"] = summary
        return ToolResult(
            ok=True,
            data={"plans": summary, "count": 1},
            artifacts_key="plan_list",
        )

    out = run_plans(message="列出计划", invoke_tool=invoke)
    assert out["status"] == "success"
    assert calls == ["data.list_plans"]
    assert "演示" in out["summary_zh"]
    assert out["plans_trace"]["action"] == "list"
