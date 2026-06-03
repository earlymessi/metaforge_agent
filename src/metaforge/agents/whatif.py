"""whatif 业务 Agent — 方案对比。

Plan 主路径：GLM plan prompt；``build_rule_plan`` 为离线 fallback（compare.variants）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES

_STRATEGY_BY_ID = {t["id"]: t for t in STRATEGY_TEMPLATES}
from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep


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
                    "enforce_material": bool(request.params.get("enforce_material", False)),
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


class WhatifAgentRunner(BaseAgent):
    agent_id = "whatif"
    name_zh = "方案对比"
    allowed_tools = [
        "scheduling.run",
        "events.reschedule",
        "compare.variants",
        "delivery.assess",
    ]

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        variants = build_variants_from_params(request)
        return [
            PlanStep(
                "s1",
                "compare.variants",
                {
                    "variants": variants,
                    "recommend_metric": request.params.get("recommend_metric", "best_score"),
                },
            ),
        ]

    def finalize(self, request, ctx, plan_log) -> AgentResponse:
        resp = super().finalize(request, ctx, plan_log)
        what_if = ctx.artifacts.get("what_if") or {}
        reason = what_if.get("recommendation_reason_zh")
        if reason:
            resp.summary_zh = reason
        if what_if.get("insignificant_diff"):
            resp.summary_zh = (resp.summary_zh or "") + "（方案差异不显著，可任选其一。）"
        return resp
