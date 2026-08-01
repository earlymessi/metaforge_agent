"""结构化输出解析（对标 LangChain OutputParser）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from metaforge.agent.scheduling_agent import _STRATEGY_BY_ID
from metaforge.agents.base import PlanStep
from metaforge.events.normalize_envelope import (
    build_event_envelope,
    coerce_hours,
    extract_job_names,
    normalize_event_type,
)
from metaforge.orchestrator.router import INTENT_TO_AGENT
from metaforge.plans.intent import parse_plan_intent, should_navigate_aps
from metaforge.agent.scheduling_agent import all_non_rl_solvers
from metaforge.scheduling.goals import infer_schedule_goal
from metaforge.scheduling.intent_types import (
    FAST_MAKESPAN_BOOST,
    ScheduleIntentType,
    normalize_intent_type,
)
from metaforge.utils.solver_registry import resolve_solver_id

_VALID_INTENTS = frozenset(INTENT_TO_AGENT.keys())
_WEIGHT_KEYS = ("makespan", "weighted_tardiness_total", "energy_cost", "machine_busy_cv")


def parse_router(raw: Dict[str, Any], *, message: str = "") -> Dict[str, Any]:
    msg = (message or "").strip()
    if msg:
        parsed = parse_plan_intent(msg)
        if parsed is not None:
            return {
                "intent": "plans",
                "agent_id": INTENT_TO_AGENT["plans"],
                "reason_zh": f"计划库操作（{parsed.get('action')}）",
                "router": "llm_guard",
            }
    intent = str(raw.get("intent") or "schedule").strip().lower()
    if intent == "pipeline":
        intent = "schedule"

    if intent == "unsupported":
        from metaforge.services.router_scope import build_out_of_scope_route

        steps = raw.get("reasoning_steps")
        rs = [str(s)[:120] for s in steps[:6]] if isinstance(steps, list) else None
        return build_out_of_scope_route(
            str(raw.get("scope_category") or "general").strip(),
            router="llm",
            reason_zh=str(raw.get("reason_zh") or "")[:200] or None,
            guidance_zh=str(raw.get("guidance_zh") or "")[:800] or None,
            reasoning_steps=rs,
        )

    if intent not in _VALID_INTENTS:
        intent = "schedule"
    out = {
        "intent": intent,
        "agent_id": INTENT_TO_AGENT[intent],
        "reason_zh": str(raw.get("reason_zh") or "")[:200],
        "router": "llm",
    }
    steps = raw.get("reasoning_steps")
    if isinstance(steps, list):
        out["reasoning_steps"] = [str(s)[:120] for s in steps[:6]]
    return out


def parse_scheduling(raw: Dict[str, Any], *, message: str = "") -> Dict[str, Any]:
    solvers_in = raw.get("solvers") or []
    valid: List[str] = []
    seen = set()
    for name in solvers_in:
        try:
            sid = resolve_solver_id(str(name))
        except (KeyError, ValueError):
            continue
        if sid not in seen:
            seen.add(sid)
            valid.append(sid)
    goal_inf = infer_schedule_goal(message) if not raw.get("schedule_goal") else None
    full_compare = bool(raw.get("full_compare"))
    if full_compare:
        valid = all_non_rl_solvers()
    elif not valid:
        valid = ["spt", "ts"]

    sid = str(raw.get("strategy_id") or "balanced")
    if sid not in _STRATEGY_BY_ID:
        sid = "balanced"
    tpl = _STRATEGY_BY_ID[sid]

    weights = dict(tpl["weights"])
    raw_w = raw.get("weights")
    if isinstance(raw_w, dict):
        for k in _WEIGHT_KEYS:
            if k in raw_w and raw_w[k] is not None:
                try:
                    weights[k] = float(raw_w[k])
                except (TypeError, ValueError):
                    pass

    bench = raw.get("benchmark_file")
    if bench is not None and bench != "":
        bench = str(bench)
        if not bench.endswith(".txt"):
            bench = f"{bench}.txt"
    else:
        bench = None

    is_fast = bool(raw.get("is_fast_mode", False))
    if is_fast and "makespan" in weights:
        weights = dict(weights)
        weights["makespan"] = float(weights["makespan"]) * FAST_MAKESPAN_BOOST

    itype = normalize_intent_type(raw.get("intent_type"))
    if full_compare:
        itype = ScheduleIntentType.COMPARE_SOLVERS
    schedule_goal = str(raw.get("schedule_goal") or (goal_inf.goal_id if goal_inf else "composite"))
    recommend_metric = str(
        raw.get("recommend_metric") or (goal_inf.recommend_metric if goal_inf else "makespan")
    )
    if full_compare and goal_inf:
        recommend_metric = goal_inf.recommend_metric

    conf_raw = raw.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(conf_raw if conf_raw is not None else 0.75)))
    except (TypeError, ValueError):
        confidence = 0.75

    clar_q = raw.get("clarification_question")
    clar_q = str(clar_q)[:300] if clar_q else None

    return {
        "message": str(raw.get("message") or message),
        "solvers": valid,
        "weights": weights,
        "strategy_id": sid,
        "strategy_name": str(raw.get("strategy_name") or tpl["name"]),
        "enforce_material": bool(raw.get("enforce_material", False)),
        "benchmark_file": bench,
        "solver_match_notes": list(raw.get("solver_match_notes") or ["由 GLM 解析"]),
        "strategy_match_note": str(raw.get("strategy_match_note") or f"匹配策略 {sid}"),
        "summary_zh": str(raw.get("summary_zh") or f"已按{tpl['name']}选择算法。")[:200],
        "planner": "llm",
        "intent_type": itype.value,
        "confidence": confidence,
        "is_fast_mode": is_fast,
        "full_compare": full_compare,
        "schedule_goal": schedule_goal,
        "schedule_goal_name_zh": str(
            raw.get("schedule_goal_name_zh") or (goal_inf.goal_name_zh if goal_inf else "综合最优")
        ),
        "recommend_metric": recommend_metric,
        "clarification_question": clar_q,
        "clarification_context": raw.get("clarification_context"),
    }


def parse_summarize(raw: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    follow = raw.get("follow_up")
    return {
        "summary_zh": str(raw.get("summary_zh") or "")[:800],
        "follow_up": str(follow)[:300] if follow else None,
        "planner": "llm_summarize",
    }


def parse_react_decision(
    raw: Dict[str, Any],
    *,
    allowed_tools: List[str],
) -> Dict[str, Any]:
    action = str(raw.get("action") or "finish").strip().lower()
    if action not in ("finish", "call_tool"):
        action = "finish"
    tool = str(raw.get("tool") or "").strip()
    params = raw.get("params")
    if not isinstance(params, dict):
        params = {}
    answer = str(raw.get("answer") or raw.get("summary_zh") or "")[:500]
    if action == "call_tool":
        if tool not in allowed_tools:
            raise ValueError(f"tool not allowed: {tool}")
        return {"action": "call_tool", "tool": tool, "params": params, "answer": answer}
    return {"action": "finish", "tool": "", "params": {}, "answer": answer}


def parse_reflect(
    raw: Dict[str, Any],
    *,
    allowed_tools: List[str],
) -> Dict[str, Any]:
    action = str(raw.get("action") or "finish").strip().lower()
    if action not in ("retry", "finish", "clarify", "human"):
        action = "finish"
    tool = str(raw.get("tool") or "").strip()
    params = raw.get("params")
    if not isinstance(params, dict):
        params = {}
    message_zh = str(raw.get("message_zh") or raw.get("answer") or "")[:500]
    feedback_zh = str(raw.get("feedback_zh") or raw.get("reason_zh") or "")[:300]
    is_valid = bool(raw.get("is_valid", action in ("finish", "retry")))
    out: Dict[str, Any] = {
        "action": action,
        "message_zh": message_zh,
        "feedback_zh": feedback_zh,
        "is_valid": is_valid,
        "planner": "llm_reflect",
    }
    if action == "retry":
        if tool and tool not in allowed_tools:
            raise ValueError(f"tool not allowed: {tool}")
        out["tool"] = tool
        out["params"] = params
    return out


def parse_event(
    raw: Dict[str, Any],
    *,
    message: str,
    base_jobs: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    event_type = normalize_event_type(str(raw.get("event_type") or "machine_breakdown"))
    params = raw.get("params")
    if not isinstance(params, dict):
        params = {}
    opts = raw.get("reschedule_options")
    if not isinstance(opts, dict):
        opts = {}
    return build_event_envelope(
        event_type,
        params,
        base_jobs=base_jobs,
        reschedule_options=opts,
        summary_zh=str(raw.get("summary_zh") or message),
        planner="llm",
    )


def parse_insert_job_followup(raw: Dict[str, Any], *, message: str = "", draft: Optional[Dict] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if raw.get("name"):
        out["name"] = str(raw["name"]).strip()
    if raw.get("priority") is not None:
        out["priority"] = int(raw["priority"])
    if raw.get("due_date") is not None:
        out["due_date"] = float(raw["due_date"])
    if raw.get("confirm_default_stub"):
        out["confirm_default_stub"] = True
    tasks = raw.get("tasks")
    if isinstance(tasks, list):
        out["tasks"] = tasks
    return out


def parse_plan_steps(raw: Dict[str, Any], allowed_tools: List[str]) -> List[PlanStep]:
    steps_in = raw.get("steps")
    if not isinstance(steps_in, list) or not steps_in:
        raise ValueError("steps empty")

    allowed = set(allowed_tools)
    out: List[PlanStep] = []
    for i, s in enumerate(steps_in):
        if not isinstance(s, dict):
            continue
        tool = str(s.get("tool") or "").strip()
        if tool not in allowed:
            raise ValueError(f"tool not allowed: {tool}")
        step_params = s.get("params")
        if not isinstance(step_params, dict):
            step_params = {}
        out.append(
            PlanStep(
                step_id=str(s.get("step_id") or f"s{i + 1}"),
                tool=tool,
                params=step_params,
                optional=bool(s.get("optional")),
            )
        )
    if not out:
        raise ValueError("no valid steps")
    return out


_PLANS_ACTIONS = frozenset(
    {
        "create",
        "list",
        "delete",
        "view",
        "bind",
        "rename",
        "duplicate",
        "update_status",
        "clear",
        "goto_aps",
    }
)


def parse_plans_intent(raw: Dict[str, Any], *, message: str = "") -> Dict[str, Any]:
    action = str(raw.get("action") or "list").strip().lower()
    if action not in _PLANS_ACTIONS:
        action = "list"

    out: Dict[str, Any] = {
        "action": action,
        "plan_name": str(raw.get("plan_name") or "").strip(),
        "query": str(raw.get("query") or "").strip(),
        "new_name": str(raw.get("new_name") or "").strip(),
        "status": str(raw.get("status") or "").strip().lower(),
        "summary_zh": str(raw.get("summary_zh") or message)[:200],
        "planner": "llm",
    }
    if should_navigate_aps(action):
        out["navigate_aps"] = True
    steps = raw.get("reasoning_steps")
    if isinstance(steps, list):
        out["reasoning_steps"] = [str(s)[:120] for s in steps[:6]]
    return out
