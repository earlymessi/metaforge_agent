from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.kitting_collab.plan_steps import resolve_kitting_mode
from metaforge.kitting_collab.trace import build_kitting_trace
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


def run_kitting(
    *,
    message: str = "",
    context: dict | None = None,
    params: dict | None = None,
    invoke_tool: InvokeTool | None = None,
) -> dict:
    """
    Fixed-stage kitting orchestration.

    Returns status/summary_zh/artifacts/plan; artifacts always include kitting_trace.
    """
    context = dict(context or {})
    params = dict(params or {})
    mode = resolve_kitting_mode(message, params)
    params["mode"] = mode
    invoke = invoke_tool or _default_invoke
    tool_ctx = _tool_context_from(context, params)
    if message and "message" not in tool_ctx.extras:
        tool_ctx.extras["message"] = message

    stages: List[str] = []
    tool_log: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def finish(status: str, summary_zh: str, **extra) -> dict:
        trace = build_kitting_trace(
            status=status,
            stages=stages,
            mode=mode,
            tool_log=tool_log,
            warnings=warnings,
        )
        tool_ctx.artifacts["kitting_trace"] = trace
        out = {
            "status": status,
            "summary_zh": summary_zh,
            "artifacts": dict(tool_ctx.artifacts),
            "plan": plan,
            "kitting_trace": trace,
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

    if mode == "check_only":
        early = run_step("s1", "material.check_static", "check_static")
        if early:
            return early
        early = run_step(
            "s2", "material.compute_delays", "compute_delays", optional=True
        )
        if early:
            return early
        early = run_step("s3", "kitting.build_report", "build_report")
        if early:
            return early
    elif mode == "schedule_then_predict":
        solvers = params.get("solvers") or ["spt"]
        early = run_step(
            "s1", "scheduling.run", "schedule", {"solvers": solvers}
        )
        if early:
            return early
        early = run_step("s2", "material.predict", "predict")
        if early:
            return early
        early = run_step("s3", "kitting.build_report", "build_report")
        if early:
            return early
    else:
        # kit_then_schedule
        early = run_step("s1", "material.check_static", "check_static")
        if early:
            return early
        early = run_step(
            "s2", "material.compute_delays", "compute_delays", optional=True
        )
        if early:
            return early
        solvers = params.get("solvers") or ["spt", "ts"]
        early = run_step(
            "s3", "scheduling.run", "schedule", {"solvers": solvers}
        )
        if early:
            return early
        early = run_step("s4", "material.predict", "predict", optional=True)
        if early:
            return early
        early = run_step("s5", "kitting.build_report", "build_report")
        if early:
            return early

    kr = tool_ctx.artifacts.get("kitting_report") or {}
    summary = kr.get("recommendation_zh") or "齐套检查完成。"
    return finish("success", summary)
