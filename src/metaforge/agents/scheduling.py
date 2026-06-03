"""scheduling 业务 Agent — 智能排程（含排程落库 / HITL）。

Plan 主路径：GLM ``plan`` prompt（``LLM_PLAN_ENABLED=1``）。
``build_rule_plan`` 为离线 fallback：调用 ``resolve_schedule_intent`` 得结构化 intent，
再按 intent_type 映射 Tool 链；``wants_persist_request`` 时追加交期评估与 ``propose_persist``。
编排器在成功后亦可调用 ``_maybe_persist_schedule_to_plan``（与 Agent 内 propose 二选一生效）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from metaforge.agents.base import AgentRequest, AgentResponse, BaseAgent, PlanStep
from metaforge.agents.persist_intent import wants_persist_request
from metaforge.scheduling.context import ContextManager
from metaforge.scheduling.intent_types import ScheduleIntentType
from metaforge.scheduling.resolve_intent import resolve_schedule_intent

_CATALOG_INTENTS = frozenset(
    {
        ScheduleIntentType.LIST_SOLVERS.value,
        ScheduleIntentType.LIST_STRATEGIES.value,
    }
)

_CLARIFY_INTENTS = frozenset(
    {
        ScheduleIntentType.CLARIFICATION.value,
        ScheduleIntentType.HELP.value,
        ScheduleIntentType.UNKNOWN.value,
        ScheduleIntentType.GET_LAST_RESULT.value,
        ScheduleIntentType.SET_DEFAULT_STRATEGY.value,
        ScheduleIntentType.SET_DEFAULT_SOLVER.value,
        ScheduleIntentType.TOGGLE_MATERIAL.value,
    }
)

_CATALOG_QUERY_RE = re.compile(
    r"有哪些算法|算法.*(?:目录|列表)|求解器.*(?:目录|列表)|支持什么算法",
    re.I,
)
_COMPARE_RUN_RE = re.compile(
    r"遗传|模拟退火|禁忌|SPT|对比.*算法|算法.*对比|对比一下|各跑一遍|和.*对比",
    re.I,
)
_FAST_RUN_RE = re.compile(r"快速|先出.*结果", re.I)
_RUN_PLAN_TOOLS = frozenset({"scheduling.parse_intent", "scheduling.run"})


def _wants_run_plan(message: str, params: Dict[str, Any]) -> bool:
    msg = (message or "").strip()
    if params.get("skip_parse") or params.get("_skip_vague_clarify"):
        return True
    if params.get("intent") == "schedule" or params.get("intent") == "pipeline":
        return True
    if _CATALOG_QUERY_RE.search(msg):
        return False
    if _COMPARE_RUN_RE.search(msg) or _FAST_RUN_RE.search(msg):
        return True
    if msg in ("排程", "排产") or (len(msg) <= 8 and "排" in msg and "计划" not in msg):
        return True
    return False


def _default_run_plan_steps(message: str) -> List[PlanStep]:
    return [
        PlanStep("s1", "scheduling.parse_intent", {"message": message}),
        PlanStep("s2", "scheduling.run", {}),
    ]


def coerce_scheduling_plan_steps(
    steps: List[PlanStep], request: AgentRequest
) -> List[PlanStep]:
    """LLM Plan 纠偏：对比/快速排程/显式 schedule 不应仅 list_catalog 或 ask_clarification。"""
    if request.params.get("confirm_token"):
        return steps
    tools = [s.tool for s in steps]
    if not _wants_run_plan(request.message or "", request.params):
        return steps
    if _RUN_PLAN_TOOLS.issubset(set(tools)):
        return steps
    if len(tools) == 1 and tools[0] == "scheduling.list_catalog":
        if _CATALOG_QUERY_RE.search(request.message or ""):
            return steps
    if "scheduling.ask_clarification" in tools or (
        len(tools) == 1 and tools[0] == "scheduling.list_catalog"
    ):
        out = _default_run_plan_steps(request.message or "")
        if wants_persist_request(request.message or "", request.params):
            out = _maybe_prepend_load_plan(out, request)
            return _append_persist_steps(out)
        return out
    return steps


def _clarification_step(resolved: Dict[str, Any], itype: str) -> PlanStep:
    return PlanStep(
        "s0",
        "scheduling.ask_clarification",
        {
            "question": resolved.get("clarification_question"),
            "clarification_context": resolved.get("clarification_context"),
            "intent_type": itype,
            "_pre_resolved": resolved,
        },
    )


def _steps_from_resolved(resolved: Dict[str, Any], message: str) -> List[PlanStep]:
    """intent_type → Tool 链（结构性映射，非 NL 规则）。"""
    itype = resolved.get("intent_type") or ScheduleIntentType.RUN_SCHEDULE.value
    if itype in _CATALOG_INTENTS:
        return [PlanStep("s0", "scheduling.list_catalog", {})]
    if itype in _CLARIFY_INTENTS:
        return [_clarification_step(resolved, itype)]
    return [
        PlanStep(
            "s1",
            "scheduling.parse_intent",
            {"message": message, "_pre_resolved": resolved},
        ),
        PlanStep("s2", "scheduling.run", {}),
    ]


def _append_persist_steps(steps: List[PlanStep]) -> List[PlanStep]:
    out = list(steps)
    out.append(PlanStep("sp1", "delivery.assess", {}))
    out.append(PlanStep("sp2", "data.propose_persist", {}))
    return out


def _maybe_prepend_load_plan(steps: List[PlanStep], request: AgentRequest) -> List[PlanStep]:
    extras = request.context.get("extras") or {}
    if extras.get("loaded_plan_id") or request.context.get("plan_id"):
        return [PlanStep("s0", "data.load_plan", {})] + steps
    return steps


class SchedulingAgentRunner(BaseAgent):
    agent_id = "scheduling"
    name_zh = "智能排程"

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        steps = super().build_plan(request)
        return coerce_scheduling_plan_steps(steps, request)

    allowed_tools = [
        "scheduling.parse_intent",
        "scheduling.run",
        "scheduling.list_catalog",
        "scheduling.ask_clarification",
        "data.load_plan",
        "delivery.assess",
        "data.propose_persist",
        "data.confirm_persist",
    ]

    def _session_id(self, request: AgentRequest) -> str:
        return (
            request.context.get("session_id")
            or request.params.get("session_id")
            or "default"
        )

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        if request.params.get("confirm_token"):
            return [
                PlanStep(
                    "c1",
                    "data.confirm_persist",
                    {"confirm_token": request.params["confirm_token"]},
                )
            ]

        persist = wants_persist_request(request.message or "", request.params)

        if persist and not request.params.get("confirm_token"):
            merge_params = dict(request.params)
            merge_params.setdefault("message", request.message)
            resolved = resolve_schedule_intent(
                merge_params,
                extras=request.context.get("extras") or {},
                benchmark_file=request.context.get("benchmark_file"),
                session_id=self._session_id(request),
                persist_context=False,
            )
            request.params["_pre_resolved"] = resolved
            itype = resolved.get("intent_type") or ScheduleIntentType.RUN_SCHEDULE.value
            if itype == ScheduleIntentType.CLARIFICATION.value:
                steps = [
                    PlanStep(
                        "s1",
                        "scheduling.run",
                        {
                            "solvers": resolved.get("solvers") or ["spt", "ts"],
                            "weights": resolved.get("weights"),
                        },
                    ),
                ]
            else:
                steps = _steps_from_resolved(resolved, request.message or "")
            steps = _maybe_prepend_load_plan(steps, request)
            return _append_persist_steps(steps)

        if request.params.get("skip_parse"):
            steps = [
                PlanStep(
                    "s1",
                    "scheduling.run",
                    {
                        "solvers": request.params.get("solvers"),
                        "weights": request.params.get("weights"),
                    },
                )
            ]
        else:
            merge_params = dict(request.params)
            merge_params.setdefault("message", request.message)
            resolved = resolve_schedule_intent(
                merge_params,
                extras=request.context.get("extras") or {},
                benchmark_file=request.context.get("benchmark_file"),
                session_id=self._session_id(request),
                persist_context=False,
            )
            request.params["_pre_resolved"] = resolved
            steps = _steps_from_resolved(resolved, request.message or "")

        if persist:
            steps = _maybe_prepend_load_plan(steps, request)
            steps = _append_persist_steps(steps)
        return steps

    def finalize(self, request: AgentRequest, ctx, plan_log) -> AgentResponse:
        if request.params.get("confirm_token"):
            pr = ctx.artifacts.get("persist_result") or ctx.artifacts.get("persist_validation")
            if pr and pr.get("status") == "success":
                return AgentResponse(
                    status="success",
                    agent_id=self.agent_id,
                    summary_zh="排程结果已写入数据库。",
                    plan=plan_log,
                    artifacts=dict(ctx.artifacts),
                )
            return AgentResponse(
                status="success" if (pr and not pr.get("error")) else "failed",
                agent_id=self.agent_id,
                summary_zh=(pr or {}).get("message_zh", "确认完成。"),
                plan=plan_log,
                artifacts=dict(ctx.artifacts),
            )

        pending = ctx.artifacts.get("pending_persist") or {}
        if pending.get("confirm_token"):
            preview = pending.get("preview") or {}
            summary = (
                f"排程完成，待确认落库：{preview.get('plan_name', '计划')}，"
                f"makespan={preview.get('makespan')}，高风险工单 {preview.get('high_risk_count', 0)} 个。"
            )
            return AgentResponse(
                status="pending_confirm",
                agent_id=self.agent_id,
                summary_zh=summary,
                plan=plan_log,
                artifacts=dict(ctx.artifacts),
                pending_action={
                    "type": "confirm_persist",
                    "confirm_token": pending.get("confirm_token"),
                    "expires_at": pending.get("expires_at"),
                    "preview": preview,
                },
            )

        persist = wants_persist_request(request.message or "", request.params)
        resp = super().finalize(request, ctx, plan_log)
        catalog = ctx.artifacts.get("scheduling_catalog")
        if catalog:
            n_sol = len(catalog.get("solvers") or [])
            n_st = len(catalog.get("strategies") or [])
            resp.summary_zh = f"当前可用 {n_st} 种策略、{n_sol} 个求解器，可在排程中心选择后执行。"
            return resp

        sr = ctx.artifacts.get("schedule_results") or {}
        if isinstance(sr, dict) and sr.get("results") and not any(
            k in sr for k in ("spt", "edd", "ts", "ga")
        ):
            sr = sr["results"]

        if isinstance(sr, dict) and sr:
            ctx.artifacts.pop("clarification", None)
            from metaforge.scheduling.goals import METRIC_LABELS_ZH, pick_best_schedule

            interp = ctx.artifacts.get("interpretation") or {}
            full_mode = interp.get("full_compare")
            metric = str(interp.get("recommend_metric") or "makespan")
            if full_mode:
                metric = "score"
            goal_zh = interp.get("schedule_goal_name_zh") or ""
            best_sid, best, best_val = pick_best_schedule(sr, recommend_metric=metric)
            st = interp.get("strategy_name") or interp.get("strategy_id") or ""
            strat_note = interp.get("strategy_match_note") or ""
            n_ok = sum(
                1 for v in sr.values() if isinstance(v, dict) and not v.get("error")
            )
            metric_zh = METRIC_LABELS_ZH.get(metric, metric)
            if best_sid and best_val != float("inf"):
                if persist:
                    ms = best.get("best_score") if best else best_val
                    resp.summary_zh = (
                        f"排程完成，待确认落库：最优 {best.get('name') or best_sid}，"
                        f"完工时间 {ms}。"
                    )
                    resp.ui_action = None
                elif full_mode or n_ok > 2:
                    resp.summary_zh = (
                        f"已在 {n_ok} 种非 RL 算法中对比（业务目标：{goal_zh or '综合'}）。"
                        f"按{metric_zh}最优：{best.get('name') or best_sid}"
                        f"（{best_val:.2f}）。"
                        f"{'策略「' + st + '」用于求解过程加权。' if st else ''}"
                        f"{strat_note + '。' if strat_note else ''}"
                        "规则启发式不保证全局最优，已全量对比后选取。"
                        "请点击「查看分析报表」查看各算法甘特图与指标。"
                    )
                    resp.ui_action = {"type": "navigate", "path": "/reports"}
                else:
                    ms = best.get("best_score") if best else best_val
                    resp.summary_zh = (
                        f"排程完成：最优 {best.get('name') or best_sid}，完工时间 {ms}。"
                        f"{'策略「' + st + '」。' if st else ''}"
                        "请点击「查看分析报表」查看甘特图与指标。"
                    )
                    resp.ui_action = {"type": "navigate", "path": "/reports"}
            else:
                resp.summary_zh = (
                    "排程已完成，待确认落库。" if persist else "排程已完成，请点击「查看分析报表」查看结果。"
                )
                if not persist:
                    resp.ui_action = {"type": "navigate", "path": "/reports"}
            ContextManager.consolidate_after_run(
                self._session_id(request),
                interp,
                event_type="schedule_completed",
            )
            resp.artifacts = dict(ctx.artifacts)
            return resp

        clar = ctx.artifacts.get("clarification")
        interp = ctx.artifacts.get("interpretation") or {}
        if clar and clar.get("question") and interp.get("intent_type") == "CLARIFICATION":
            ContextManager.set_pending(
                self._session_id(request),
                original_message=request.message,
                partial_intent=dict(interp.get("clarification_context") or {}),
                question=str(clar["question"]),
            )
            return AgentResponse(
                status="pending_clarification",
                agent_id=self.agent_id,
                summary_zh=str(clar["question"]),
                plan=plan_log,
                artifacts=dict(ctx.artifacts),
                plan_planner=getattr(self, "_plan_planner", "rule"),
            )

        if interp.get("summary_zh") and interp.get("intent_type") != "CLARIFICATION":
            resp.summary_zh = interp["summary_zh"]
        elif clar and clar.get("question"):
            resp.summary_zh = str(clar["question"])
        return resp
