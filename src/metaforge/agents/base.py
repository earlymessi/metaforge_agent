"""业务 Agent 基类：单意图域内 Plan-and-Solve。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from metaforge.tools.base import ToolContext
from metaforge.tools.registry import run_tool


@dataclass
class PlanStep:
    step_id: str
    tool: str
    params: Dict[str, Any] = field(default_factory=dict)
    optional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "params": self.params,
            "optional": self.optional,
            "status": "pending",
        }


@dataclass
class AgentRequest:
    message: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    status: str
    agent_id: str
    summary_zh: str = ""
    plan: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    pending_action: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    plan_planner: Optional[str] = None
    ui_action: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "status": self.status,
            "agent": self.agent_id,
            "summary_zh": self.summary_zh,
            "plan": self.plan,
            "artifacts": self.artifacts,
        }
        if self.ui_action is not None:
            d["ui_action"] = self.ui_action
        if self.plan_planner:
            d["plan_planner"] = self.plan_planner
        if self.pending_action is not None:
            d["pending_action"] = self.pending_action
        if self.error:
            d["error"] = self.error
        events_trace = self.artifacts.get("events_trace") if isinstance(self.artifacts, dict) else None
        if isinstance(events_trace, dict):
            d["events_trace"] = events_trace
        kitting_trace = self.artifacts.get("kitting_trace") if isinstance(self.artifacts, dict) else None
        if isinstance(kitting_trace, dict):
            d["kitting_trace"] = kitting_trace
        commitment_trace = (
            self.artifacts.get("commitment_trace") if isinstance(self.artifacts, dict) else None
        )
        if isinstance(commitment_trace, dict):
            d["commitment_trace"] = commitment_trace
        whatif_trace = self.artifacts.get("whatif_trace") if isinstance(self.artifacts, dict) else None
        if isinstance(whatif_trace, dict):
            d["whatif_trace"] = whatif_trace
        plans_trace = self.artifacts.get("plans_trace") if isinstance(self.artifacts, dict) else None
        if isinstance(plans_trace, dict):
            d["plans_trace"] = plans_trace
        return d


class BaseAgent:
    agent_id: str = "base"
    name_zh: str = "Base"
    allowed_tools: List[str] = []
    _plan_planner: str = "rule"

    def build_rule_plan(self, request: AgentRequest) -> List[PlanStep]:
        raise NotImplementedError

    def build_plan(self, request: AgentRequest) -> List[PlanStep]:
        from metaforge.orchestrator.llm_plan import resolve_agent_plan_steps

        steps, planner = resolve_agent_plan_steps(
            agent_id=self.agent_id,
            name_zh=self.name_zh,
            allowed_tools=self.allowed_tools,
            message=request.message,
            params=request.params,
            rule_builder=lambda: self.build_rule_plan(request),
        )
        self._plan_planner = planner
        return steps

    def finalize(self, request: AgentRequest, ctx: ToolContext, plan_log: List[Dict[str, Any]]) -> AgentResponse:
        summary = self._resolve_summary(request, ctx, plan_log)
        return AgentResponse(
            status="success",
            agent_id=self.agent_id,
            summary_zh=summary,
            plan=plan_log,
            artifacts=dict(ctx.artifacts),
            plan_planner=getattr(self, "_plan_planner", "rule"),
        )

    def _resolve_summary(
        self,
        request: AgentRequest,
        ctx: ToolContext,
        plan_log: List[Dict[str, Any]],
    ) -> str:
        """自上而下最后一环：Tool 结果 → LLM 组织答复（失败则回退 artifacts 摘要）。"""
        rule_summary = (ctx.artifacts.get("react_summary") or "").strip()
        if not rule_summary:
            rule_summary = (ctx.artifacts.get("interpretation") or {}).get("summary_zh", "")
        if not rule_summary:
            rule_summary = (ctx.artifacts.get("delivery_assessment") or {}).get("summary_zh", "")
        if not rule_summary:
            rule_summary = (ctx.artifacts.get("impact_summary") or {}).get("summary_zh", "")
        if not rule_summary:
            rule_summary = f"{self.name_zh} 执行完成。"

        from metaforge.orchestrator.llm_summarize import llm_summarize_enabled, summarize_agent_response

        if not llm_summarize_enabled() or not (request.message or "").strip():
            return rule_summary

        try:
            data = summarize_agent_response(
                agent_id=self.agent_id,
                name_zh=self.name_zh,
                message=request.message,
                plan_log=plan_log,
                artifacts=ctx.artifacts,
            )
            summary = str(data.get("summary_zh") or "").strip()
            if summary:
                ctx.artifacts["llm_summary"] = data
                return summary
        except Exception:
            pass
        return rule_summary

    def _after_tool_step(
        self,
        request: AgentRequest,
        step: PlanStep,
        result,
        tool_ctx: ToolContext,
        plan_log: List[Dict[str, Any]],
    ) -> Optional[AgentResponse]:
        """ReAct 循环中 Tool 执行后的钩子；返回 AgentResponse 则提前结束。"""
        return None

    def _reflect_on_tool_failure(
        self,
        request: AgentRequest,
        step: PlanStep,
        error: str,
        tool_ctx: ToolContext,
        plan_log: List[Dict[str, Any]],
        history: List[Dict[str, Any]],
        retry_count: int,
    ) -> Optional[AgentResponse]:
        """Tool 失败时调用反思层；返回 None 表示应直接失败。"""
        from metaforge.orchestrator.llm_reflect import (
            llm_reflect_enabled,
            reflect_max_retries,
            reflect_tool_failure,
        )

        if not llm_reflect_enabled() or retry_count >= reflect_max_retries():
            return AgentResponse(
                status="failed",
                agent_id=self.agent_id,
                plan=plan_log,
                error=error,
                artifacts=tool_ctx.artifacts,
                plan_planner=self._plan_planner,
            )

        try:
            reflection = reflect_tool_failure(
                agent_id=self.agent_id,
                name_zh=self.name_zh,
                allowed_tools=self.allowed_tools,
                message=request.message,
                failed_tool=step.tool,
                error=error or "",
                params=request.params,
                history=history,
                artifacts=tool_ctx.artifacts,
                retry_count=retry_count,
            )
        except Exception:
            return AgentResponse(
                status="failed",
                agent_id=self.agent_id,
                plan=plan_log,
                error=error,
                artifacts=tool_ctx.artifacts,
                plan_planner=self._plan_planner,
            )

        tool_ctx.artifacts["last_reflection"] = reflection
        action = reflection.get("action") or "finish"
        msg = reflection.get("message_zh") or error

        if action == "clarify":
            return AgentResponse(
                status="pending_clarification",
                agent_id=self.agent_id,
                summary_zh=msg or "请补充更多信息以便继续。",
                plan=plan_log,
                artifacts=dict(tool_ctx.artifacts),
                plan_planner="llm_reflect",
            )
        if action == "human":
            return AgentResponse(
                status="need_input",
                agent_id=self.agent_id,
                summary_zh=msg or "该情况需人工审核后再处理。",
                plan=plan_log,
                artifacts=dict(tool_ctx.artifacts),
                pending_action={"type": "human_review", "reason_zh": msg},
                plan_planner="llm_reflect",
            )
        if action == "retry":
            retry_tool = str(reflection.get("tool") or step.tool)
            retry_params = dict(reflection.get("params") or step.params or {})
            retry_step = PlanStep(f"{step.step_id}-retry", retry_tool, retry_params)
            early = self._run_single_step(
                request,
                retry_step,
                tool_ctx,
                plan_log,
                on_step_start=None,
                on_step_done=None,
            )
            if early is not None:
                return early
            last = plan_log[-1] if plan_log else {}
            history.append(
                {
                    "tool": retry_tool,
                    "ok": last.get("status") == "completed",
                    "error": last.get("error"),
                    "note": reflection.get("feedback_zh") or "reflect retry",
                }
            )
            if last.get("status") == "failed":
                return self._reflect_on_tool_failure(
                    request,
                    retry_step,
                    str(last.get("error") or error),
                    tool_ctx,
                    plan_log,
                    history,
                    retry_count + 1,
                )
            hook = self._after_tool_step(request, retry_step, None, tool_ctx, plan_log)
            if hook is not None:
                return hook
            return None

        if reflection.get("message_zh"):
            tool_ctx.artifacts["react_summary"] = reflection["message_zh"]
        return AgentResponse(
            status="failed",
            agent_id=self.agent_id,
            summary_zh=msg or error,
            plan=plan_log,
            error=error,
            artifacts=dict(tool_ctx.artifacts),
            plan_planner="llm_reflect",
        )

    def _run_react_loop(
        self,
        request: AgentRequest,
        tool_ctx: ToolContext,
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResponse:
        from metaforge.orchestrator.llm_react import decide_react_step, react_max_steps

        self._plan_planner = "llm_react"
        plan_log: List[Dict[str, Any]] = []
        history: List[Dict[str, Any]] = []
        reflect_retries = 0

        for i in range(react_max_steps()):
            try:
                decision = decide_react_step(
                    agent_id=self.agent_id,
                    name_zh=self.name_zh,
                    allowed_tools=self.allowed_tools,
                    message=request.message,
                    params=request.params,
                    history=history,
                    artifacts=tool_ctx.artifacts,
                )
            except Exception as e:
                from metaforge.orchestrator.llm_config import llm_fallback_rule

                if not llm_fallback_rule():
                    return AgentResponse(
                        status="failed",
                        agent_id=self.agent_id,
                        plan=plan_log,
                        error=str(e)[:300],
                        artifacts=tool_ctx.artifacts,
                        plan_planner="llm_react_fallback",
                    )
                steps = self.build_plan(request)
                self._plan_planner = "rule_fallback"
                return self._run_plan_steps(
                    request, tool_ctx, steps, plan_log, on_step_start, on_step_done
                )

            if decision.get("action") == "finish":
                if decision.get("answer"):
                    tool_ctx.artifacts["react_summary"] = decision["answer"]
                return self.finalize(request, tool_ctx, plan_log)

            step = PlanStep(
                step_id=f"r{i + 1}",
                tool=str(decision.get("tool") or ""),
                params=dict(decision.get("params") or {}),
            )
            early = self._run_single_step(
                request,
                step,
                tool_ctx,
                plan_log,
                on_step_start=on_step_start,
                on_step_done=on_step_done,
            )
            if early is not None:
                return early
            last = plan_log[-1] if plan_log else {}
            history.append(
                {
                    "tool": step.tool,
                    "ok": last.get("status") == "completed",
                    "error": last.get("error"),
                    "note": decision.get("reasoning_zh") or decision.get("answer"),
                }
            )
            if last.get("status") == "failed" and not step.optional:
                reflected = self._reflect_on_tool_failure(
                    request,
                    step,
                    str(last.get("error") or ""),
                    tool_ctx,
                    plan_log,
                    history,
                    reflect_retries,
                )
                reflect_retries += 1
                if reflected is None:
                    continue
                return reflected
            hook = self._after_tool_step(request, step, None, tool_ctx, plan_log)
            if hook is not None:
                return hook

        return AgentResponse(
            status="failed",
            agent_id=self.agent_id,
            plan=plan_log,
            error="ReAct 步数已达上限，请简化请求或重试",
            artifacts=tool_ctx.artifacts,
            plan_planner=self._plan_planner,
        )

    def _run_single_step(
        self,
        request: AgentRequest,
        step: PlanStep,
        tool_ctx: ToolContext,
        plan_log: List[Dict[str, Any]],
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Optional[AgentResponse]:
        entry = step.to_dict()
        entry["tool"] = step.tool
        if on_step_start:
            on_step_start(dict(entry))
        if step.tool not in self.allowed_tools:
            entry["status"] = "failed"
            entry["error"] = f"tool not allowed: {step.tool}"
            plan_log.append(entry)
            if on_step_done:
                on_step_done(dict(entry))
            if not step.optional:
                return AgentResponse(
                    status="failed",
                    agent_id=self.agent_id,
                    plan=plan_log,
                    error=entry["error"],
                    artifacts=tool_ctx.artifacts,
                    plan_planner=getattr(self, "_plan_planner", "rule"),
                )
            return None

        t0 = time.perf_counter()
        result = run_tool(step.tool, step.params, tool_ctx)
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        if result.ok:
            entry["status"] = "completed"
            if result.artifacts_key and result.data is not None:
                if (
                    result.artifacts_key == "schedule_results"
                    and isinstance(result.data, dict)
                ):
                    rd = result.data
                    if isinstance(rd.get("results"), dict):
                        tool_ctx.artifacts["schedule_results"] = rd["results"]
                    for key in (
                        "impact_report",
                        "impact_gantt",
                        "updated_jobs",
                        "event_type",
                    ):
                        if rd.get(key) is not None:
                            tool_ctx.artifacts[key] = rd[key]
                else:
                    tool_ctx.artifacts.setdefault(result.artifacts_key, result.data)
        else:
            entry["status"] = "failed"
            entry["error"] = result.error
            plan_log.append(entry)
            if on_step_done:
                on_step_done(dict(entry))
            if not step.optional:
                return AgentResponse(
                    status="failed",
                    agent_id=self.agent_id,
                    plan=plan_log,
                    error=result.error,
                    artifacts=tool_ctx.artifacts,
                    plan_planner=getattr(self, "_plan_planner", "rule"),
                )
            return None

        plan_log.append(entry)
        if on_step_done:
            on_step_done(dict(entry))
        return None

    def _run_plan_steps(
        self,
        request: AgentRequest,
        tool_ctx: ToolContext,
        steps: List[PlanStep],
        plan_log: List[Dict[str, Any]],
        on_step_start,
        on_step_done,
    ) -> AgentResponse:
        for step in steps:
            early = self._run_single_step(
                request, step, tool_ctx, plan_log, on_step_start=on_step_start, on_step_done=on_step_done
            )
            if early is not None:
                return early
        return self.finalize(request, tool_ctx, plan_log)

    def _tool_context(self, request: AgentRequest) -> ToolContext:
        ctx = request.context
        return ToolContext(
            custom_data=ctx.get("custom_data"),
            benchmark_file=ctx.get("benchmark_file"),
            plan_id=ctx.get("plan_id"),
            weights=ctx.get("weights") or request.params.get("weights"),
            enforce_material=bool(ctx.get("enforce_material", False)),
            random_seed=ctx.get("random_seed"),
            artifacts=dict(ctx.get("artifacts") or {}),
            extras=dict(ctx.get("extras") or {}),
        )

    def run(
        self,
        request: AgentRequest,
        *,
        on_step_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_step_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentResponse:
        tool_ctx = self._tool_context(request)
        if request.message and "message" not in (tool_ctx.extras or {}):
            tool_ctx.extras["message"] = request.message

        extras = tool_ctx.extras or {}
        cached = extras.get("cached_plan_steps")
        if isinstance(cached, list) and cached:
            steps = [
                PlanStep(
                    step_id=str(s.get("step_id", f"s{i}")),
                    tool=str(s.get("tool", "")),
                    params=dict(s.get("params") or {}),
                    optional=bool(s.get("optional")),
                )
                for i, s in enumerate(cached)
                if isinstance(s, dict) and s.get("tool")
            ]
            if extras.get("cached_plan_planner"):
                self._plan_planner = str(extras["cached_plan_planner"])
        else:
            steps = self.build_plan(request)

        from metaforge.orchestrator.llm_react import llm_react_enabled_for

        if llm_react_enabled_for(self.agent_id) and not (
            isinstance(extras.get("cached_plan_steps"), list) and extras.get("cached_plan_steps")
        ):
            return self._run_react_loop(
                request,
                tool_ctx,
                on_step_start=on_step_start,
                on_step_done=on_step_done,
            )

        plan_log: List[Dict[str, Any]] = []

        for step in steps:
            early = self._run_single_step(
                request,
                step,
                tool_ctx,
                plan_log,
                on_step_start=on_step_start,
                on_step_done=on_step_done,
            )
            if early is not None:
                return early
            hook = self._after_tool_step(request, step, None, tool_ctx, plan_log)
            if hook is not None:
                return hook

        return self.finalize(request, tool_ctx, plan_log)
