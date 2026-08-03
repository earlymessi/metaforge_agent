"""Golden: preset objectives stay aligned with legacy STRATEGY_TEMPLATES."""

from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES
from metaforge.strategy.presets import strategy_from_preset


def test_delivery_preset_objectives_match_strategy_templates():
    delivery_tpl = next(t for t in STRATEGY_TEMPLATES if t["id"] == "delivery")
    strategy = strategy_from_preset("delivery")
    assert strategy.objectives == delivery_tpl["weights"]
