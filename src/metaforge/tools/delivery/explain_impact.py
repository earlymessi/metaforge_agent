"""delivery.explain_impact — 解读重排影响报告。"""

from __future__ import annotations

from typing import Any, Dict

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    impact = params.get("impact_report") or (ctx.artifacts or {}).get("impact_report")
    if not impact:
        return ToolResult(ok=False, error="impact_report required")

    et = impact.get("event_type") or impact.get("mode") or "reschedule"
    scenarios = impact.get("scenarios") or {}
    lines: list[str] = []

    if et == "insert_order" and scenarios:
        ins = impact.get("insert_job_name") or "插单"
        ft = float(impact.get("freeze_time") or 0)
        lines.append(f"{ins}：{ft:.0f}小时后插入，模式 {impact.get('mode', 'local_repair')}。")
        r0, r1, r2 = scenarios.get("r0", {}), scenarios.get("r1", {}), scenarios.get("r2", {})
        lines.append(
            f"原计划(R0) makespan={r0.get('makespan', 0):.1f}；"
            f"仅往后排(R1)={r1.get('makespan', 0):.1f}；"
            f"重排(R2)={r2.get('makespan', 0):.1f}。"
        )
        imp = impact.get("improvement_vs_r1") or {}
        if float(imp.get("makespan_delta", 0)) < -1e-6:
            lines.append(
                f"相对仅往后排，完工缩短 {abs(float(imp['makespan_delta'])):.1f}h。"
            )
        dd = impact.get("delay_details") or []
        if dd:
            top = dd[0]
            lines.append(
                f"受影响最大：{top.get('job_name', '工单')} "
                f"{top.get('old_completion')}→{top.get('new_completion')}h。"
            )
    elif et == "machine_breakdown" and scenarios:
        label = impact.get("machine_label_zh") or f"{int(impact.get('machine_id', 0)) + 1}号机"
        lines.append(
            f"{label}故障 {impact.get('breakdown_start', 0):.1f}–{impact.get('breakdown_end', 0):.1f}h"
            f"（冻结时刻 {impact.get('freeze_time', 0):.1f}h）。"
        )
        r0, r1, r2 = scenarios.get("r0", {}), scenarios.get("r1", {}), scenarios.get("r2", {})
        lines.append(
            f"原计划(R0) makespan={r0.get('makespan', 0):.1f}；"
            f"不重排(R1)={r1.get('makespan', 0):.1f}；"
            f"重排(R2,{impact.get('baseline_solver', '')})={r2.get('makespan', 0):.1f}。"
        )
        imp = impact.get("improvement_vs_r1") or {}
        if float(imp.get("makespan_delta", 0)) < -1e-6:
            lines.append(
                f"相对不重排，完工缩短 {abs(float(imp['makespan_delta'])):.1f}h。"
            )
        elif impact.get("warning"):
            lines.append(
                impact.get("warning_zh")
                or "注意：重排未优于故障推演，请核对冻结时刻是否与 MES 仿真一致。"
            )
    else:
        affected = impact.get("affected_jobs", 0)
        max_delay = impact.get("max_delay", 0)
        lines.append(f"事件类型：{et}。")
        lines.append(f"受影响工单数：{affected}，最大完工推迟：{max_delay:.1f}。")
        changes = impact.get("commitment_changes") or []
        worsened = [c for c in changes if float(c.get("delta", 0)) > 0.1]
        if worsened:
            top = worsened[0]
            lines.append(
                f"交期承诺变化：{top.get('job_name', '工单')} 预计完工 "
                f"{top.get('old_completion')} → {top.get('new_completion')}。"
            )
    summary_zh = "".join(lines)
    data = {"summary_zh": summary_zh, "impact_report": impact}
    if ctx.artifacts is not None:
        ctx.artifacts["impact_summary"] = data
    return ToolResult(ok=True, data=data, artifacts_key="impact_summary")


def register_delivery_explain_impact_tool() -> None:
    name = "delivery.explain_impact"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="将 impact_report 转为车间可读摘要",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
