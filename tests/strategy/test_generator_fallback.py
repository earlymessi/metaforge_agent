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
    assert s.generated_by == "rule_fallback"
    assert meta["fallback"] is True
    assert "A" in s.critical_orders
    hard_types = {c.type for c in s.hard_constraints}
    soft_types = {c.type for c in s.soft_constraints}
    assert "order_on_time" in hard_types
    assert "reduce_changeover" in soft_types


class _FakeLLMClient:
    def __init__(self, payload):
        self._payload = payload

    def complete_json(self, prompt, attempt=0):
        return self._payload


def test_llm_invalid_hard_type_falls_back_to_rules():
    invalid_payload = {
        "base_template": "delivery",
        "objectives": {"weighted_tardiness_total": 1.0},
        "hard_constraints": [{"type": "not_a_real_type", "job_id": "A"}],
        "soft_constraints": [],
        "critical_orders": [],
        "generated_by": "llm",
    }
    s, meta = generate_strategy(
        user_goal="优先交付，保证客户A按期，减少换型",
        jobs=[{"job_id": "A", "customer": "A", "due_date": 20}],
        machines=["M01"],
        llm_client=_FakeLLMClient(invalid_payload),
    )
    assert s.generated_by == "rule_fallback"
    assert meta["fallback"] is True
    assert meta.get("llm_validation_failed") is True
    assert any("not_a_real_type" in err for err in meta.get("validation_errors", []))
    hard_types = {c.type for c in s.hard_constraints}
    assert "not_a_real_type" not in hard_types
    assert "order_on_time" in hard_types
    assert meta["validation_ok"] is True
