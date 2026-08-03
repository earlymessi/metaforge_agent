"""Bridge: Orchestrator plans intent → plans_collab fixed pipeline."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep
from metaforge.plans_collab.pipeline import run_plans
from metaforge.plans_collab.plan_steps import resolve_and_build_plan_steps


class PlansCollabBridge(BaseAgent):
    """Thin agent: plans_collab pipeline (replaces PlansAgentRunner)."""

    agent_id = "plans"
    name_zh = "计划管理"
    allowed_tools: List[str] = []

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        steps, _intent, planner = resolve_and_build_plan_steps(request)
        self._plan_planner = "plans_collab"
        self._intent_planner = planner
        return steps

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        """Skip LLM Tool-plan — intent resolve + fixed steps only."""
        return self.build_rule_plan(request)

    def run(
        self,
        request: AgentRequest,
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResponse:
        if on_step_start:
            on_step_start({"step_id": "collab", "tool": "plans.collab.run"})

        out = run_plans(
            message=request.message or "",
            context=request.context,
            params=request.params,
        )

        if on_step_done:
            on_step_done(
                {
                    "step_id": "collab",
                    "tool": "plans.collab.run",
                    "status": out.get("status"),
                }
            )

        return AgentResponse(
            status=out.get("status") or "failed",
            agent_id=self.agent_id,
            summary_zh=out.get("summary_zh") or "",
            plan=list(out.get("plan") or []),
            artifacts=dict(out.get("artifacts") or {}),
            pending_action=out.get("pending_action"),
            error=out.get("error"),
            plan_planner="plans_collab",
            ui_action=out.get("ui_action"),
        )
