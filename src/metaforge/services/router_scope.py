"""Orchestrator：能力范围外问题的引导文案（由 GLM Router 判定 intent=unsupported）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# scope_category 由 GLM 在 Router JSON 中输出；此处仅维护默认引导模板
SCOPE_GUIDANCE: Dict[str, str] = {
    "mes_execution": (
        "您问的是 **MES 现场执行监控**（当前在执行哪张计划/订单、仿真进度、机台实时状态等），"
        "这不在六个业务 Agent（排程、异常重排、齐套、交期承诺、方案对比、计划库）的职责范围内。\n\n"
        "请前往 **生产看板**（主控台 → 生产看板，`/new-ui/dashboard`）查看：\n"
        "· 当前执行计划与基准算法\n"
        "· MES 仿真进度与甘特\n"
        "· 数字孪生车间与人员派工\n\n"
        "若需评估「排程结果能否满足交期」，请明确提问，例如："
        "「当前排程交期能否满足」「哪些工单可能延期」。"
    ),
    "general": (
        "该问题不在当前六个业务 Agent 的能力范围内，我无法代为处理。\n\n"
        "本助手可协助：排程计算、异常重排、齐套检查、交期承诺评估、多方案对比、计划库管理。"
        "请换一种与上述能力相关的问法，或到对应功能页面操作。"
    ),
}

SUPPORTED_SCOPE_CATEGORIES = frozenset(SCOPE_GUIDANCE.keys())


def build_out_of_scope_route(
    category: str,
    *,
    router: str = "llm",
    reason_zh: Optional[str] = None,
    guidance_zh: Optional[str] = None,
    reasoning_steps: Optional[List[str]] = None,
    router_build_id: Optional[str] = None,
) -> Dict[str, Any]:
    """将 GLM Router 的 unsupported 判定转为编排器可执行的拦截路由。"""
    cat = category if category in SUPPORTED_SCOPE_CATEGORIES else "general"
    guidance = (guidance_zh or "").strip() or SCOPE_GUIDANCE[cat]
    route: Dict[str, Any] = {
        "agent_id": None,
        "intent": "unsupported",
        "router": router,
        "out_of_scope": True,
        "scope_category": cat,
        "reason_zh": (reason_zh or f"问题超出六个业务 Agent 范围（{cat}）")[:300],
        "guidance_zh": guidance,
    }
    if router_build_id:
        route["router_build_id"] = router_build_id
    if reasoning_steps:
        route["reasoning_steps"] = [str(s)[:120] for s in reasoning_steps[:6]]
    return route
