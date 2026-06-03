"""Router 测试。"""

import os
from unittest.mock import patch

import pytest

from metaforge.orchestrator.router import resolve_agent_id, resolve_agent_route
from metaforge.plans.intent import is_plans_management_message


@pytest.fixture(autouse=True)
def _disable_llm_router():
    os.environ["LLM_ENABLED"] = "0"
    os.environ["LLM_ROUTER"] = "rule"
    yield


@pytest.mark.parametrize(
    "message,expected",
    [
        ("新建计划a", "plans"),
        ("创建一个新的计划", "plans"),
        ("列出计划", "plans"),
        ("把这个计划排程并保存落库", "scheduling"),
        ("随便排一下", "scheduling"),
        ("工单A加急", "events"),
        ("支持哪些异常", "events"),
    ],
)
def test_rule_fallback_when_llm_off(message, expected):
    assert resolve_agent_id(message) == expected


def test_plans_management_detector():
    assert is_plans_management_message("新建计划a")
    assert is_plans_management_message("创建一个新的计划")
    assert not is_plans_management_message("用禁忌搜索排程")


@pytest.mark.parametrize(
    "message,intent,agent_id,expect_router",
    [
        ("检查一下齐套能否开工", "kitting", "kitting", "llm"),
        ("对比一下交付优先和吞吐优先", "whatif", "whatif", "llm"),
        ("用禁忌搜索排程", "schedule", "scheduling", "llm"),
    ],
)
def test_llm_primary_routing(message, intent, agent_id, expect_router):
    fake = {
        "intent": intent,
        "agent_id": agent_id,
        "reason_zh": "mock",
        "router": "llm",
        "reasoning_steps": ["mock step"],
    }

    def _classify(m):
        assert m == message
        return fake

    with patch(
        "metaforge.orchestrator.llm_router.classify_message_with_llm",
        side_effect=_classify,
    ):
        with patch.dict(
            os.environ,
            {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_ROUTER": "glm"},
        ):
            route = resolve_agent_route(message)
    assert route["agent_id"] == agent_id
    assert route["router"] == expect_router
    assert route["intent"] == intent


def test_reschedule_guard_overrides_llm_misroute():
    """改交期/故障类消息：LLM 误判时由 guard 纠正为 events。"""
    with patch(
        "metaforge.orchestrator.llm_router.classify_message_with_llm",
        return_value={
            "intent": "commitment",
            "agent_id": "commitment",
            "router": "llm",
            "reason_zh": "mock wrong",
        },
    ):
        with patch.dict(
            os.environ,
            {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_ROUTER": "glm"},
        ):
            route = resolve_agent_route("3号机坏了重排")
    assert route["agent_id"] == "events"
    assert route["intent"] == "reschedule"
    assert route["router"] == "rule_override"


def test_plans_guard_overrides_llm_misroute():
    """计划库 CRUD：LLM 误判时由 guard 纠正为 plans。"""
    with patch(
        "metaforge.orchestrator.llm_router.classify_message_with_llm",
        return_value={
            "intent": "schedule",
            "agent_id": "scheduling",
            "router": "llm",
            "reason_zh": "mock wrong",
        },
    ):
        with patch.dict(
            os.environ,
            {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_ROUTER": "glm"},
        ):
            route = resolve_agent_route("新建计划b")
    assert route["agent_id"] == "plans"
    assert route["intent"] == "plans"
    assert route["router"] == "rule_override"


def test_due_date_change_routes_to_events_not_commitment():
    """「订单106交期改为20」必须进异常重排，不能进 commitment。"""
    with patch(
        "metaforge.orchestrator.llm_router.classify_message_with_llm",
        return_value={
            "intent": "commitment",
            "agent_id": "commitment",
            "router": "llm",
            "reason_zh": "mock wrong",
        },
    ):
        with patch.dict(
            os.environ,
            {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_ROUTER": "glm"},
        ):
            route = resolve_agent_route("订单106交期改为20")
    assert route["agent_id"] == "events"
    assert route["intent"] == "reschedule"
    assert route["router"] == "rule_override"


def test_llm_misroute_commitment_corrected_for_due_date_change():
    """含「交期改为」的改期指令不走 commitment。"""
    with patch(
        "metaforge.orchestrator.llm_router.classify_message_with_llm",
        return_value={
            "intent": "commitment",
            "agent_id": "commitment",
            "router": "llm",
            "reason_zh": "mock wrong",
        },
    ):
        with patch.dict(
            os.environ,
            {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_ROUTER": "glm"},
        ):
            route = resolve_agent_route("106号单交期改为20")
    assert route["agent_id"] == "events"
    assert route["intent"] == "reschedule"


def test_resolve_agent_id_explicit_intent():
    assert resolve_agent_id("随便", intent="commitment") == "commitment"


def test_resolve_unknown_intent():
    with pytest.raises(ValueError):
        resolve_agent_id(intent="invalid")
