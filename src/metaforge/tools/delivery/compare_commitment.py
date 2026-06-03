"""delivery.compare_commitment — 重排前后交期承诺对比。"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_RISK_ORDER = {"on_time": 0, "low": 1, "medium": 2, "high": 3, "critical": 4, "unknown": 5}


def _risk_level(p: Dict[str, Any]) -> str:
    return str(p.get("risk_level") or "unknown")


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    impact = params.get("impact_report") or (ctx.artifacts or {}).get("impact_report")
    if not impact:
        return ToolResult(ok=False, error="impact_report required")

    changes: List[Dict[str, Any]] = list(impact.get("commitment_changes") or [])
    worsened = [c for c in changes if float(c.get("delta", 0)) > 0.1]
    improved = [c for c in changes if float(c.get("delta", 0)) < -0.1]

    before_levels = [_risk_level(c) for c in changes if c.get("old_risk_level")]
    after_levels = [_risk_level(c) for c in changes if c.get("new_risk_level")]

    def _count(levels: List[str]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for lv in levels:
            out[lv] = out.get(lv, 0) + 1
        return out

    summary_parts = [
        f"共 {len(changes)} 条交期记录有变化，",
        f"恶化 {len(worsened)} 条，改善 {len(improved)} 条。",
    ]
    if worsened:
        w = worsened[0]
        summary_parts.append(
            f"典型：{w.get('job_name', '工单')} 风险 {w.get('old_risk_level')} → {w.get('new_risk_level')}。"
        )

    data = {
        "commitment_changes": changes,
        "worsened_count": len(worsened),
        "improved_count": len(improved),
        "before_risk_counts": _count(before_levels),
        "after_risk_counts": _count(after_levels),
        "summary_zh": "".join(summary_parts),
    }
    if ctx.artifacts is not None:
        ctx.artifacts["commitment_comparison"] = data
    return ToolResult(ok=True, data=data, artifacts_key="commitment_comparison")


def register_delivery_compare_commitment_tool() -> None:
    name = "delivery.compare_commitment"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="对比重排前后交期风险与承诺变化",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
