"""Preview/plan steps for plans_collab (reuse resolve_plan_intent)."""

from __future__ import annotations

from typing import List, Tuple

from metaforge.agents.base import AgentRequest, PlanStep
from metaforge.plans.resolve_intent import intent_to_plan_steps, resolve_plan_intent


def resolve_and_build_plan_steps(
    request: AgentRequest,
) -> Tuple[List[PlanStep], dict, str]:
    intent, planner = resolve_plan_intent(request.message, params=request.params)
    steps = intent_to_plan_steps(intent)
    return steps, intent, planner


def build_plans_plan_steps(request: AgentRequest) -> List[PlanStep]:
    steps, _intent, _planner = resolve_and_build_plan_steps(request)
    return steps
