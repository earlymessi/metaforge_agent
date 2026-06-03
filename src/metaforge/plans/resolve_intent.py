"""计划库意图：GLM 优先 → 精确规则 → 短语兜底。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from metaforge.orchestrator.llm_config import llm_enabled, llm_fallback_rule
from metaforge.plans.intent import parse_plan_intent, rule_fallback_plan_intent, should_navigate_aps


def intent_to_plan_steps(intent: Dict[str, Any]) -> list:
    """由结构化 intent 生成 PlanStep 列表（供 plans Agent 使用）。"""
    from metaforge.agents.base import PlanStep

    action = intent.get("action") or "list"
    nav = bool(intent.get("navigate_aps", should_navigate_aps(action)))

    if action == "create":
        return [
            PlanStep(
                "s1",
                "data.create_plan",
                {"plan_name": intent.get("plan_name") or ""},
            )
        ]
    if action == "delete":
        return [PlanStep("s1", "data.delete_plan", {"query": intent.get("query") or ""})]
    if action in ("bind", "view"):
        return [
            PlanStep(
                "s1",
                "data.bind_plan",
                {"query": intent.get("query") or "", "navigate_aps": nav},
            )
        ]
    if action == "rename":
        return [
            PlanStep(
                "s1",
                "data.rename_plan",
                {
                    "query": intent.get("query") or "",
                    "new_name": intent.get("new_name") or "",
                },
            )
        ]
    if action == "duplicate":
        return [
            PlanStep(
                "s1",
                "data.duplicate_plan",
                {
                    "query": intent.get("query") or "",
                    "new_name": intent.get("new_name") or "",
                },
            )
        ]
    if action == "update_status":
        return [
            PlanStep(
                "s1",
                "data.update_status",
                {
                    "query": intent.get("query") or "",
                    "status": intent.get("status") or "done",
                },
            )
        ]
    if action == "goto_aps":
        return [PlanStep("s1", "data.list_plans", {}, optional=True)]
    if action == "clear":
        return []
    return [PlanStep("s1", "data.list_plans", {})]


def resolve_plan_intent(
    message: str,
    *,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """返回 (intent_dict, planner: llm|rule|rule_fallback)。"""
    msg = (message or "").strip()
    params = params or {}

    if not msg:
        return {"action": "list", "planner": "rule"}, "rule"

    llm_error = ""
    use_llm = llm_enabled() and params.get("use_llm") is not False
    if use_llm:
        try:
            from metaforge.orchestrator.llm import invoke

            data = invoke("plans_intent", message=msg)
            out = dict(data)
            out["planner"] = "llm"
            return out, "llm"
        except Exception as e:
            if not llm_fallback_rule():
                raise
            llm_error = str(e)

    rule = parse_plan_intent(msg)
    if rule is not None:
        out = dict(rule)
        out["planner"] = "rule"
        return out, "rule"

    fb = rule_fallback_plan_intent(msg, llm_error=llm_error)
    fb["planner"] = "rule_fallback"
    return fb, "rule_fallback"
