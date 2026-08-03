from metaforge.agents.base import AgentRequest
from metaforge.tools.base import ToolContext, ToolResult
from metaforge.whatif_collab.pipeline import run_whatif
from metaforge.whatif_collab.plan_steps import build_variants_from_params
from metaforge.whatif_collab.trace import build_whatif_trace


def test_build_whatif_trace_minimal():
    tr = build_whatif_trace(status="success", stages=["compare"], recommend_metric="best_score")
    assert tr["recommend_metric"] == "best_score"


def test_build_variants_default_two_strategies():
    req = AgentRequest(params={"solvers": ["spt"]})
    variants = build_variants_from_params(req)
    assert len(variants) >= 2
    assert variants[0]["scheduling"]["solvers"] == ["spt"]


def test_run_whatif_scripted_compare():
    def invoke(name, params, ctx: ToolContext):
        assert name == "compare.variants"
        assert len(params.get("variants") or []) >= 2
        return ToolResult(
            ok=True,
            data={
                "recommendation": "delivery",
                "recommendation_reason_zh": "交期更优",
                "variants": [],
            },
            artifacts_key="what_if",
        )

    out = run_whatif(
        message="对比一下交期和产能",
        params={"solvers": ["spt"], "strategy_ids": ["delivery", "throughput"]},
        invoke_tool=invoke,
    )
    assert out["status"] == "success"
    assert out["whatif_trace"]["stages"] == ["compare"]
    assert "交期更优" in out["summary_zh"]
