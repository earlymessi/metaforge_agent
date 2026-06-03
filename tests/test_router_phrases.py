"""车间话术 → 期望 Agent（规则路由，不依赖 GLM）。"""

from __future__ import annotations

import pytest

from metaforge.orchestrator.router import resolve_agent_id

# 设计验收：20 条典型话术（规则回退 / explicit intent）
PHRASE_CASES = [
    ("用禁忌搜索和 SPT 对比一下排程", "scheduling"),
    ("3号机坏了4小时，帮我重排", "events"),
    ("新建计划试产01", "plans"),
    ("检查一下齐套能否开工", "kitting"),
    ("缺料会导致哪些工单延期", "kitting"),
    ("交期能不能满足客户", "commitment"),
    ("哪些工单可能延期", "commitment"),
    ("对比一下交付优先和吞吐优先", "whatif"),
    ("做一个生产计划并排程落库", "scheduling"),
    ("把这个计划排程并保存落库", "scheduling"),
    ("订单106交期改为20", "events"),
    ("支持哪些异常事件", "events"),
    ("列出所有计划", "plans"),
    ("加载计划 演示-A", "plans"),
    ("生成客户交期说明话术", "commitment"),
    ("先排程再预测物料", "kitting"),
    ("对比遗传算法和模拟退火", "scheduling"),
    ("物料延迟3天到货重排", "events"),
    ("删除计划旧版", "plans"),
    ("紧急插单工单 J005", "events"),
]


@pytest.mark.parametrize("message,expected", PHRASE_CASES)
def test_router_phrase_rule_path(message: str, expected: str):
    import os

    prev = os.environ.get("LLM_ROUTER")
    os.environ["LLM_ROUTER"] = "rule"
    try:
        assert resolve_agent_id(message) == expected
    finally:
        if prev is None:
            os.environ.pop("LLM_ROUTER", None)
        else:
            os.environ["LLM_ROUTER"] = prev


def test_legacy_pipeline_intent_maps_scheduling():
    from metaforge.orchestrator.router import resolve_agent_route

    route = resolve_agent_route("x", intent="pipeline")
    assert route["agent_id"] == "scheduling"
