"""events 业务 Agent — 异常重排（插单多轮补全）。"""

from __future__ import annotations

import re
from typing import List, Optional

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep
from metaforge.tools.base import ToolContext

# 离线 fallback：能力问询（主路径由 plan prompt few-shot 处理）
_CATALOG_QUERY_RE = re.compile(
    r"支持哪些|有哪些事件|事件类型|能处理什么异常",
    re.I,
)


class EventsAgentRunner(BaseAgent):
    agent_id = "events"
    name_zh = "异常重排"
    allowed_tools = [
        "execution.get_state",
        "events.list_event_types",
        "events.parse_event",
        "events.merge_insert_job",
        "events.check_insert_job",
        "events.reschedule",
        "delivery.explain_impact",
        "delivery.compare_commitment",
    ]

    def _envelope_from_request(self, request: AgentRequest) -> Optional[dict]:
        env = request.params.get("event_envelope")
        if isinstance(env, dict) and env.get("event_type"):
            return env
        return None

    def _insert_intake_pending(self, request: AgentRequest) -> bool:
        from metaforge.orchestrator.router import has_pending_insert_job_intake

        return has_pending_insert_job_intake(request.context)

    def _attach_envelope_to_reschedule(self, request: AgentRequest, steps: List[PlanStep]) -> List[PlanStep]:
        envelope = self._envelope_from_request(request)
        if not envelope:
            return steps
        out: List[PlanStep] = []
        for step in steps:
            if step.tool == "events.reschedule":
                params = dict(step.params or {})
                params["event_envelope"] = envelope
                out.append(
                    PlanStep(step.step_id, step.tool, params, optional=step.optional)
                )
            else:
                out.append(step)
        return out

    def _after_tool_step(
        self,
        request: AgentRequest,
        step: PlanStep,
        result,
        tool_ctx: ToolContext,
        plan_log: List[dict],
    ) -> Optional[AgentResponse]:
        if step.tool != "events.check_insert_job":
            return None
        intake = tool_ctx.artifacts.get("insert_job_intake") or {}
        if intake.get("status") != "need_input":
            return None
        from metaforge.memory.manager import MemoryManager

        mm = MemoryManager.from_context(request.context)
        mm.set_working("events", "insert_job_intake", intake)
        return AgentResponse(
            status="need_input",
            agent_id=self.agent_id,
            summary_zh=intake.get("question_zh") or "请补充插单工序信息。",
            plan=plan_log,
            artifacts=dict(tool_ctx.artifacts),
            pending_action={
                "type": "insert_job_details",
                "missing_fields": intake.get("missing_fields") or [],
                "draft": intake.get("draft"),
            },
            plan_planner=getattr(self, "_plan_planner", "rule"),
        )

    def _is_default_reschedule_rule_plan(self, steps: List[PlanStep]) -> bool:
        tools = [s.tool for s in steps]
        return tools == [
            "execution.get_state",
            "events.parse_event",
            "events.check_insert_job",
            "events.reschedule",
            "delivery.compare_commitment",
            "delivery.explain_impact",
        ]

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        # 插单多轮补全：必须走 merge 规则链，禁止 GLM Plan 误生成 parse_event
        if self._insert_intake_pending(request):
            self._plan_planner = "rule"
            steps = self.build_rule_plan(request)
            return self._attach_envelope_to_reschedule(request, steps)
        rule_steps = self.build_rule_plan(request)
        if self._is_default_reschedule_rule_plan(rule_steps):
            self._plan_planner = "rule"
            steps = rule_steps
        else:
            steps = super().build_plan(request)
        if not self._insert_intake_pending(request):
            steps = [s for s in steps if s.tool != "events.merge_insert_job"]
        return self._attach_envelope_to_reschedule(request, steps)

    def build_plan_with_planner(self, request: AgentRequest) -> tuple[List[PlanStep], str]:
        """供测试/诊断：返回步骤与 planner 来源。"""
        steps = self.build_plan(request)
        return steps, getattr(self, "_plan_planner", "rule")

    def _insert_intake_plan(self, request: AgentRequest) -> List[PlanStep]:
        return [
            PlanStep("m1", "events.merge_insert_job", {"message": request.message}),
            PlanStep("m2", "events.check_insert_job", {"message": request.message}),
            PlanStep("s2", "events.reschedule", {}),
            PlanStep("s3", "delivery.explain_impact", {}),
        ]

    def _default_reschedule_plan(self, request: AgentRequest) -> List[PlanStep]:
        """离线默认重排链（无 NL 关键词分支；理解由 event/ plan prompt 负责）。"""
        steps: List[PlanStep] = [
            PlanStep("s0", "execution.get_state", {}, optional=True),
        ]
        envelope = self._envelope_from_request(request)
        if not request.params.get("skip_parse"):
            steps.append(
                PlanStep(
                    "s1",
                    "events.parse_event",
                    {"message": request.message, "event_envelope": envelope},
                )
            )
        steps.append(PlanStep("s1b", "events.check_insert_job", {"message": request.message}))
        reschedule_params: dict = {}
        if envelope:
            reschedule_params["event_envelope"] = envelope
        steps.append(PlanStep("s2", "events.reschedule", reschedule_params))
        steps.append(PlanStep("s3", "delivery.compare_commitment", {}, optional=True))
        steps.append(PlanStep("s4", "delivery.explain_impact", {}))
        return steps

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        if self._insert_intake_pending(request):
            return self._insert_intake_plan(request)

        msg = (request.message or "").strip()
        if msg and _CATALOG_QUERY_RE.search(msg):
            return [PlanStep("s0", "events.list_event_types", {})]

        return self._default_reschedule_plan(request)

    def run(
        self,
        request: AgentRequest,
        *,
        on_step_start=None,
        on_step_done=None,
    ) -> AgentResponse:
        from metaforge.orchestrator.llm_react import llm_react_enabled_for

        tool_ctx = self._tool_context(request)
        if request.message and "message" not in (tool_ctx.extras or {}):
            tool_ctx.extras["message"] = request.message
        extras = tool_ctx.extras or {}
        cached = extras.get("cached_plan_steps")
        if (
            llm_react_enabled_for(self.agent_id)
            and not (isinstance(cached, list) and cached)
            and not self._insert_intake_pending(request)
        ):
            return self._run_react_loop(
                request,
                tool_ctx,
                on_step_start=on_step_start,
                on_step_done=on_step_done,
            )
        return super().run(
            request,
            on_step_start=on_step_start,
            on_step_done=on_step_done,
        )

    def finalize(self, request, ctx, plan_log) -> AgentResponse:
        resp = super().finalize(request, ctx, plan_log)
        catalog = ctx.artifacts.get("event_type_catalog")
        if catalog:
            names = [e.get("name_zh") for e in catalog.get("event_types", [])[:6]]
            resp.summary_zh = "支持的事件类型：" + "、".join(names) + " 等。"
            return resp
        intake = ctx.artifacts.get("insert_job_intake") or {}
        if intake.get("status") == "need_input":
            resp.status = "need_input"
            resp.summary_zh = intake.get("question_zh") or resp.summary_zh
            resp.pending_action = {
                "type": "insert_job_details",
                "missing_fields": intake.get("missing_fields") or [],
                "draft": intake.get("draft"),
            }
            return resp
        summary = (ctx.artifacts.get("impact_summary") or {}).get("summary_zh")
        if summary:
            resp.summary_zh = summary
        impact = ctx.artifacts.get("impact_report") or (ctx.artifacts.get("impact_summary") or {}).get(
            "impact_report"
        )
        if impact:
            resp.ui_action = {
                "type": "navigate",
                "path": "/",
                "hint": "可在生产看板查看双甘特对比与实时执行甘特",
            }
        return resp
