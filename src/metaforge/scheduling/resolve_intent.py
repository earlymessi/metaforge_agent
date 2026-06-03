"""统一排程意图解析：五步流程 + GLM 优先，失败回退规则。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.agent.scheduling_agent import SchedulingAgent, _BENCHMARK_RE
from metaforge.orchestrator.llm_config import llm_enabled, llm_fallback_rule
from metaforge.plans.intent import is_plans_management_message
from metaforge.scheduling.context import ContextManager
from metaforge.agent.scheduling_agent import all_non_rl_solvers
from metaforge.scheduling.finalize_intent import finalize_schedule_interpretation
from metaforge.scheduling.goals import (
    goal_summary_note,
    parse_clarification_reply,
    clarification_reply_wants_full_compare,
    should_run_full_compare,
)
from metaforge.scheduling.intent_types import (
    CONFIDENCE_CLARIFY,
    CONFIDENCE_EXECUTE,
    CONFIDENCE_HIGH,
    FAST_MAKESPAN_BOOST,
    ScheduleIntentType,
    detect_list_intent,
    normalize_intent_type,
)


from metaforge.scheduling.llm_intent import parse_message_with_llm


def intent_to_interpretation_dict(intent) -> Dict[str, Any]:
    return {
        "message": intent.message,
        "solvers": intent.solvers,
        "weights": intent.weights,
        "strategy_id": intent.strategy_id,
        "strategy_name": intent.strategy_name,
        "enforce_material": intent.enforce_material,
        "benchmark_file": intent.benchmark_file,
        "solver_match_notes": list(intent.solver_match_notes),
        "strategy_match_note": intent.strategy_match_note,
        "summary_zh": intent.summary_zh,
        "intent_type": getattr(intent, "intent_type", ScheduleIntentType.RUN_SCHEDULE.value),
        "confidence": float(getattr(intent, "confidence", 0.75)),
        "is_fast_mode": bool(getattr(intent, "is_fast_mode", False)),
        "full_compare": bool(getattr(intent, "full_compare", False)),
        "schedule_goal": getattr(intent, "schedule_goal", "composite"),
        "schedule_goal_name_zh": getattr(intent, "schedule_goal_name_zh", ""),
        "recommend_metric": getattr(intent, "recommend_metric", "makespan"),
        "clarification_question": getattr(intent, "clarification_question", None),
        "clarification_context": getattr(intent, "clarification_context", None),
        "parse_note_zh": getattr(intent, "parse_note_zh", None),
        "needs_user_reply": bool(getattr(intent, "needs_user_reply", False)),
    }


def _rule_interpretation(
    message: str,
    params: Dict[str, Any],
    benchmark_file: Optional[str],
    *,
    llm_error: Optional[str] = None,
    planner: str = "rule",
) -> Dict[str, Any]:
    agent = SchedulingAgent()
    intent = agent.parse(
        message,
        solvers=params.get("solvers"),
        weights=params.get("weights"),
        strategy_id=params.get("strategy_id"),
        enforce_material=params.get("enforce_material"),
        benchmark_file=benchmark_file or params.get("benchmark_file"),
    )
    data = intent_to_interpretation_dict(intent)
    data["planner"] = planner
    if llm_error:
        data["llm_error"] = llm_error
    return data


def _apply_explicit_overrides(data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    from metaforge.agent.scheduling_agent import _STRATEGY_BY_ID

    out = dict(data)
    if params.get("solvers"):
        out["solvers"] = list(params["solvers"])
    if params.get("weights"):
        out["weights"] = dict(params["weights"])
    sid = params.get("strategy_id")
    if sid and sid in _STRATEGY_BY_ID:
        out["strategy_id"] = sid
        out["strategy_name"] = _STRATEGY_BY_ID[sid]["name"]
        if not params.get("weights"):
            out["weights"] = dict(_STRATEGY_BY_ID[sid]["weights"])
    if params.get("enforce_material") is not None:
        out["enforce_material"] = bool(params["enforce_material"])
    if params.get("benchmark_file"):
        out["benchmark_file"] = params["benchmark_file"]
    if params.get("intent_type"):
        out["intent_type"] = normalize_intent_type(params["intent_type"]).value
    return out


def _apply_fast_makespan_boost(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data.get("is_fast_mode"):
        return data
    w = dict(data.get("weights") or {})
    if "makespan" in w:
        w["makespan"] = float(w["makespan"]) * FAST_MAKESPAN_BOOST
    out = dict(data)
    out["weights"] = w
    return out


def _step1_structural_intercept(
    message: str, params: Dict[str, Any], bench: Optional[str]
) -> Optional[Dict[str, Any]]:
    """结构性短路：显式 intent_type、计划库误路由提示（不抢在 GLM 前做 NL 判别）。"""
    if params.get("intent_type"):
        itype = normalize_intent_type(params["intent_type"])
        data = _rule_interpretation(message, params, bench)
        data["intent_type"] = itype.value
        data["confidence"] = CONFIDENCE_HIGH
        return data

    if is_plans_management_message(message):
        data = _rule_interpretation(message, params, bench)
        data["planner"] = "rule"
        data["summary_zh"] = "该消息属于计划库管理，请使用「计划管理」或说「新建计划 xxx」。"
        data["confidence"] = CONFIDENCE_HIGH
        return data

    return None


def _offline_catalog_intercept(
    message: str, params: Dict[str, Any], bench: Optional[str]
) -> Optional[Dict[str, Any]]:
    """离线回退：目录列举与标准算例（语义判别见 scheduling prompt few-shots）。"""
    list_type = detect_list_intent(message)
    if list_type:
        return {
            "message": message,
            "intent_type": list_type.value,
            "confidence": CONFIDENCE_HIGH,
            "planner": "rule",
            "summary_zh": "列出可用算法或策略。",
            "solvers": [],
            "weights": {},
            "strategy_id": "balanced",
            "strategy_name": "综合平衡",
            "enforce_material": True,
            "benchmark_file": None,
            "solver_match_notes": [],
            "strategy_match_note": "",
            "is_fast_mode": False,
        }

    m = _BENCHMARK_RE.search(message)
    if m and any(k in message for k in ("算例", "benchmark", "跑", "ft", "la")):
        data = _rule_interpretation(message, params, bench or f"{m.group(1).lower()}.txt")
        data["intent_type"] = ScheduleIntentType.RUN_BENCHMARK.value
        data["confidence"] = CONFIDENCE_HIGH
        data["benchmark_file"] = data.get("benchmark_file") or f"{m.group(1).lower()}.txt"
        return data

    return None


def _resolve_offline(message: str, params: Dict[str, Any], bench: Optional[str]) -> Dict[str, Any]:
    intercepted = _offline_catalog_intercept(message, params, bench)
    if intercepted is not None:
        return intercepted
    data = _rule_interpretation(message, params, bench)
    data["confidence"] = _evaluate_confidence(data)
    return data


def _evaluate_confidence(data: Dict[str, Any], *, from_llm: bool = False) -> float:
    if from_llm and data.get("confidence") is not None:
        try:
            c = float(data["confidence"])
            return max(0.0, min(1.0, c))
        except (TypeError, ValueError):
            pass
    notes = data.get("solver_match_notes") or []
    if any("未命中具体算法" in str(n) for n in notes):
        return 0.55
    if len(notes) >= 2 and not any("默认" in str(n) for n in notes):
        return CONFIDENCE_HIGH
    if data.get("solvers") and data.get("strategy_id") not in (None, "", "balanced"):
        return 0.85
    if data.get("solvers") and any("命中算法" in str(n) for n in notes):
        return 0.75
    return 0.55


def _merge_pending_message(message: str, session_id: Optional[str]) -> str:
    pending = ContextManager.get_pending(session_id)
    if not pending:
        return message
    return ContextManager.merge_clarification_reply(session_id, message)


def _interpretation_from_clarification_reply(
    goal_inf,
    reply_message: str,
    params: Dict[str, Any],
    benchmark_file: Optional[str],
    *,
    original_message: str = "",
) -> Dict[str, Any]:
    """澄清续答已解析出明确目标：仅用续答文本做物料等细节，不再把原问里的「满意度」带入。"""
    agent = SchedulingAgent()
    intent = agent.parse(
        reply_message,
        solvers=params.get("solvers"),
        weights=params.get("weights"),
        strategy_id=goal_inf.strategy_id,
        enforce_material=params.get("enforce_material"),
        benchmark_file=benchmark_file or params.get("benchmark_file"),
    )
    intent.schedule_goal = goal_inf.goal_id
    intent.schedule_goal_name_zh = goal_inf.goal_name_zh
    intent.recommend_metric = goal_inf.recommend_metric
    intent.strategy_id = goal_inf.strategy_id
    intent.strategy_name = goal_inf.strategy_name
    intent.confidence = max(float(intent.confidence), goal_inf.confidence, 0.9)
    intent.intent_type = ScheduleIntentType.RUN_SCHEDULE.value

    if clarification_reply_wants_full_compare(reply_message) and should_run_full_compare(
        goal_inf,
        reply_message,
        explicit_solvers=bool(params.get("solvers")),
        is_fast=bool(intent.is_fast_mode),
    ):
        intent.solvers = all_non_rl_solvers()
        intent.full_compare = True
        intent.intent_type = ScheduleIntentType.COMPARE_SOLVERS.value
        intent.solver_match_notes = list(intent.solver_match_notes) + [
            goal_summary_note(goal_inf, n_solvers=len(intent.solvers)),
        ]
        intent.strategy_match_note = goal_summary_note(goal_inf, n_solvers=len(intent.solvers))
    elif not params.get("solvers"):
        intent.full_compare = False
        intent.intent_type = ScheduleIntentType.RUN_SCHEDULE.value
        if len(intent.solvers) > 4:
            intent.solvers = ["spt", "ts"]

    data = intent_to_interpretation_dict(intent)
    data["planner"] = "rule"
    note = f"已根据澄清续答「{goal_inf.matched_keyword or goal_inf.goal_name_zh}」确定目标"
    if original_message:
        note += f"（原描述：{original_message[:40]}…）" if len(original_message) > 40 else f"（原描述：{original_message}）"
    data["solver_match_notes"] = list(data.get("solver_match_notes") or []) + [note]
    data["needs_user_reply"] = False
    return data


def resolve_schedule_intent(
    params: Dict[str, Any],
    *,
    extras: Optional[Dict[str, Any]] = None,
    benchmark_file: Optional[str] = None,
    session_id: Optional[str] = None,
    persist_context: bool = True,
) -> Dict[str, Any]:
    extras = extras or {}
    session_id = session_id or params.get("session_id") or extras.get("session_id")
    reply_raw = (params.get("message") or extras.get("message") or "").strip()
    bench = benchmark_file or params.get("benchmark_file") or extras.get("benchmark_file")

    pending_snapshot = ContextManager.get_pending(session_id)
    had_pending = pending_snapshot is not None

    if had_pending:
        goal_from_reply = parse_clarification_reply(reply_raw)
        if goal_from_reply:
            original = (pending_snapshot or {}).get("original_message") or ""
            data = _interpretation_from_clarification_reply(
                goal_from_reply,
                reply_raw,
                params,
                bench,
                original_message=original,
            )
            data = _apply_explicit_overrides(data, params)
            if persist_context:
                ContextManager.consolidate_after_run(
                    session_id, data, event_type="clarification_resolved"
                )
            return data
        message = _merge_pending_message(reply_raw, session_id)
        params = dict(params)
        params["message"] = message
    else:
        message = reply_raw

    intercepted = _step1_structural_intercept(message, params, bench)
    if intercepted is not None:
        data = _apply_explicit_overrides(intercepted, params)
        if had_pending and data.get("intent_type") != ScheduleIntentType.CLARIFICATION.value:
            ContextManager.consolidate_after_run(session_id, data, event_type="clarification_resolved")
        else:
            ContextManager.update_from_interpretation(session_id, data)
        return data

    use_llm = llm_enabled() and params.get("use_llm") is not False and bool(message)
    data: Dict[str, Any]

    if use_llm:
        try:
            data = parse_message_with_llm(
                message,
                params=params,
                benchmark_file=bench,
                session_id=session_id,
            )
            data["planner"] = "llm"
            data = _apply_fast_makespan_boost(data)
            data["confidence"] = _evaluate_confidence(data, from_llm=True)
        except Exception as e:
            if not llm_fallback_rule():
                raise
            data = _resolve_offline(message, params, bench)
            data["planner"] = "rule_fallback"
            if str(e):
                data["llm_error"] = str(e)[:300]
    else:
        data = _resolve_offline(message, params, bench)
        data["planner"] = data.get("planner") or "rule"

    if data.get("is_fast_mode") and params.get("solvers"):
        data["solvers"] = list(params["solvers"])

    data = finalize_schedule_interpretation(
        data,
        message,
        params,
        session_id,
        skip_vague=had_pending or bool(params.get("_skip_vague_clarify")),
        persist_context=persist_context,
    )
    data = _apply_explicit_overrides(data, params)

    if data.get("intent_type") == ScheduleIntentType.CLARIFICATION.value:
        return data
    if not persist_context:
        return data
    if had_pending:
        ContextManager.consolidate_after_run(session_id, data, event_type="clarification_resolved")
    else:
        ContextManager.update_from_interpretation(session_id, data)
    return data