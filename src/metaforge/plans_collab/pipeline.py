from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import AgentRequest
from metaforge.plans_collab.plan_steps import resolve_and_build_plan_steps
from metaforge.plans_collab.trace import build_plans_trace
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
    # list_plans writes summary list on ctx; ToolResult.data is a wrapper dict.
    if key == "plan_list" and isinstance(result.data, dict) and "plans" in result.data:
        ctx.artifacts["plan_list"] = result.data["plans"]
    else:
        ctx.artifacts[key] = result.data
    if isinstance(result.data, dict) and result.data.get("ui_action"):
        ctx.artifacts["ui_action"] = result.data["ui_action"]


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


def _format_active_plan_summary(active: dict, intent: Optional[dict]) -> str:
    name = active.get("plan_name") or "未命名"
    n = active.get("job_count", 0)
    parts = [f"计划「{name}」", f"{n} 个工单"]
    st = active.get("plan_status")
    if st:
        st_zh = {
            "pending": "待排程",
            "done": "已完成",
            "scheduled": "已排程",
            "archived": "已归档",
        }.get(st, st)
        parts.append(f"状态：{st_zh}")
    if active.get("has_schedule"):
        parts.append("已有排程快照")
    action = (intent or {}).get("action")
    nav_tail = "。正在打开排程中心，可说「按交期优先排产」继续。"
    if action == "view":
        head = "已找到并绑定：" if n else "已找到计划（暂无工单）："
        return head + "，".join(parts) + nav_tail
    if action in ("create", "bind", "rename", "duplicate", "update_status"):
        verb = {
            "create": "已新建",
            "bind": "已加载",
            "rename": "已重命名",
            "duplicate": "已复制",
            "update_status": "已更新状态",
        }.get(action, "已处理")
        return verb + " " + "，".join(parts) + nav_tail
    return "已处理 " + "，".join(parts) + "。"


def _build_summary(tool_ctx: ToolContext, intent: Optional[dict]) -> str:
    if intent and intent.get("action") == "clear":
        return "已请求解除绑定（请在前端清除当前计划选择）。"
    active = (tool_ctx.artifacts or {}).get("active_plan")
    plan_list = (tool_ctx.artifacts or {}).get("plan_list")
    if active:
        return _format_active_plan_summary(active, intent)
    if plan_list is not None:
        if not plan_list:
            return "数据库中暂无计划。可说「新建计划叫 XXX」创建。"
        lines = [
            f"· {p.get('plan_name')}（{p.get('job_count', 0)} 工单）"
            for p in plan_list[:12]
        ]
        extra = f"\n共 {len(plan_list)} 条。" if len(plan_list) > 12 else ""
        return "计划列表：\n" + "\n".join(lines) + extra
    return "计划管理操作已完成。"


def run_plans(
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

    req = AgentRequest(message=message, params=params, context=context)
    steps, intent, intent_planner = resolve_and_build_plan_steps(req)
    action = (intent or {}).get("action")

    stages: List[str] = ["resolve_intent"]
    tool_log: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def finish(status: str, summary_zh: str, **extra) -> dict:
        ui = tool_ctx.artifacts.get("ui_action")
        if action == "goto_aps" and not ui:
            tool_ctx.artifacts["ui_action"] = {
                "type": "navigate",
                "path": "/aps",
                "reason": "打开排程",
            }
            ui = tool_ctx.artifacts["ui_action"]
        trace = build_plans_trace(
            status=status,
            stages=stages,
            action=action,
            intent_planner=intent_planner,
            tool_log=tool_log,
            warnings=warnings,
        )
        tool_ctx.artifacts["plans_trace"] = trace
        out = {
            "status": status,
            "summary_zh": summary_zh,
            "artifacts": dict(tool_ctx.artifacts),
            "plan": plan,
            "plans_trace": trace,
            "ui_action": ui,
        }
        out.update(extra)
        return out

    if action == "clear":
        stages.append("clear")
        return finish("success", _build_summary(tool_ctx, intent))

    if not steps:
        stages.append("noop")
        return finish("success", _build_summary(tool_ctx, intent))

    for step in steps:
        stages.append(step.tool.split(".")[-1] if step.tool else "step")
        result = invoke(step.tool, dict(step.params or {}), tool_ctx)
        entry = {
            "tool": step.tool,
            "ok": bool(result.ok),
            "optional": bool(step.optional),
        }
        if result.ok:
            _merge_tool_data(tool_ctx, result)
            plan.append(
                {
                    "step_id": step.step_id,
                    "tool": step.tool,
                    "status": "completed",
                }
            )
        else:
            entry["error"] = result.error
            plan.append(
                {
                    "step_id": step.step_id,
                    "tool": step.tool,
                    "status": "skipped" if step.optional else "failed",
                }
            )
            if not step.optional:
                tool_log.append(entry)
                return finish(
                    "failed",
                    result.error or f"{step.tool} 失败",
                    error=result.error,
                )
            warnings.append(f"{step.tool}: {result.error or 'failed'}")
        tool_log.append(entry)

    return finish("success", _build_summary(tool_ctx, intent))
