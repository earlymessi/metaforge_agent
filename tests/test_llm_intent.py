"""llm_intent 测试。"""

from unittest.mock import patch

from metaforge.scheduling.llm_intent import normalize_llm_payload, parse_message_with_llm


def test_normalize_maps_unknown_solver_and_strategy():
    raw = {
        "solvers": ["ts", "not_a_solver"],
        "strategy_id": "not_exist",
        "weights": {},
        "enforce_material": True,
        "summary_zh": "测试",
    }
    out = normalize_llm_payload(raw)
    assert "ts" in out["solvers"]
    assert "not_a_solver" not in out["solvers"]
    assert out["strategy_id"] == "balanced"
    assert "makespan" in out["weights"]
    assert out["planner"] == "llm"


@patch("metaforge.scheduling.llm_intent.invoke")
def test_parse_message_with_llm(mock_invoke):
    from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES

    delivery = next(t for t in STRATEGY_TEMPLATES if t["id"] == "delivery")
    mock_invoke.return_value = {
        "message": "交付优先快速排程",
        "solvers": ["spt"],
        "strategy_id": "delivery",
        "weights": delivery["weights"],
        "enforce_material": False,
        "summary_zh": "交付优先用SPT",
        "strategy_name": delivery["name"],
        "solver_match_notes": [],
        "strategy_match_note": "",
        "benchmark_file": None,
        "planner": "llm",
    }
    with patch.dict("os.environ", {"ZHIPU_API_KEY": "k", "ZHIPU_MODEL": "glm-4.5-air"}):
        out = parse_message_with_llm("交付优先快速排程")
    assert out["planner"] == "llm"
    assert out["solvers"] == ["spt"]
    assert out["strategy_id"] == "delivery"
