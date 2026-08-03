from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.commitment_collab.plan_steps import want_customer_script
from metaforge.commitment_collab.trace import build_commitment_trace
from metaforge.tools.base import ToolContext, ToolResult

InvokeTool = Callable[[str, Dict[str, Any], ToolContext], ToolResult]


def _default_invoke(name: str, params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    from metaforge.tools.load_all import load_all_tools
    from metaforge.tools.registry import run_tool

    load_all_tools()
    return run_tool(name, params or {}, ctx)


def _merge_tool_data(ctx: ToolContext, result: ToolResult) -> None:
    if not result.ok or result.data is None:
        return
    key = result.artifacts_key
    if not key:
        if isinstance(result.data, dict):
            ctx.artifacts.update(result.data)
        return
    if key == "schedule_results" and isinstance(result.data, dict):
        rd = result.data
        if isinstance(rd.get("results"), dict):
            ctx.artifacts["schedule_results"] = rd["results"]
        for k in ("impact_report", "impact_gantt", "updated_jobs", "event_type"):
            if rd.get(k) is not None:
                ctx.artifacts[k] = rd[k]
        return
    ctx.artifacts[key] = result.data


def _tool_context_from(context: Optional[dict], params: Optional[dict]) -> ToolContext:
    ctx = dict(context or {})
    params = dict(params or {})
    return ToolContext(
        custom_data=ctx.get("custom_data"),
        benchmark_file=ctx.get("benchmark_file"),
        plan_id=ctx.get("plan_id"),
        weights=ctx.get("weights") or params.get("weights"),
        enforce_material=bool(ctx.get("enforce_material", False)),
        random_seed=ctx.get("random_seed"),
        artifacts=dict(ctx.get("artifacts") or {}),
        extras=dict(ctx.get("extras") or {}),
    )


def _call(
    invoke: InvokeTool,
    tool: str,
    params: Dict[str, Any],
    ctx: ToolContext,
    *,
    optional: bool = False,
) -> tuple[ToolResult, Dict[str, Any]]:
    result = invoke(tool, params, ctx)
    entry = {"tool": tool, "ok": bool(result.ok), "optional": optional}
    if result.ok:
        _merge_tool_data(ctx, result)
    else:
        entry["error"] = result.error
    return result, entry


def run_commitment(
    *,
    message: str = "",
    context: dict | None = None,
    params: dict | None = None,
    invoke_tool: InvokeTool | None = None,
) -> dict:
    context = dict(context or {})
    params = dict(params or {})
    invoke = invoke_tool or _default_invoke
    tool_ctx = _tool_context_from(context, params)
    if message and "message" not in tool_ctx.extras:
        tool_ctx.extras["message"] = message

    want_script = want_customer_script(message)
    has_schedule = bool(tool_ctx.artifacts.get("schedule_results"))
    stages: List[str] = []
    tool_log: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def finish(status: str, summary_zh: str, **extra) -> dict:
        trace = build_commitment_trace(
            status=status,
            stages=stages,
            want_script=want_script,
            tool_log=tool_log,
            warnings=warnings,
        )
        tool_ctx.artifacts["commitment_trace"] = trace
        out = {
            "status": status,
            "summary_zh": summary_zh,
            "artifacts": dict(tool_ctx.artifacts),
            "plan": plan,
            "commitment_trace": trace,
        }
        out.update(extra)
        return out

    def run_step(
        step_id: str,
        tool: str,
        stage: str,
        p: Optional[Dict[str, Any]] = None,
        *,
        optional: bool = False,
    ) -> Optional[dict]:
        stages.append(stage)
        result, entry = _call(invoke, tool, p or {}, tool_ctx, optional=optional)
        tool_log.append(entry)
        plan.append(
            {
                "step_id": step_id,
                "tool": tool,
                "status": (
                    "completed"
                    if result.ok
                    else ("skipped" if optional else "failed")
                ),
            }
        )
        if not result.ok and not optional:
            return finish("failed", result.error or f"{tool} 失败", error=result.error)
        if not result.ok and optional:
            warnings.append(f"{tool}: {result.error or 'failed'}")
        return None

    if params.get("run_schedule_first") and not has_schedule:
        early = run_step(
            "s0",
            "scheduling.run",
            "schedule",
            {"solvers": params.get("solvers", ["spt"])},
            optional=True,
        )
        if early:
            return early

    early = run_step("s1", "delivery.assess", "assess")
    if early:
        return early

    if want_script:
        early = run_step("s2", "delivery.customer_script", "customer_script")
        if early:
            return early

    da = tool_ctx.artifacts.get("delivery_assessment") or {}
    summary = da.get("summary_zh") or "交期评估完成。"
    script = tool_ctx.artifacts.get("customer_script") or {}
    if isinstance(script, dict) and script.get("script_zh"):
        summary = script.get("summary_zh") or summary
    return finish("success", summary)
