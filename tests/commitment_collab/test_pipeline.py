from metaforge.commitment_collab.pipeline import run_commitment
from metaforge.commitment_collab.trace import build_commitment_trace
from metaforge.tools.base import ToolContext, ToolResult


def test_build_commitment_trace_minimal():
    tr = build_commitment_trace(status="success", stages=["assess"], want_script=False)
    assert tr["status"] == "success"
    assert tr["want_script"] is False


def test_assess_only_no_schedule_when_results_present():
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        return ToolResult(
            ok=True,
            data={"summary_zh": "交期可满足", "overall": "met"},
            artifacts_key="delivery_assessment",
        )

    out = run_commitment(
        message="交期评估一下",
        context={"artifacts": {"schedule_results": {"spt": {}}}},
        invoke_tool=invoke,
    )
    assert out["status"] == "success"
    assert calls == ["delivery.assess"]
    assert out["commitment_trace"]["stages"] == ["assess"]


def test_script_path_calls_customer_script():
    calls = []

    def invoke(name, params, ctx: ToolContext):
        calls.append(name)
        if name == "delivery.assess":
            return ToolResult(
                ok=True,
                data={"summary_zh": "部分延期", "overall": "partial"},
                artifacts_key="delivery_assessment",
            )
        return ToolResult(
            ok=True,
            data={"script_zh": "您好…", "summary_zh": "话术已生成"},
            artifacts_key="customer_script",
        )

    out = run_commitment(message="给客户一段交期说明话术", invoke_tool=invoke)
    assert out["status"] == "success"
    assert calls == ["delivery.assess", "delivery.customer_script"]
    assert out["commitment_trace"]["want_script"] is True
