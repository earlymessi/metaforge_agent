"""路由后验 Guard 单测。"""

from metaforge.orchestrator.router import (
    _apply_route_guards,
    is_commitment_assessment_message,
    is_events_catalog_message,
    is_kitting_material_message,
    is_kitting_schedule_then_predict_message,
    is_whatif_compare_message,
    resolve_agent_id,
)


def test_is_kitting_material_message_shortage_delay():
    assert is_kitting_material_message("缺料会导致哪些工单延期？")


def test_kitting_guard_overrides_commitment():
    route = {
        "agent_id": "commitment",
        "intent": "commitment",
        "router": "llm",
        "reason_zh": "误判",
    }
    out = _apply_route_guards(route, "缺料会导致哪些工单延期？")
    assert out["agent_id"] == "kitting"
    assert out["router"] == "rule_override"


def test_rule_fallback_shortage_goes_kitting():
    """LLM 关闭时规则回退也应进 kitting。"""
    assert resolve_agent_id("缺料会导致哪些工单延期？") == "kitting"


def test_rule_fallback_long_question_goes_kitting():
    msg = "缺料会导致哪些工单延期？哪些工单可能延期？"
    assert resolve_agent_id(msg) == "kitting"


def test_commitment_delay_inquiry_routes_commitment():
    from metaforge.orchestrator.router import resolve_agent_id

    assert resolve_agent_id("哪些工单可能延期") == "commitment"
    assert resolve_agent_id("哪些订单可能会延期") == "commitment"


def test_rule_fallback_persist_goes_scheduling():
    from metaforge.orchestrator.router import resolve_agent_id

    assert resolve_agent_id("把这个计划排程并保存落库") == "scheduling"


def test_explicit_pipeline_intent_maps_scheduling():
    from metaforge.orchestrator.router import resolve_agent_route

    route = resolve_agent_route("test", intent="pipeline")
    assert route["agent_id"] == "scheduling"
    assert route["intent"] == "schedule"


def test_events_catalog_guard_overrides_plans():
    route = {
        "agent_id": "plans",
        "intent": "plans",
        "router": "llm",
    }
    out = _apply_route_guards(route, "支持哪些异常")
    assert out["agent_id"] == "events"
    assert is_events_catalog_message("支持哪些异常")


def test_kitting_schedule_predict_guard():
    route = {
        "agent_id": "scheduling",
        "intent": "schedule",
        "router": "llm",
    }
    msg = "先排程再预测物料消耗"
    assert is_kitting_schedule_then_predict_message(msg)
    out = _apply_route_guards(route, msg)
    assert out["agent_id"] == "kitting"


def test_whatif_guard_solver_compare():
    route = {
        "agent_id": "scheduling",
        "intent": "schedule",
        "router": "llm",
    }
    msg = "假设用 SPT 和禁忌搜索各跑一遍，对比一下"
    assert is_whatif_compare_message(msg)
    out = _apply_route_guards(route, msg)
    assert out["agent_id"] == "whatif"


def test_package_route_corrects_scheduling_on_material_question():
    from metaforge.orchestrator.router import _package_route

    route = _package_route(
        "scheduling",
        "规则回退：未启用 GLM 时默认智能排程",
        "rule_fallback",
        "缺料会导致哪些工单延期？",
        llm_error="timeout",
    )
    assert route["agent_id"] == "kitting"
    assert route["router"] in ("rule_fallback", "rule_override")


def test_commitment_assessment_overrides_scheduling():
    assert is_commitment_assessment_message("评估一下当前排程的交付情况")
    route = {
        "agent_id": "scheduling",
        "intent": "schedule",
        "router": "llm",
    }
    out = _apply_route_guards(route, "客户问能不能5月15日交货")
    assert out["agent_id"] == "commitment"


def test_whatif_strategy_compare_phrases():
    assert is_whatif_compare_message("如果按交期优先和按产能优先排，哪个更好")
    assert is_whatif_compare_message("对比交付优先和产能优先")


def test_kitting_on_time_start_message():
    assert is_kitting_material_message("这批订单能否按时开工")
    route = {"agent_id": "scheduling", "intent": "schedule", "router": "llm"}
    out = _apply_route_guards(route, "这批订单能否按时开工")
    assert out["agent_id"] == "kitting"


def test_parse_router_unsupported_mes_execution():
    from metaforge.orchestrator.llm.parsers import parse_router

    out = parse_router(
        {
            "intent": "unsupported",
            "scope_category": "mes_execution",
            "reason_zh": "MES 现场执行监控",
            "reasoning_steps": ["问执行状态", "非交期评估"],
        },
        message="目前的执行情况如何 在进行哪个订单",
    )
    assert out.get("out_of_scope") is True
    assert out["scope_category"] == "mes_execution"
    assert out["agent_id"] is None
    assert "生产看板" in (out.get("guidance_zh") or "")


def test_resolve_agent_route_llm_unsupported():
    from unittest.mock import patch

    from metaforge.orchestrator.router import resolve_agent_route

    with patch("metaforge.orchestrator.llm_router.classify_message_with_llm") as mock_cls:
        mock_cls.return_value = {
            "out_of_scope": True,
            "agent_id": None,
            "intent": "unsupported",
            "scope_category": "mes_execution",
            "router": "llm",
            "reason_zh": "MES 执行态",
            "guidance_zh": "请去生产看板",
        }
        with patch.dict(
            "os.environ",
            {"LLM_ENABLED": "1", "ZHIPU_API_KEY": "k", "LLM_ROUTER": "glm"},
        ):
            route = resolve_agent_route("目前执行情况如何")
    assert route.get("out_of_scope") is True
    assert route["scope_category"] == "mes_execution"
