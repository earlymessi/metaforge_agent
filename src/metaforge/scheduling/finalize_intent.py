"""排程意图后处理：LLM 与规则解析共用（目标推断、全量对比、置信度门控）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.agent.scheduling_agent import all_non_rl_solvers
from metaforge.scheduling.context import OFFERED_GOAL_OPTIONS, ContextManager
from metaforge.scheduling.goals import (
    detect_unmapped_goal_phrase,
    infer_schedule_goal,
    is_under_specified_scheduling_goal,
    should_run_full_compare,
)
from metaforge.scheduling.intent_types import (
    CONFIDENCE_CLARIFY,
    CONFIDENCE_EXECUTE,
    CONFIDENCE_HIGH,
    ScheduleIntentType,
    normalize_intent_type,
)

_VAGUE_SCHEDULE_HINTS = ("帮我排", "排一下", "排个程", "安排一下", "做个排程")


def apply_goal_driven_compare(
    data: Dict[str, Any],
    message: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """根据业务目标决定是否全量算法对比（LLM 未显式 full_compare 时补充）。"""
    if data.get("full_compare"):
        return data
    goal_inf = infer_schedule_goal(message)
    if not should_run_full_compare(
        goal_inf,
        message,
        explicit_solvers=bool(params.get("solvers")),
        is_fast=bool(data.get("is_fast_mode")),
    ):
        return data
    out = dict(data)
    out["solvers"] = all_non_rl_solvers()
    out["full_compare"] = True
    out["schedule_goal"] = goal_inf.goal_id
    out["schedule_goal_name_zh"] = goal_inf.goal_name_zh
    out["recommend_metric"] = goal_inf.recommend_metric
    out["strategy_id"] = goal_inf.strategy_id
    out["strategy_name"] = goal_inf.strategy_name
    out["intent_type"] = ScheduleIntentType.COMPARE_SOLVERS.value
    out["confidence"] = max(float(out.get("confidence") or 0), goal_inf.confidence, 0.9)
    notes = list(out.get("solver_match_notes") or [])
    notes.append(
        f"目标「{goal_inf.goal_name_zh}」：对比全部 {len(out['solvers'])} 个非 RL 算法后选优"
    )
    out["solver_match_notes"] = notes
    return out


def _is_vague_schedule_request(message: str) -> bool:
    text = (message or "").strip()
    goal = infer_schedule_goal(text)
    if goal.is_clear:
        return False
    if any(
        k in text
        for k in (
            "交付",
            "交期",
            "吞吐",
            "成本",
            "均衡",
            "禁忌",
            "遗传",
            "模拟退火",
            "蚁群",
            "算例",
            "物料",
            "不考虑物料",
            "忽略物料",
            "最短",
            "完工",
            "拖期",
            "能耗",
        )
    ):
        return False
    if len(text) > 24:
        return False
    from metaforge.agent.scheduling_agent import _COMPARE_HINTS

    if any(h in text for h in _VAGUE_SCHEDULE_HINTS):
        return not any(h in text for h in _COMPARE_HINTS)
    return len(text) <= 5 and "排" in text


def _build_clarification(
    data: Dict[str, Any],
    message: str,
    *,
    unmapped_phrase: Optional[str] = None,
) -> Dict[str, Any]:
    parts: List[str] = []
    if unmapped_phrase:
        parts.append(
            f"「{unmapped_phrase}」无法直接对应系统内的排程指标"
            "（完工时间、拖期、能耗、负载均衡等），请说明您更看重哪一类："
        )
    else:
        parts.append("当前描述未明确排程优先级，请说明您更看重：")
    parts.append("① 交期/拖期最少 ② 完工时间最短 ③ 能耗成本最低 ④ 负载均衡（可多选或补充）。")
    parts.append("是否启用物料约束？")
    question = " ".join(parts)
    out = dict(data)
    out["intent_type"] = ScheduleIntentType.CLARIFICATION.value
    out["clarification_question"] = question
    out["clarification_context"] = {
        "original_message": message,
        "unmapped_phrase": unmapped_phrase,
        "partial": {k: data.get(k) for k in ("strategy_id", "is_fast_mode")},
    }
    out["summary_zh"] = question
    out["solvers"] = []
    out["solver_match_notes"] = list(data.get("solver_match_notes") or []) + [
        "目标不明确，未选定算法，等待用户补充后再全量对比"
    ]
    if unmapped_phrase:
        out["parse_note_zh"] = (
            f"未能将「{unmapped_phrase}」解析为可计算的优化目标，需澄清后再排程。"
        )
    else:
        out["parse_note_zh"] = "排程目标不明确，需澄清后再执行算法对比。"
    out["needs_user_reply"] = True
    out["offered_options"] = [o.get("label_zh") for o in OFFERED_GOAL_OPTIONS]
    return out


def apply_confidence_gate(
    data: Dict[str, Any],
    message: str,
    session_id: Optional[str],
    *,
    skip_vague: bool = False,
    persist_context: bool = True,
) -> Dict[str, Any]:
    if skip_vague:
        out = dict(data)
        out["confidence"] = max(float(out.get("confidence") or 0.7), CONFIDENCE_EXECUTE)
        if normalize_intent_type(out.get("intent_type")) == ScheduleIntentType.CLARIFICATION:
            out["intent_type"] = ScheduleIntentType.RUN_SCHEDULE.value
            out["needs_user_reply"] = False
            out.pop("clarification_question", None)
            out.pop("clarification_context", None)
        if not out.get("solvers"):
            out["solvers"] = ["spt", "ts"]
        return out

    if not skip_vague and _is_vague_schedule_request(message):
        clar = _build_clarification(data, message, unmapped_phrase=detect_unmapped_goal_phrase(message))
        if persist_context:
            ContextManager.set_pending(
                session_id,
                original_message=message,
                partial_intent=dict(clar.get("clarification_context") or {}),
                question=str(clar["clarification_question"]),
            )
        clar["confidence"] = float(data.get("confidence") or 0.45)
        clar["planner"] = data.get("planner", "rule")
        return clar

    conf = float(data.get("confidence") or 0.7)
    itype = normalize_intent_type(data.get("intent_type"))

    if itype in (
        ScheduleIntentType.LIST_SOLVERS,
        ScheduleIntentType.LIST_STRATEGIES,
        ScheduleIntentType.RUN_BENCHMARK,
    ):
        data["confidence"] = max(conf, CONFIDENCE_EXECUTE)
        return data

    if conf >= CONFIDENCE_EXECUTE:
        data["confidence"] = conf
        return data

    if conf >= CONFIDENCE_CLARIFY:
        clar = _build_clarification(data, message)
        if persist_context:
            ContextManager.set_pending(
                session_id,
                original_message=message,
                partial_intent=dict(clar.get("clarification_context") or {}),
                question=str(clar["clarification_question"]),
            )
        clar["confidence"] = conf
        clar["planner"] = data.get("planner", "rule")
        return clar

    boosted = dict(data)
    boosted["confidence"] = max(conf, 0.55)
    return boosted


def finalize_schedule_interpretation(
    data: Dict[str, Any],
    message: str,
    params: Dict[str, Any],
    session_id: Optional[str],
    *,
    skip_vague: bool = False,
    persist_context: bool = True,
) -> Dict[str, Any]:
    """LLM / 规则解析后的统一后处理链。"""
    if not skip_vague:
        unmapped = detect_unmapped_goal_phrase(message)
        goal_inf = infer_schedule_goal(message)
        if unmapped or is_under_specified_scheduling_goal(message, goal_inf):
            clar = _build_clarification(data, message, unmapped_phrase=unmapped)
            clar["planner"] = data.get("planner", "rule")
            if persist_context:
                ContextManager.set_pending(
                    session_id,
                    original_message=message,
                    partial_intent=dict(clar.get("clarification_context") or {}),
                    question=str(clar["clarification_question"]),
                )
            clar["confidence"] = float(data.get("confidence") or 0.45)
            return clar

    data = apply_goal_driven_compare(data, message, params)
    return apply_confidence_gate(
        data, message, session_id, skip_vague=skip_vague, persist_context=persist_context
    )
