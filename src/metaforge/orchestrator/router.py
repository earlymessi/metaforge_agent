"""Intent Router：一个用户意图 → 一个业务 Agent。

意图分辨以 GLM 为主（见 orchestrator.llm 的 router 节点）；本模块仅保留：
- 用户显式指定 intent
- 计划库话术的硬性纠正（避免误判为 schedule）
- 动态事件（改交期/插单/故障等）的硬性纠正（避免误判为 commitment）
- LLM 不可用时的极简规则回退
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from metaforge.orchestrator.llm_config import llm_enabled, llm_fallback_rule
from metaforge.agents.persist_intent import is_schedule_persist_message
from metaforge.plans.intent import parse_plan_intent

INTENT_TO_AGENT = {
    "schedule": "scheduling",
    "reschedule": "events",
    "kitting": "kitting",
    "commitment": "commitment",
    "whatif": "whatif",
    "plans": "plans",
    # 兼容旧客户端 / GLM 仍输出 pipeline
    "pipeline": "scheduling",
}

AGENT_TO_INTENT = {v: k for k, v in INTENT_TO_AGENT.items() if k != "pipeline"}

# 启动后可在 /api/llm/status 核对；若与助手 trace 不一致说明未加载本文件
ROUTER_BUILD_ID = "2026-06-05-llm-scope-v2"

# 改交期/插单/故障等动态事件 → events Agent（非 commitment 问询）
_RESCHEDULE_EVENT_RE = re.compile(
    r"(?:改交期|插单|急单|撤单|"
    r"(?:订单|工单).*(?:交期|工期).*(?:改为|改成|调整到?|延至)|"
    r"(?:交期|工期).*(?:改为|改成|调整到?|延至)|"
    r"(?:改为|改成|调整到?|延至).*(?:交期|工期)|"
    r"(?:坏了|故障|breakdown|停机|重排|新增(?:订单|工单)))",
    re.I,
)


def is_reschedule_event_message(message: str) -> bool:
    """用户要发起动态事件并重排（与生产看板异常重排一致），非单纯交期风险评估。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if _RESCHEDULE_EVENT_RE.search(msg):
        return True
    # 「3号机坏了4小时」类已在上面；数量/优先级/取消
    if re.search(r"(?:加急|优先级|取消|撤单|数量).*(?:改|变|调整)", msg):
        return True
    if re.search(r"(?:工单|订单).*(?:加急|优先级)|(?:加急|优先级).*(?:工单|订单)", msg):
        return True
    return False


_EVENTS_CATALOG_RE = re.compile(
    r"支持哪些|有哪些事件|事件类型|能处理什么异常",
    re.I,
)


def is_events_catalog_message(message: str) -> bool:
    msg = (message or "").strip()
    if not msg:
        return False
    if _EVENTS_CATALOG_RE.search(msg) and re.search(
        r"异常|事件|重排|故障|插单", msg, re.I
    ):
        return True
    return bool(_EVENTS_CATALOG_RE.search(msg) and "计划" not in msg)


_KITTING_SCHEDULE_PREDICT_RE = re.compile(
    r"先排程|先排产",
    re.I,
)
_KITTING_PREDICT_RE = re.compile(
    r"预测物料|物料消耗|物料仿真",
    re.I,
)


def is_kitting_schedule_then_predict_message(message: str) -> bool:
    msg = (message or "").strip()
    if not msg:
        return False
    return bool(
        _KITTING_SCHEDULE_PREDICT_RE.search(msg)
        and _KITTING_PREDICT_RE.search(msg)
    )


_WHATIF_COMPARE_RE = re.compile(
    r"对比|比较|哪个更好|各跑一遍|假设用",
    re.I,
)
_WHATIF_ALGO_RE = re.compile(
    r"遗传|模拟退火|禁忌|SPT|GA|TS|算法",
    re.I,
)
_WHATIF_STRATEGY_RE = re.compile(
    r"对比.*(?:策略|方案)|两种方案|交付.*吞吐|吞吐.*交付|"
    r"(?:交期|交付).*(?:产能|吞吐)|(?:产能|吞吐).*(?:交期|交付)|"
    r"(?:交付|产能)优先.*(?:产能|交付)优先|方案.*风险|风险.*方案",
    re.I,
)


def is_whatif_compare_message(message: str) -> bool:
    msg = (message or "").strip()
    if not msg:
        return False
    if _WHATIF_STRATEGY_RE.search(msg) and not _WHATIF_ALGO_RE.search(msg):
        return True
    if _WHATIF_COMPARE_RE.search(msg) and _WHATIF_ALGO_RE.search(msg):
        return True
    return False


_KITTING_MATERIAL_RE = re.compile(
    r"缺料|齐套|物料.{0,12}(?:够|足|齐)|能否开工|按时开工|开工条件|齐套检查|BOM|"
    r"这批订单能否",
    re.I,
)


def is_kitting_material_message(message: str) -> bool:
    """齐套/缺料因果分析（非单纯「交期能不能满足」）。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if _KITTING_MATERIAL_RE.search(msg):
        return True
    if "缺料" in msg and re.search(r"延期|工单|开工|影响", msg):
        return True
    return False


_COMMITMENT_DELAY_INQUIRY_RE = re.compile(
    r"哪些.*(?:工单|订单).*(?:延期|延迟)|(?:工单|订单).*(?:可能|会).*(?:延期|延迟)|"
    r"可能延期|延期风险|哪些.*会延期",
    re.I,
)


def is_commitment_delay_inquiry(message: str) -> bool:
    """基于当前排程的延期风险问询（非缺料/BOM 因果）。"""
    if is_kitting_material_message(message):
        return False
    return bool(_COMMITMENT_DELAY_INQUIRY_RE.search((message or "").strip()))


_COMMITMENT_ASSESS_RE = re.compile(
    r"评估.*交付|交付情况|交期说明|对客户|客户.*(?:交货|话术)|"
    r"(?:交期|交付).*(?:风险|满足)|能不能.*(?:交货|交付)|"
    r"5月\d+日.*交货",
    re.I,
)


def is_commitment_assessment_message(message: str) -> bool:
    """交期/交付评估与话术（非重新排程、非 whatif 对比）。"""
    msg = (message or "").strip()
    if not msg or is_kitting_material_message(msg) or is_whatif_compare_message(msg):
        return False
    if re.search(r"用.{0,8}(?:算法|搜索|SPT|禁忌)|跑一下|全量对比", msg, re.I):
        return False
    if _COMMITMENT_ASSESS_RE.search(msg):
        return True
    return is_commitment_delay_inquiry(msg)


def _reschedule_rule_route(message: str, *, router: str = "rule") -> Dict[str, Any]:
    return {
        "agent_id": "events",
        "router": router,
        "intent": "reschedule",
        "rule_reason_zh": "动态事件重排（改交期/插单/故障等），与生产看板异常重排一致",
        "router_build_id": ROUTER_BUILD_ID,
    }


def is_insert_job_followup_message(message: str) -> bool:
    """插单多轮补全：用户仅回复工序/机台/时长等，不含「重排/插单」关键词。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if re.search(r"工序|号机|确认默认|使用默认|默认工艺", msg):
        return True
    if re.search(r"\d+\s*(?:小时|h|分钟|min)\b", msg, re.I):
        return True
    if re.search(r"\d+\s*道", msg):
        return True
    return False


def _rule_fallback_resolve(message: str) -> tuple[str, str]:
    """LLM 关闭或调用失败时的极简回退（关键词尽量少，细粒度交给 GLM）。"""
    msg = (message or "").strip()
    if not msg:
        return "scheduling", "默认进入智能排程（消息为空）"

    # 缺料/齐套因果（含「哪些工单延期」）优先于默认排程
    if is_kitting_material_message(msg):
        return "kitting", "齐套/缺料对工单延期影响分析（规则回退）"

    parsed = parse_plan_intent(msg)
    if parsed is not None:
        return "plans", f"计划库管理（{parsed.get('action')}，规则回退）"

    if is_schedule_persist_message(msg):
        return "scheduling", "排程并落库（规则回退，合并入智能排程）"

    if any(k in msg for k in ("重排", "故障", "插单", "改交期", "急单", "新增")):
        return "events", "异常/重排（规则回退）"
    if is_events_catalog_message(msg):
        return "events", "事件能力查询（规则回退）"
    if is_reschedule_event_message(msg):
        return "events", "动态事件重排（规则回退）"
    if is_insert_job_followup_message(msg):
        return "events", "插单工艺补充（规则回退）"

    if any(k in msg for k in ("齐套", "缺料", "物料够", "能否开工", "开工条件", "齐套检查")):
        return "kitting", "齐套/物料检查（规则回退）"

    if is_commitment_delay_inquiry(msg):
        return "commitment", "工单延期风险问询（规则回退）"

    if is_kitting_schedule_then_predict_message(msg):
        return "kitting", "先排程再物料预测（规则回退）"

    if (
        not is_reschedule_event_message(msg)
        and any(
            k in msg
            for k in (
                "能不能满足",
                "能否满足",
                "交期风险",
                "对客户",
                "违约风险",
                "交付承诺",
                "话术",
            )
        )
    ):
        return "commitment", "交期承诺评估（规则回退）"

    if is_whatif_compare_message(msg):
        return "whatif", "多策略/多算法方案对比（规则回退）"

    if is_kitting_material_message(msg):
        return "kitting", "齐套/缺料对工单延期影响分析（规则回退）"
    return "scheduling", "规则回退：未启用 GLM 时默认智能排程"


def _package_route(
    agent_id: str,
    reason: str,
    router: str,
    message: str,
    *,
    llm_error: Optional[str] = None,
) -> Dict[str, Any]:
    """规则/回退路由统一过护栏，避免 GLM 超时后误进 scheduling。"""
    route: Dict[str, Any] = {
        "agent_id": agent_id,
        "router": router,
        "intent": AGENT_TO_INTENT.get(agent_id),
        "rule_reason_zh": reason,
        "router_build_id": ROUTER_BUILD_ID,
    }
    if llm_error:
        route["llm_error"] = llm_error[:300]
    return _apply_route_guards(route, message)


def _apply_reschedule_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    """改交期/插单/故障等必须进 events，禁止误判为 commitment。"""
    if not is_reschedule_event_message(message):
        return route
    if route.get("agent_id") == "events" and route.get("intent") == "reschedule":
        return route
    return {
        **_reschedule_rule_route(message, router="rule_override"),
        "llm_misroute": route.get("intent"),
        "reason_zh": "用户要修改交期或触发动态事件并重排，已纠正为异常重排 Agent",
    }


def _apply_plans_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    """计划库 CRUD 与排程计算语义不同，GLM 若误判则强制纠正。"""
    parsed = parse_plan_intent(message)
    if parsed is None:
        return route
    if route.get("agent_id") == "plans":
        return route
    return {
        "agent_id": "plans",
        "router": "rule_override",
        "intent": "plans",
        "plan_action": parsed.get("action"),
        "rule_reason_zh": f"计划库操作（{parsed.get('action')}），已纠正路由",
        "llm_misroute": route.get("intent"),
        "reason_zh": "计划库操作应由计划管理 Agent 处理，已纠正路由",
    }


def _apply_commitment_delay_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    """交期/交付评估与延期风险问询 → commitment（非 scheduling 误排程）。"""
    if not is_commitment_assessment_message(message):
        return route
    if route.get("agent_id") == "commitment" and route.get("intent") == "commitment":
        return route
    if route.get("agent_id") in ("scheduling", "kitting", "whatif"):
        return {
            **route,
            "agent_id": "commitment",
            "intent": "commitment",
            "router": "rule_override",
            "rule_reason_zh": "交期/交付评估 → 交期承诺 Agent",
            "router_build_id": ROUTER_BUILD_ID,
        }
    return route


def _apply_kitting_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    """缺料/齐套类问题必须进 kitting，禁止误判为 commitment（会误跑新排程）。"""
    if not is_kitting_material_message(message):
        return route
    if route.get("agent_id") == "kitting" and route.get("intent") == "kitting":
        return route
    return {
        "agent_id": "kitting",
        "router": "rule_override",
        "intent": "kitting",
        "rule_reason_zh": "齐套/缺料对工单开工与延期的影响，应由齐套顾问分析",
        "llm_misroute": route.get("intent"),
        "reason_zh": "用户问的是物料缺料导致的延期，不是交期承诺话术评估",
        "router_build_id": ROUTER_BUILD_ID,
    }


def _apply_events_catalog_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    """「支持哪些异常」等能力查询 → events，避免误判为 plans.list_plans。"""
    if not is_events_catalog_message(message):
        return route
    if route.get("agent_id") == "events" and route.get("intent") == "reschedule":
        return route
    return {
        "agent_id": "events",
        "router": "rule_override",
        "intent": "reschedule",
        "rule_reason_zh": "异常事件能力查询 → 异常重排 Agent",
        "llm_misroute": route.get("intent"),
        "reason_zh": "用户询问支持的异常类型，应由 events 列出事件目录",
        "router_build_id": ROUTER_BUILD_ID,
    }


def _apply_kitting_schedule_predict_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    if not is_kitting_schedule_then_predict_message(message):
        return route
    if route.get("agent_id") == "kitting" and route.get("intent") == "kitting":
        return route
    return {
        "agent_id": "kitting",
        "router": "rule_override",
        "intent": "kitting",
        "rule_reason_zh": "先排程再预测物料 → 齐套顾问 Agent",
        "llm_misroute": route.get("intent"),
        "reason_zh": "用户要排程后做物料仿真，应由齐套顾问处理",
        "router_build_id": ROUTER_BUILD_ID,
    }


def _apply_whatif_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    if not is_whatif_compare_message(message):
        return route
    if route.get("agent_id") == "whatif" and route.get("intent") == "whatif":
        return route
    return {
        "agent_id": "whatif",
        "router": "rule_override",
        "intent": "whatif",
        "rule_reason_zh": "多算法/多策略对比 → 方案对比 Agent",
        "llm_misroute": route.get("intent"),
        "reason_zh": "用户要对比多种排程方案，应由 whatif Agent 处理",
        "router_build_id": ROUTER_BUILD_ID,
    }


def _apply_insert_followup_guard(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    """插单工艺补充（无「插单」关键词）必须留在 events Agent。"""
    if not is_insert_job_followup_message(message):
        return route
    if route.get("agent_id") == "events" and route.get("intent") == "reschedule":
        return route
    return {
        **_reschedule_rule_route(message, router="rule_override"),
        "llm_misroute": route.get("intent"),
        "reason_zh": "插单工艺补充应继续由异常重排 Agent 处理，已纠正路由",
    }


def _apply_route_guards(route: Dict[str, Any], message: str) -> Dict[str, Any]:
    """LLM / 规则 / rule_fallback 路由后的安全护栏（能力范围由 GLM intent=unsupported 判定）。"""
    if route.get("out_of_scope"):
        return route
    route = _apply_events_catalog_guard(route, message)
    route = _apply_kitting_schedule_predict_guard(route, message)
    route = _apply_whatif_guard(route, message)
    route = _apply_kitting_guard(route, message)
    route = _apply_commitment_delay_guard(route, message)
    route = _apply_reschedule_guard(route, message)
    route = _apply_plans_guard(route, message)
    route = _apply_insert_followup_guard(route, message)
    return route


def _llm_router_mode() -> str:
    """glm/auto：LLM 优先；rule/off：仅规则回退。"""
    return os.getenv("LLM_ROUTER", "glm").strip().lower()


def coerce_route_for_message(
    message: str,
    intent: Optional[str] = None,
    route: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """流式/预览链路兜底：计划库话术必须落在 plans（防止加载到旧包时误进 scheduling）。"""
    from metaforge.memory.pending import pending_route_hint

    pending = pending_route_hint(context)
    if pending:
        return pending
    if has_pending_insert_job_intake(context):
        return resolve_agent_route(message, intent, context=context)
    msg = (message or "").strip()
    if parse_plan_intent(msg) is not None:
        if route and route.get("agent_id") == "plans" and route.get("intent") == "plans":
            return route
        return resolve_agent_route(msg, intent, context=context)
    return route if route else resolve_agent_route(msg, intent, context=context)


def has_pending_insert_job_intake(context: Optional[Dict[str, Any]]) -> bool:
    from metaforge.memory.manager import MemoryManager
    from metaforge.memory.types import WORKING_KEY_INSERT_JOB

    ns, key = WORKING_KEY_INSERT_JOB
    intake = MemoryManager.from_context(context).get_working(ns, key)
    if intake is None:
        art = (context or {}).get("artifacts") or {}
        intake = art.get("insert_job_intake")
    return isinstance(intake, dict) and intake.get("status") == "need_input"


def resolve_agent_route(
    message: str = "",
    intent: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """返回 agent_id、router（llm|rule|rule_fallback|explicit|rule_override）及 intent。"""
    from metaforge.memory.pending import pending_route_hint

    pending = pending_route_hint(context)
    if pending:
        return pending

    if intent:
        key = intent.strip().lower()
        if key not in INTENT_TO_AGENT:
            raise ValueError(f"Unknown intent: {intent}")
        agent_id = INTENT_TO_AGENT[key]
        resolved_intent = "schedule" if key == "pipeline" else key
        return {
            "agent_id": agent_id,
            "router": "explicit",
            "intent": resolved_intent,
        }

    msg = (message or "").strip()
    if not msg:
        return {"agent_id": "scheduling", "router": "rule", "intent": "schedule"}

    mode = _llm_router_mode()
    rule_only = mode in ("0", "false", "off", "rule")

    if llm_enabled() and not rule_only:
        try:
            from metaforge.orchestrator.llm_router import classify_message_with_llm

            data = classify_message_with_llm(msg)
            if data.get("out_of_scope"):
                route = dict(data)
                route.setdefault("router_build_id", ROUTER_BUILD_ID)
                return route
            route = {
                "agent_id": data["agent_id"],
                "router": "llm",
                "intent": data["intent"],
                "reason_zh": data.get("reason_zh"),
                "router_build_id": ROUTER_BUILD_ID,
            }
            if data.get("reasoning_steps"):
                route["reasoning_steps"] = data["reasoning_steps"]
            return _apply_route_guards(route, msg)
        except Exception as e:
            if not llm_fallback_rule():
                raise
            aid, reason = _rule_fallback_resolve(msg)
            return _package_route(
                aid, reason, "rule_fallback", msg, llm_error=str(e)
            )

    aid, reason = _rule_fallback_resolve(msg)
    return _package_route(aid, reason, "rule", msg)


def resolve_agent_id(message: str = "", intent: Optional[str] = None) -> str:
    return resolve_agent_route(message, intent)["agent_id"]


def get_agent(agent_id: str):
    from metaforge.agents.commitment_collab_bridge import CommitmentCollabBridge
    from metaforge.agents.events_collab_bridge import EventsCollabBridge
    from metaforge.agents.kitting_collab_bridge import KittingCollabBridge
    from metaforge.agents.plans_collab_bridge import PlansCollabBridge
    from metaforge.agents.scheduling_collab_bridge import SchedulingCollabBridge
    from metaforge.agents.whatif_collab_bridge import WhatifCollabBridge

    registry = {
        "scheduling": SchedulingCollabBridge,
        "commitment": CommitmentCollabBridge,
        "kitting": KittingCollabBridge,
        "events": EventsCollabBridge,
        "whatif": WhatifCollabBridge,
        "plans": PlansCollabBridge,
    }
    cls = registry.get(agent_id)
    if cls is None:
        raise ValueError(f"Agent not implemented yet: {agent_id}")
    return cls()
