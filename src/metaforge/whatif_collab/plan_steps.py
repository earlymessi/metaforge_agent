"""Variant construction + preview plan steps for whatif_collab."""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES
from metaforge.agents.base import AgentRequest, PlanStep

_STRATEGY_BY_ID = {t["id"]: t for t in STRATEGY_TEMPLATES}


def build_variants_from_params(request: AgentRequest) -> List[Dict[str, Any]]:
    explicit = request.params.get("variants")
    if explicit:
        return list(explicit)

    strategy_ids = request.params.get("strategy_ids") or ["delivery", "throughput"]
    solvers = request.params.get("solvers") or ["spt", "ts"]
    variants: List[Dict[str, Any]] = []
    for sid in strategy_ids[:4]:
        tpl = _STRATEGY_BY_ID.get(sid)
        if not tpl:
            continue
        variants.append(
            {
                "variant_id": sid,
                "label": tpl.get("name", sid),
                "scheduling": {
                    "strategy_id": sid,
                    "solvers": list(solvers),
                    "weights": dict(tpl["weights"]),
                    "enforce_material": bool(
                        request.params.get("enforce_material", False)
                    ),
                },
                "event": None,
            }
        )
    if len(variants) < 2 and STRATEGY_TEMPLATES:
        for tpl in STRATEGY_TEMPLATES[:2]:
            if tpl["id"] not in {v["variant_id"] for v in variants}:
                variants.append(
                    {
                        "variant_id": tpl["id"],
                        "label": tpl["name"],
                        "scheduling": {
                            "strategy_id": tpl["id"],
                            "solvers": list(solvers),
                            "weights": dict(tpl["weights"]),
                        },
                        "event": None,
                    }
                )
    return variants


def build_whatif_plan_steps(request: AgentRequest) -> List[PlanStep]:
    variants = build_variants_from_params(request)
    return [
        PlanStep(
            "s1",
            "compare.variants",
            {
                "variants": variants,
                "recommend_metric": request.params.get(
                    "recommend_metric", "best_score"
                ),
            },
        ),
    ]
