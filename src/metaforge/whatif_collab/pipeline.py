from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import AgentRequest
from metaforge.tools.base import ToolContext, ToolResult
from metaforge.whatif_collab.plan_steps import build_variants_from_params
from metaforge.whatif_collab.trace import build_whatif_trace

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


def run_whatif(
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

    metric = params.get("recommend_metric", "best_score")
    stages: List[str] = ["compare"]
    tool_log: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []
    warnings: List[str] = []

    req = AgentRequest(message=message, params=params, context=context)
    variants = build_variants_from_params(req)
    result = invoke(
        "compare.variants",
        {"variants": variants, "recommend_metric": metric},
        tool_ctx,
    )
    entry = {"tool": "compare.variants", "ok": bool(result.ok), "optional": False}
    if result.ok:
        _merge_tool_data(tool_ctx, result)
        plan.append(
            {"step_id": "s1", "tool": "compare.variants", "status": "completed"}
        )
    else:
        entry["error"] = result.error
        plan.append(
            {"step_id": "s1", "tool": "compare.variants", "status": "failed"}
        )
    tool_log.append(entry)

    what_if = tool_ctx.artifacts.get("what_if") or {}
    status = "success" if result.ok else "failed"
    summary = what_if.get("recommendation_reason_zh") or (
        result.error or "方案对比完成。"
    )
    if what_if.get("insignificant_diff"):
        summary = (summary or "") + "（方案差异不显著，可任选其一。）"

    trace = build_whatif_trace(
        status=status,
        stages=stages,
        recommend_metric=metric,
        tool_log=tool_log,
        warnings=warnings,
    )
    tool_ctx.artifacts["whatif_trace"] = trace
    out = {
        "status": status,
        "summary_zh": summary,
        "artifacts": dict(tool_ctx.artifacts),
        "plan": plan,
        "whatif_trace": trace,
    }
    if not result.ok:
        out["error"] = result.error
    return out
