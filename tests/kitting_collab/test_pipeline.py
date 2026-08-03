from metaforge.agents.base import AgentRequest
from metaforge.agents.kitting_collab_bridge import KittingCollabBridge
from metaforge.kitting_collab.pipeline import run_kitting
from metaforge.kitting_collab.trace import build_kitting_trace
from metaforge.tools.base import ToolContext, ToolResult
from metaforge.tools.load_all import load_all_tools


def setup_module():
    load_all_tools()


def test_build_kitting_trace_minimal():
    tr = build_kitting_trace(
        status="success",
        stages=["check_static", "build_report"],
        mode="check_only",
        tool_log=[{"tool": "kitting.build_report", "ok": True}],
    )
    assert tr["mode"] == "check_only"
    assert tr["status"] == "success"


def test_check_only_pipeline_with_scripted_tools():
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        scripts = {
            "material.check_static": ToolResult(
                ok=True, data={"ok": True}, artifacts_key="material_static"
            ),
            "material.compute_delays": ToolResult(
                ok=True, data={"delays": []}, artifacts_key="material_delays"
            ),
            "kitting.build_report": ToolResult(
                ok=True,
                data={"can_start_all": True, "recommendation_zh": "物料充足，可开工。"},
                artifacts_key="kitting_report",
            ),
        }
        return scripts[name]

    out = run_kitting(
        message="齐套检查一下",
        params={"mode": "check_only"},
        invoke_tool=invoke,
    )
    assert out["status"] == "success"
    assert calls == [
        "material.check_static",
        "material.compute_delays",
        "kitting.build_report",
    ]
    assert out["kitting_trace"]["mode"] == "check_only"


def test_bridge_skips_llm_plan(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("LLM_PLAN_ENABLED", "1")
    monkeypatch.setenv("LLM_PLAN_AGENTS", "scheduling,kitting")
    agent = KittingCollabBridge()
    steps = agent.build_plan(AgentRequest(message="缺料检查"))
    assert agent._plan_planner == "kitting_collab"
    assert steps[0].tool == "material.check_static"
