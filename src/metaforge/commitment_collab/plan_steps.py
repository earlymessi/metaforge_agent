"""Preview/plan steps mirroring commitment_collab fixed stages."""

from __future__ import annotations

from typing import List

from metaforge.agents.base import AgentRequest, PlanStep

_SCRIPT_KEYS = ("话术", "客户", "怎么说", "对外", "沟通")


def want_customer_script(message: str = "") -> bool:
    return any(k in (message or "") for k in _SCRIPT_KEYS)


def build_commitment_plan_steps(request: AgentRequest) -> List[PlanStep]:
    msg = request.message or ""
    arts = (request.context or {}).get("artifacts") or {}
    has_schedule = bool(arts.get("schedule_results"))
    want_script = want_customer_script(msg)

    steps: List[PlanStep] = []
    if request.params.get("run_schedule_first") and not has_schedule:
        steps.append(
            PlanStep(
                "s0",
                "scheduling.run",
                {"solvers": request.params.get("solvers", ["spt"])},
                optional=True,
            )
        )
    steps.append(PlanStep("s1", "delivery.assess", {}))
    if want_script:
        steps.append(PlanStep("s2", "delivery.customer_script", {}))
    return steps
