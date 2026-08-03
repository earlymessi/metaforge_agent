"""Orchestrator 执行轨迹（路由 / 计划 / 步骤），供前端「思考过程」展示。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.agents.base import AgentRequest, PlanStep
from metaforge.agents.registry_meta import AGENT_REGISTRY

_AGENT_NAME: Dict[str, str] = {a["id"]: a["name_zh"] for a in AGENT_REGISTRY}

_INTENT_LABEL: Dict[str, str] = {
    "schedule": "排程",
    "reschedule": "异常重排",
    "kitting": "齐套顾问",
    "commitment": "交期承诺",
    "whatif": "方案对比",
    "plans": "计划管理（增删改查）",
}


def _agent_label(agent_id: str) -> str:
    return _AGENT_NAME.get(agent_id, agent_id)


def build_scope_guidance_trace(route: Dict[str, Any]) -> Dict[str, Any]:
    lines = [
        "问题超出六个业务 Agent 能力范围，已拦截执行",
        f"类别：{route.get('scope_category', 'unknown')}",
    ]
    if route.get("llm_misroute"):
        lines.append(f"原 GLM 误识别 intent：{route['llm_misroute']}")
    if route.get("reason_zh"):
        lines.append(route["reason_zh"])
    guidance = route.get("guidance_zh") or ""
    for part in guidance.split("\n"):
        part = part.strip()
        if part:
            lines.append(part)
    return {
        "phase": "scope",
        "title": "② 能力范围提示",
        "planner": route.get("router") or "scope_block",
        "lines": lines,
        "scope_category": route.get("scope_category"),
    }


def build_route_trace(route: Dict[str, Any]) -> Dict[str, Any]:
    router = route.get("router") or "rule"
    if route.get("out_of_scope"):
        agent_id = None
        intent = route.get("intent") or "unsupported"
        lines: List[str] = ["意图识别后触发能力范围护栏（不进入任何 Agent）"]
        if router in ("llm", "llm_guard"):
            lines[0] = "意图识别（智谱 GLM）→ 能力范围纠正"
            for step in route.get("reasoning_steps") or []:
                lines.append(f"· {step}")
        if route.get("llm_misroute"):
            lines.append(f"原 GLM intent：{route['llm_misroute']}")
        if route.get("reason_zh"):
            lines.append(f"结论：{route['reason_zh']}")
        lines.append(f"识别 intent：超出范围（{intent}）")
        lines.append("未选中业务 Agent（问题已拦截）")
        build_id = route.get("router_build_id")
        if build_id:
            lines.append(f"路由版本：{build_id}")
        return {
            "phase": "route",
            "title": "① 意图路由",
            "planner": router,
            "lines": lines,
            "agent_id": agent_id,
            "intent": intent,
            "out_of_scope": True,
            "scope_category": route.get("scope_category"),
        }

    agent_id = route.get("agent_id") or "scheduling"
    intent = route.get("intent")
    lines: List[str] = []

    if router == "explicit" and intent:
        lines.append(f"用户指定意图：{_INTENT_LABEL.get(intent, intent)}（{intent}）")
    elif router in ("llm", "llm_guard"):
        lines.append("意图识别（智谱 GLM）")
        for step in route.get("reasoning_steps") or []:
            lines.append(f"· {step}")
        if route.get("reason_zh"):
            lines.append(f"结论：{route['reason_zh']}")
        if intent:
            lines.append(f"识别 intent：{_INTENT_LABEL.get(intent, intent)}（{intent}）")
    elif router == "rule_override":
        lines.append("GLM 路由已纠正（计划库话术不得进入排程 Agent）")
        if route.get("reason_zh"):
            lines.append(route["reason_zh"])
        if route.get("llm_misroute"):
            lines.append(f"原 GLM intent：{route['llm_misroute']}")
        if intent:
            lines.append(f"纠正为：{_INTENT_LABEL.get(intent, intent)}（{intent}）")
    elif router == "rule_fallback":
        lines.append("GLM 路由失败，回退规则关键词匹配")
        if route.get("llm_error"):
            lines.append(f"原因：{str(route['llm_error'])[:200]}")
        if route.get("rule_reason_zh"):
            lines.append(route["rule_reason_zh"])
    else:
        lines.append("规则匹配（计划库/离线回退，未调用 GLM 路由）")
        if route.get("rule_reason_zh"):
            lines.append(route["rule_reason_zh"])

    lines.append(f"选中 Agent：{_agent_label(agent_id)}（{agent_id}）")
    build_id = route.get("router_build_id")
    if build_id:
        lines.append(f"路由版本：{build_id}")

    return {
        "phase": "route",
        "title": "① 意图路由",
        "planner": router,
        "lines": lines,
        "agent_id": agent_id,
        "intent": intent,
    }


def build_plan_trace(
    agent_id: str,
    steps: List[PlanStep],
    *,
    plan_planner: str = "rule",
) -> Dict[str, Any]:
    step_rows = [
        {"step_id": s.step_id, "tool": s.tool, "optional": bool(s.optional)}
        for s in steps
    ]
    planner_note = {
        "llm": "由 GLM 生成 Tool 调用链（白名单校验）",
        "rule": "使用 Agent 内置规则模板",
        "rule_fallback": "GLM 计划失败，回退规则模板",
    }.get(plan_planner, plan_planner)

    return {
        "phase": "plan",
        "title": "② 生成执行计划",
        "planner": plan_planner,
        "lines": [planner_note, f"共 {len(step_rows)} 步"],
        "steps": step_rows,
        "agent_id": agent_id,
    }


def build_parse_trace(agent_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if agent_id == "scheduling":
        if data.get("intent_type") == "CLARIFICATION":
            lines = [
                str(data.get("parse_note_zh") or "目标无法映射为可计算指标"),
                str(data.get("clarification_question") or data.get("summary_zh") or ""),
                "等待您的回复；本次不执行排程计算。",
            ]
        else:
            lines = [
                f"业务目标：{data.get('schedule_goal_name_zh') or data.get('schedule_goal') or '—'}",
                f"策略：{data.get('strategy_name') or data.get('strategy_id') or '—'}",
                f"算法：{', '.join(data.get('solvers') or []) or '—'}",
            ]
            if data.get("full_compare"):
                lines.append("模式：全部非 RL 算法对比后按目标指标选优")
            if data.get("summary_zh") and data.get("summary_zh") not in lines:
                lines.insert(0, str(data["summary_zh"]))
        return {
            "phase": "parse",
            "title": "③ 排程参数解析",
            "planner": data.get("planner", "rule"),
            "lines": lines,
        }
    if agent_id == "events":
        env = data if data.get("event_type") else (data.get("event_envelope") or data)
        lines = [
            f"事件类型：{env.get('event_type', '—')}",
        ]
        if env.get("summary_zh"):
            lines.insert(0, str(env["summary_zh"]))
        return {
            "phase": "parse",
            "title": "③ 异常事件解析",
            "planner": data.get("planner", "rule"),
            "lines": lines,
        }
    return None


def format_plan_log_line(entry: Dict[str, Any]) -> str:
    status = entry.get("status", "pending")
    line = f"{entry.get('step_id', '?')} {entry.get('tool', '?')} → {status}"
    if entry.get("duration_ms") is not None:
        line += f" ({entry['duration_ms']} ms)"
    if entry.get("error"):
        line += f"：{str(entry['error'])[:120]}"
    return line


def build_execution_trace_shell() -> Dict[str, Any]:
    return {
        "phase": "execute",
        "title": "④ 执行 Tool 链",
        "planner": None,
        "lines": [],
        "steps": [],
    }


def build_execution_trace(plan_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    for entry in plan_log or []:
        rows.append(format_plan_log_line(entry))
    return {
        "phase": "execute",
        "title": "④ 执行 Tool 链",
        "planner": None,
        "lines": rows or ["（无步骤）"],
        "steps": plan_log,
    }


def build_preview_trace(
    *,
    message: str,
    route: Dict[str, Any],
    plan_steps: List[PlanStep],
    plan_planner: str,
    parse_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    trace: List[Dict[str, Any]] = [build_route_trace(route)]
    trace.append(build_plan_trace(route["agent_id"], plan_steps, plan_planner=plan_planner))
    if parse_data:
        pt = build_parse_trace(route["agent_id"], parse_data)
        if pt:
            trace.append(pt)
    return trace


def merge_run_trace(
    preview_trace: List[Dict[str, Any]],
    plan_log: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out = list(preview_trace)
    out.append(build_execution_trace(plan_log))
    return out


def build_strategy_trace_block(run: Dict[str, Any]) -> Dict[str, Any]:
    """Thin wrapper: planning run → SSE-mergeable strategy trace block."""
    from metaforge.strategy.trace import build_strategy_trace

    return build_strategy_trace(run)
