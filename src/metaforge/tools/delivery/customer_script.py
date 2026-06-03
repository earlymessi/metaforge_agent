"""delivery.customer_script — 对外交期说明话术。"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    assessment = params.get("delivery_assessment") or (ctx.artifacts or {}).get("delivery_assessment")
    if not assessment:
        return ToolResult(ok=False, error="delivery_assessment required")

    jobs: List[Dict[str, Any]] = assessment.get("jobs") or []
    late = [j for j in jobs if j.get("risk_level") in ("high", "critical", "medium")]
    if not late:
        script = (
            "尊敬的客户，根据当前生产计划，您的订单可按承诺交期交付。"
            f"（{assessment.get('summary_zh', '')}）"
        )
    else:
        parts = []
        for j in late[:5]:
            name = j.get("job_name", "订单")
            pred = j.get("predicted_completion")
            due = j.get("due_date")
            parts.append(f"{name}预计{pred:.0f}完成" + (f"（交期{due:.0f}）" if due else ""))
        script = "尊敬的客户，" + "；".join(parts) + "。我们正在协调产能，将尽快同步最新承诺。"

    data = {"customer_script": script}
    if ctx.artifacts is not None:
        ctx.artifacts["customer_script"] = script
    return ToolResult(ok=True, data=data, artifacts_key="customer_script")


def register_delivery_customer_script_tool() -> None:
    name = "delivery.customer_script"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="基于交期评估生成对客户说明话术",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
