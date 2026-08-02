from __future__ import annotations

from typing import Any, Dict, List

from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES
from metaforge.strategy.models import SchedulingStrategy

_STRATEGY_BY_ID = {t["id"]: t for t in STRATEGY_TEMPLATES}


def list_presets() -> List[Dict[str, Any]]:
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "weights": dict(t["weights"]),
            "objectives": dict(t["weights"]),
        }
        for t in STRATEGY_TEMPLATES
    ]


def strategy_from_preset(preset_id: str) -> SchedulingStrategy:
    tpl = _STRATEGY_BY_ID.get(preset_id)
    if tpl is None:
        raise ValueError(f"Unknown preset id: {preset_id!r}")
    return SchedulingStrategy(
        base_template=preset_id,
        objectives=dict(tpl["weights"]),
        generated_by="preset",
    )
