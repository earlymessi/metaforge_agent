from metaforge.strategy.context_builder import build_for_strategy_generation
from metaforge.strategy.generator import generate_strategy


def test_context_builder_omits_full_gantt():
    ctx = build_for_strategy_generation(
        user_goal="保证A按期",
        jobs=[{"job_id": "A", "due_date": 10, "priority": 5}],
        machines=["M01", "M02"],
        gantt_data=[{"job": "A", "op": 0}] * 500,
        bom={"items": list(range(200))},
    )
    blob = str(ctx)
    assert "保证A按期" in blob
    assert blob.count("job") < 50  # 摘要而非全量翻倍
    assert "items" not in blob or "bom_item_count" in blob


def test_rule_fallback_delivery_keywords():
    s, meta = generate_strategy(
        user_goal="优先交付，保证客户A按期，减少换型",
        jobs=[{"job_id": "A", "customer": "A", "due_date": 20}],
        machines=["M01"],
        llm_client=None,  # 强制规则
    )
    assert s.generated_by in ("rule_fallback", "preset", "llm")
    assert s.base_template in ("delivery", "balanced") or s.objectives.get("weighted_tardiness_total", 0) > 0
    assert meta.get("fallback") is True or s.generated_by == "rule_fallback"
