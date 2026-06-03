"""commitment 业务 Agent — 交期承诺。

Plan 主路径：GLM plan prompt；``build_rule_plan`` 为离线 fallback（assess + 可选话术）。
"""

from __future__ import annotations

from typing import List

from metaforge.agents.base import AgentRequest, BaseAgent, PlanStep


class CommitmentAgentRunner(BaseAgent):
    agent_id = "commitment"
    name_zh = "交期承诺"
    allowed_tools = [
        "scheduling.run",
        "delivery.assess",
        "delivery.customer_script",
    ]

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        msg = (request.message or "")
        arts = request.context.get("artifacts") or {}
        has_schedule = bool(arts.get("schedule_results"))
        want_script = any(k in msg for k in ("话术", "客户", "怎么说", "对外", "沟通"))

        steps: List[PlanStep] = []
        # 默认不重新排程；仅显式 run_schedule_first 且尚无排程结果时才可选跑 scheduling.run
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
