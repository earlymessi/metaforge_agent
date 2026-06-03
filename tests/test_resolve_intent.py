"""resolve_schedule_intent 测试。"""

import os
from unittest.mock import patch

from metaforge.scheduling.resolve_intent import resolve_schedule_intent


def setup_function():
    os.environ.pop("LLM_ENABLED", None)
    os.environ.pop("ZHIPU_API_KEY", None)


def test_resolve_uses_rule_when_llm_disabled():
    os.environ["LLM_ENABLED"] = "0"
    result = resolve_schedule_intent({"message": "禁忌搜索排程"}, extras={})
    assert result["planner"] == "rule"
    assert result["solvers"]


@patch("metaforge.scheduling.resolve_intent.parse_message_with_llm")
def test_resolve_uses_llm_when_enabled(mock_llm):
    os.environ["LLM_ENABLED"] = "1"
    os.environ["ZHIPU_API_KEY"] = "test"
    mock_llm.return_value = {
        "message": "随便排",
        "solvers": ["spt"],
        "strategy_id": "balanced",
        "strategy_name": "综合平衡",
        "weights": {
            "makespan": 1.0,
            "weighted_tardiness_total": 0.5,
            "energy_cost": 0.05,
            "machine_busy_cv": 10.0,
        },
        "summary_zh": "ok",
        "planner": "llm",
        "enforce_material": False,
        "benchmark_file": None,
        "solver_match_notes": [],
        "strategy_match_note": "",
    }
    result = resolve_schedule_intent({"message": "随便排"}, extras={})
    assert result["planner"] == "llm"


@patch("metaforge.scheduling.resolve_intent.parse_message_with_llm", side_effect=Exception("timeout"))
def test_resolve_fallback_on_llm_error(mock_llm):
    os.environ["LLM_ENABLED"] = "1"
    os.environ["ZHIPU_API_KEY"] = "test"
    os.environ["LLM_FALLBACK"] = "rule"
    result = resolve_schedule_intent({"message": "禁忌搜索"}, extras={})
    assert result["planner"] == "rule_fallback"
    assert "llm_error" in result
