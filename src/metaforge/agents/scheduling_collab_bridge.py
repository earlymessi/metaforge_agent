"""Bridge: Orchestrator scheduling intent → planning_collab Supervisor."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep
from metaforge.planning_collab.supervisor import run_collab


class SchedulingCollabBridge(BaseAgent):
    """Thin agent that replaces SchedulingAgentRunner when PLANNING_COLLAB_V1=1."""

    agent_id = "scheduling"
    name_zh = "智能排程"
    allowed_tools: List[str] = []

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        return []

    def run(
        self,
        request: AgentRequest,
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResponse:
        params = dict(request.params or {})
        ctx = dict(request.context or {})
        extras = dict(ctx.get("extras") or {})

        jobs = params.get("jobs") or ctx.get("jobs") or extras.get("jobs") or []
        machines = (
            params.get("machines")
            or ctx.get("machines")
            or extras.get("machines")
            or []
        )
        user_goal = (
            (request.message or "").strip()
            or str(params.get("user_goal") or "")
            or "综合平衡排程"
        )
        skip_hitl = bool(params.get("skip_strategy_hitl", True))
        problem = params.get("problem") or ctx.get("problem")

        if on_step_start:
            on_step_start({"step_id": "collab", "tool": "planning.collab.run"})

        out = run_collab(
            user_goal=user_goal,
            jobs=jobs,
            machines=machines,
            skip_strategy_hitl=skip_hitl,
            llm_client=params.get("llm_client") or extras.get("llm_client"),
            problem=problem,
        )

        if on_step_done:
            on_step_done(
                {
                    "step_id": "collab",
                    "tool": "planning.collab.run",
                    "status": out.get("status"),
                }
            )

        status = out.get("status") or "FAILED"
        if status == "FAILED":
            return AgentResponse(
                status="failed",
                agent_id=self.agent_id,
                summary_zh="协同排产失败。",
                plan=[
                    {
                        "step_id": "collab",
                        "tool": "planning.collab.run",
                        "status": "failed",
                    }
                ],
                artifacts={"collab": out, **(out.get("artifacts") or {})},
                error=str(out.get("error") or out.get("warnings") or "collab failed"),
                plan_planner="planning_collab",
            )

        pending = None
        summary = "协同排产完成。"
        if status == "WAITING_APPROVAL":
            summary = "策略待确认（HITL）。"
            pending = {
                "type": "strategy_hitl",
                "run_id": out.get("run_id"),
                "approve_path": f"/api/planning/runs/{out.get('run_id')}/strategy/approve",
            }
        elif status == "COMPLETED":
            rec = (out.get("package") or {}).get("recommended_schedule_id")
            summary = f"协同排产完成，推荐方案：{rec or '无'}。"

        return AgentResponse(
            status="success",
            agent_id=self.agent_id,
            summary_zh=summary,
            plan=[
                {
                    "step_id": "collab",
                    "tool": "planning.collab.run",
                    "status": "done",
                }
            ],
            artifacts={
                "collab": out,
                "package": out.get("package"),
                "order_analysis": (out.get("artifacts") or {}).get("order_analysis"),
                "constraint_analysis": (out.get("artifacts") or {}).get(
                    "constraint_analysis"
                ),
                "resource_analysis": (out.get("artifacts") or {}).get(
                    "resource_analysis"
                ),
            },
            pending_action=pending,
            plan_planner="planning_collab",
        )
