"""Router GLM 测试。"""

import pytest
from unittest.mock import patch

from metaforge.orchestrator.llm_router import classify_message_with_llm, normalize_router_payload
from metaforge.orchestrator.router import resolve_agent_route


def test_normalize_router_payload_unknown_intent():
    out = normalize_router_payload({"intent": "bogus", "reason_zh": "x"})
    assert out["intent"] == "schedule"
    assert out["agent_id"] == "scheduling"


def test_normalize_router_payload_unsupported():
    out = normalize_router_payload(
        {
            "intent": "unsupported",
            "scope_category": "mes_execution",
            "reason_zh": "MES 执行",
        },
        message="哪个订单在执行",
    )
    assert out.get("out_of_scope") is True
    assert out["intent"] == "unsupported"
    assert out["agent_id"] is None


@patch("metaforge.orchestrator.llm_router.invoke")
def test_classify_message_with_llm(mock_invoke):
    mock_invoke.return_value = {
        "intent": "reschedule",
        "agent_id": "events",
        "reason_zh": "设备故障重排",
        "router": "llm",
    }
    with patch.dict("os.environ", {"ZHIPU_API_KEY": "k", "ZHIPU_MODEL": "glm-4.5-air"}):
        data = classify_message_with_llm("3号机坏了要重排")
    assert data["agent_id"] == "events"
    assert data["router"] == "llm"


@patch("metaforge.orchestrator.llm_router.classify_message_with_llm")
def test_resolve_agent_route_llm(mock_cls):
    mock_cls.return_value = {
        "agent_id": "kitting",
        "intent": "kitting",
        "router": "llm",
        "reason_zh": "齐套",
    }
    with patch.dict(
        "os.environ",
        {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_ROUTER": "glm"},
    ):
        route = resolve_agent_route("检查一下物料齐套")
    assert route["agent_id"] == "kitting"
    assert route["router"] == "llm"


@patch("metaforge.orchestrator.llm_router.classify_message_with_llm", side_effect=RuntimeError("api down"))
def test_resolve_agent_route_fallback(mock_cls):
    with patch.dict(
        "os.environ",
        {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_FALLBACK": "rule", "LLM_ROUTER": "glm"},
    ):
        route = resolve_agent_route("3号机坏了重排")
    assert route["router"] == "rule_fallback"
    assert route["agent_id"] == "events"
