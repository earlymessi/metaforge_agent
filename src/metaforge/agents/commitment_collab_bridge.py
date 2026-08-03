"""Bridge: Orchestrator commitment intent → commitment_collab fixed pipeline."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep
from metaforge.commitment_collab.pipeline import run_commitment
from metaforge.commitment_collab.plan_steps import build_commitment_plan_steps


class CommitmentCollabBridge(BaseAgent):
    """Thin agent: fixed-stage commitment_collab pipeline."""

    agent_id = "commitment"
    name_zh = "交期承诺"
    allowed_tools: List[str] = []

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        self._plan_planner = "commitment_collab"
        return build_commitment_plan_steps(request)

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        return self.build_rule_plan(request)

    def run(
        self,
        request: AgentRequest,
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResponse:
        if on_step_start:
            on_step_start({"step_id": "collab", "tool": "commitment.collab.run"})

        out = run_commitment(
            message=request.message or "",
            context=request.context,
            params=request.params,
        )

        if on_step_done:
            on_step_done(
                {
                    "step_id": "collab",
                    "tool": "commitment.collab.run",
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
            plan_planner="commitment_collab",
            ui_action=out.get("ui_action"),
        )
