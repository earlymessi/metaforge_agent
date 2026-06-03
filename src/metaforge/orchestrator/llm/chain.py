"""Prompt | ChatModel | Parser 链（对标 LangChain RunnableSequence / LangGraph 节点）。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from metaforge.orchestrator.llm import parsers, prompts
from metaforge.orchestrator.llm.client import LlmClient


@dataclass(frozen=True)
class LlmNode:
    """单节点：组 prompt → 调模型 → 解析。"""

    name: str
    temperature: float
    system: Callable[..., str]
    user: Callable[..., str]
    parse: Callable[..., Any]


def _attach_meta(result: Dict[str, Any], client: LlmClient, latency_ms: float) -> Dict[str, Any]:
    result["llm_model"] = client.model
    result["llm_latency_ms"] = latency_ms
    return result


# LangGraph 式任务注册表：一任务一节点
NODES: Dict[str, LlmNode] = {
    "router": LlmNode(
        name="router",
        temperature=0.1,
        system=lambda **_: prompts.router_system(),
        user=lambda *, message, **_: prompts.router_user(message),
        parse=lambda raw, *, message="", **_: parsers.parse_router(raw, message=message),
    ),
    "scheduling": LlmNode(
        name="scheduling",
        temperature=0.2,
        system=lambda **_: prompts.scheduling_system(),
        user=lambda *, message, benchmark_file=None, params=None, session_context=None, **_: prompts.scheduling_user(
            message,
            benchmark_file=benchmark_file,
            params=params,
            session_context=session_context,
        ),
        parse=lambda raw, *, message="", **_: parsers.parse_scheduling(raw, message=message),
    ),
    "event": LlmNode(
        name="event",
        temperature=0.15,
        system=lambda **_: prompts.event_system(),
        user=lambda *, message, base_jobs=None, **_: prompts.event_user(
            message, job_names=parsers.extract_job_names(base_jobs)
        ),
        parse=lambda raw, *, message, base_jobs=None, **_: parsers.parse_event(
            raw, message=message, base_jobs=base_jobs
        ),
    ),
    "plan": LlmNode(
        name="plan",
        temperature=0.25,
        system=lambda *, agent_id, name_zh, allowed_tools, **_: prompts.plan_system(
            agent_id=agent_id, name_zh=name_zh, allowed_tools=allowed_tools
        ),
        user=lambda *, agent_id, message, params=None, **_: prompts.plan_user(
            agent_id=agent_id, message=message, params=params
        ),
        parse=lambda raw, *, allowed_tools, **_: parsers.parse_plan_steps(raw, allowed_tools),
    ),
    "plans_intent": LlmNode(
        name="plans_intent",
        temperature=0.15,
        system=lambda **_: prompts.plans_intent_system(),
        user=lambda *, message, **_: prompts.plans_intent_user(message),
        parse=lambda raw, *, message="", **_: parsers.parse_plans_intent(raw, message=message),
    ),
    "insert_job_followup": LlmNode(
        name="insert_job_followup",
        temperature=0.15,
        system=lambda **_: prompts.insert_job_followup_system(),
        user=lambda *, message, draft=None, **_: prompts.insert_job_followup_user(
            message, draft=draft
        ),
        parse=lambda raw, *, message="", draft=None, **_: parsers.parse_insert_job_followup(
            raw, message=message, draft=draft
        ),
    ),
    "react_step": LlmNode(
        name="react_step",
        temperature=0.2,
        system=lambda *, agent_id, name_zh, allowed_tools, **_: prompts.react_system(
            agent_id=agent_id, name_zh=name_zh, allowed_tools=allowed_tools
        ),
        user=lambda *, agent_id, message, params=None, history=None, artifacts=None, **_: prompts.react_user(
            agent_id=agent_id,
            message=message,
            params=params,
            history=history,
            artifacts=artifacts,
        ),
        parse=lambda raw, *, allowed_tools, **_: parsers.parse_react_decision(
            raw, allowed_tools=allowed_tools
        ),
    ),
    "reflect": LlmNode(
        name="reflect",
        temperature=0.15,
        system=lambda *, agent_id, name_zh, allowed_tools, **_: prompts.reflect_system(
            agent_id=agent_id, name_zh=name_zh, allowed_tools=allowed_tools
        ),
        user=lambda *, agent_id, message, failed_tool, error, retry_count=0, params=None, history=None, artifacts=None, **_: prompts.reflect_user(
            agent_id=agent_id,
            message=message,
            failed_tool=failed_tool,
            error=error,
            retry_count=retry_count,
            params=params,
            history=history,
            artifacts=artifacts,
        ),
        parse=lambda raw, *, allowed_tools, **_: parsers.parse_reflect(
            raw, allowed_tools=allowed_tools
        ),
    ),
    "summarize": LlmNode(
        name="summarize",
        temperature=0.25,
        system=lambda *, agent_id, name_zh, **_: prompts.summarize_system(
            agent_id=agent_id, name_zh=name_zh
        ),
        user=lambda *, message, agent_id, plan_log=None, artifacts=None, **_: prompts.summarize_user(
            message=message,
            agent_id=agent_id,
            plan_log=plan_log,
            artifacts=artifacts,
        ),
        parse=lambda raw, **_: parsers.parse_summarize(raw),
    ),
}


def invoke(task: str, client: Optional[LlmClient] = None, **kwargs: Any) -> Any:
    """执行一条 LLM 链。task: router | scheduling | event | plan | plans_intent"""
    node = NODES[task]
    llm = client or LlmClient.from_env()
    t0 = time.perf_counter()
    raw = llm.invoke_json(
        system=node.system(**kwargs),
        user=node.user(**kwargs),
        temperature=node.temperature,
    )
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    result = node.parse(raw, **kwargs)
    if isinstance(result, dict):
        return _attach_meta(result, llm, latency_ms)
    return result
