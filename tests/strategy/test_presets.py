from metaforge.strategy.presets import list_presets, strategy_from_preset


def test_list_presets_has_six():
    ids = {p["id"] for p in list_presets()}
    assert ids >= {"balanced", "delivery", "cost", "balance_load", "makespan", "throughput"}


def test_strategy_from_preset_delivery_has_tardiness_weight():
    s = strategy_from_preset("delivery")
    assert s.base_template == "delivery"
    assert s.objectives["weighted_tardiness_total"] >= s.objectives["makespan"]
    assert s.generated_by == "preset"
