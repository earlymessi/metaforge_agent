"""kitting 业务 Agent — 齐套顾问。

Plan 主路径：GLM ``plan`` prompt（``LLM_PLAN_AGENTS`` 含 kitting）。
``build_rule_plan`` 为离线 fallback，按 params.mode 映射 Tool 链。
"""

from __future__ import annotations

import re
from typing import List

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep

_SCHEDULE_THEN_PREDICT_RE = re.compile(r"先排程|先排产|预测物料|物料仿真", re.I)


class KittingAgentRunner(BaseAgent):
    agent_id = "kitting"
    name_zh = "齐套顾问"
    allowed_tools = [
        "material.check_static",
        "material.compute_delays",
        "material.predict",
        "scheduling.run",
        "kitting.build_report",
    ]

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        # 默认把「缺料影响/齐套检查」收敛到 check_only，避免误走 predict 分支要求 material_catalog。
        if not request.params.get("mode"):
            msg = (request.message or "").strip()
            request.params["mode"] = (
                "schedule_then_predict"
                if _SCHEDULE_THEN_PREDICT_RE.search(msg)
                else "check_only"
            )
        return super().build_plan(request)

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        mode = request.params.get("mode", "check_only")
        if mode == "check_only":
            return [
                PlanStep("s1", "material.check_static", {}),
                PlanStep("s2", "material.compute_delays", {}, optional=True),
                PlanStep("s3", "kitting.build_report", {}),
            ]
        if mode == "schedule_then_predict":
            return [
                PlanStep("s1", "scheduling.run", {"solvers": request.params.get("solvers", ["spt"])}),
                PlanStep("s2", "material.predict", {}),
                PlanStep("s3", "kitting.build_report", {}),
            ]
        # kit_then_schedule
        return [
            PlanStep("s1", "material.check_static", {}),
            PlanStep("s2", "material.compute_delays", {}, optional=True),
            PlanStep(
                "s3",
                "scheduling.run",
                {"solvers": request.params.get("solvers", ["spt", "ts"])},
            ),
            PlanStep("s4", "material.predict", {}, optional=True),
            PlanStep("s5", "kitting.build_report", {}),
        ]

    def finalize(self, request, ctx, plan_log) -> AgentResponse:
        resp = super().finalize(request, ctx, plan_log)
        kr = ctx.artifacts.get("kitting_report") or {}
        if kr.get("recommendation_zh"):
            resp.summary_zh = kr["recommendation_zh"]
        return resp
