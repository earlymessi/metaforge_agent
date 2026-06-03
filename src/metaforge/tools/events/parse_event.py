"""events.parse_event — NL 解析入口：LLM 优先（prompt+few-shots），规则仅 offline fallback。

主链路：resolve_event_envelope → parse_event_with_llm → normalize_envelope
本文件 _handle 只做：解析编排 + 执行态注入 + 插单 intake（非 NL 分支）
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from metaforge.events.insert_job_intake import (
    apply_intake_to_envelope,
    assess_insert_order_envelope,
    merge_insert_job_followup,
    parse_insert_job_name as _parse_insert_job_name_intake,
)
from metaforge.events.normalize_envelope import build_event_envelope
from metaforge.orchestrator.llm_config import llm_enabled
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(小时|h|分钟|min)?", re.I)
_DUE_CHANGE_RE = re.compile(
    r"((?:订单|工单)[^\s,，]*).*?(?:交期|工期).*?(?:改为|改成|调整到?|延至)\s*(\d+(?:\.\d+)?)",
    re.I,
)
_DUE_CHANGE_FALLBACK_RE = re.compile(
    r"([^\s,，]+).*?(?:交期|工期).*?(?:改为|改成|调整到?|延至)\s*(\d+(?:\.\d+)?)",
    re.I,
)
_INSERT_NAME_RE = re.compile(r"插单[「『\"']?([^」』\"'\s,，]+)")


def _parse_machine_id(text: str, default: int = 0) -> int:
    from metaforge.events.insert_job_intake import _parse_machine_id as _mid

    mid = _mid(text, default=-1)
    return mid if mid >= 0 else default


def _parse_duration(text: str, default: float = 4.0) -> float:
    m = _DURATION_RE.search(text)
    if not m:
        return default
    val = float(m.group(1))
    unit = (m.group(2) or "小时").lower()
    if unit in ("分钟", "min"):
        return val / 60.0
    return val


def _job_name(job: Any, default: str) -> str:
    if isinstance(job, dict):
        return str(job.get("name") or default)
    return str(getattr(job, "name", None) or default)


def default_insert_job(name: str = "急单") -> Dict[str, Any]:
    """与看板插单表单默认结构一致。"""
    return {
        "name": name or "急单",
        "priority": 100,
        "tasks": [
            {
                "name": "Op-1",
                "machine_id": 0,
                "duration": 5,
            }
        ],
    }


def _parse_insert_job_name(text: str) -> str:
    m = _INSERT_NAME_RE.search(text)
    if m:
        return m.group(1).strip()
    return _parse_insert_job_name_intake(text)


def _parse_due_date_changes(text: str, base_jobs: Optional[List[Any]]) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    for pattern in (_DUE_CHANGE_RE, _DUE_CHANGE_FALLBACK_RE):
        for m in pattern.finditer(text):
            job_name = m.group(1).strip()
            if len(job_name) < 2 and pattern is _DUE_CHANGE_FALLBACK_RE:
                continue
            changes.append({"job_name": job_name, "new_due_date": float(m.group(2))})
        if changes:
            return changes
    if base_jobs:
        j0 = base_jobs[0]
        due_m = re.search(
            r"(?:改为|改成|调整到?|延至)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:小时|h)?\s*$",
            text,
        )
        if due_m:
            val = due_m.group(1) or due_m.group(2)
            return [{"job_name": _job_name(j0, "工单A"), "new_due_date": float(val)}]
    return []


def _merge_execution_reschedule_options(
    opts: Dict[str, Any], execution: Dict[str, Any]
) -> Dict[str, Any]:
    from metaforge.utils.solver_registry import try_resolve_solver_id

    out = dict(opts or {})
    if execution.get("baseline_gantt"):
        out.setdefault("baseline_gantt", execution.get("baseline_gantt"))
    raw_solver = execution.get("baseline_solver")
    if raw_solver:
        sid = try_resolve_solver_id(str(raw_solver), default=str(raw_solver).strip())
        out.setdefault("baseline_solver", sid)
        out.setdefault("solvers", [sid])
    if execution.get("weights"):
        out.setdefault("weights", execution.get("weights"))
    return out


def _apply_execution_defaults(
    event_type: str, params: Dict[str, Any], execution: Dict[str, Any]
) -> Dict[str, Any]:
    if execution.get("status") not in ("running", "paused"):
        return params
    p = dict(params)
    sim = float(execution.get("sim_time") or 0)
    if event_type == "machine_breakdown":
        if p.get("breakdown_start") is None:
            p["breakdown_start"] = sim
        if p.get("freeze_time") is None:
            p["freeze_time"] = sim
    elif event_type == "insert_order":
        if p.get("freeze_time") is None:
            p["freeze_time"] = sim
    elif event_type == "due_date_change":
        if p.get("freeze_time") is None:
            p["freeze_time"] = sim
    return p


def _merge_insert_job_from_message(
    message: str,
    job: Dict[str, Any],
) -> Dict[str, Any]:
    """插单工艺：LLM 可用时走 insert_job_followup prompt，否则规则合并。"""
    draft = dict(job)
    use_llm = llm_enabled()
    return merge_insert_job_followup(message, draft, use_llm=use_llm)


def parse_event_message(message: str, *, base_jobs: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Offline fallback：LLM 关闭或失败时使用（与 event prompt few-shots 对齐的极简规则）。"""
    from metaforge.events.insert_job_intake import message_looks_like_insert_order

    text = (message or "").strip()
    tl = text.lower()
    params: Dict[str, Any] = {}
    event_type = "machine_breakdown"

    if message_looks_like_insert_order(text):
        event_type = "insert_order"
        params["mode"] = "global" if "全局" in text else "local_repair"
        ins_name = _parse_insert_job_name(text) or "急单"
        params["insert_job"] = _merge_insert_job_from_message(
            text, {"name": ins_name, "priority": 100, "tasks": []}
        )
        freeze_m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:小时|h|H)?\s*(?:后|之后|以后)|"
            r"(\d+(?:\.\d+)?)\s*(?:小时|h|H)\s*(?:插入|插单)",
            text,
            re.I,
        )
        if freeze_m:
            params["freeze_time"] = float(freeze_m.group(1) or freeze_m.group(2))
    elif "改交期" in text or (
        "交期" in text and any(k in text for k in ("改为", "改成", "调整", "延至", "重排"))
    ):
        event_type = "due_date_change"
        params["due_date_changes"] = _parse_due_date_changes(text, base_jobs)
    elif "停机" in text or "大修" in text:
        event_type = "planned_downtime"
        mid = _parse_machine_id(text)
        dur = _parse_duration(text, 8.0)
        params["downtime_blocks"] = [
            {"machine_id": mid, "start": 0.0, "end": dur, "label": "planned_downtime"}
        ]
    elif "晚到" in text or "延迟到料" in text:
        event_type = "material_delay"
        params["job_name"] = _job_name(base_jobs[0] if base_jobs else None, "工单A")
        params["delay_hours"] = _parse_duration(text, 24.0)
    elif "加急" in text or "优先级" in text:
        event_type = "priority_change"
        params["changes"] = [
            {"job_name": _job_name(base_jobs[0] if base_jobs else None, "工单A"), "new_priority": 100}
        ]
    elif "取消" in text or "撤单" in text:
        event_type = "order_cancel"
        params["job_names"] = [_job_name(base_jobs[-1] if base_jobs else None, "工单B")]
    elif "数量" in text:
        event_type = "quantity_change"
        params["changes"] = [
            {"job_name": _job_name(base_jobs[0] if base_jobs else None, "工单A"), "new_quantity": 2}
        ]
    elif "坏了" in text or "故障" in text or "breakdown" in tl:
        event_type = "machine_breakdown"
        params["machine_id"] = _parse_machine_id(text)
        params["breakdown_start"] = None
        kw_idx = max(text.find("坏了"), text.find("故障"), text.lower().find("breakdown"))
        dur_text = text[kw_idx:] if kw_idx >= 0 else text
        params["breakdown_duration"] = _parse_duration(dur_text, 4.0)
        if any(k in text for k in ("现在", "马上", "立即", "当前")):
            params["freeze_time"] = None
    else:
        event_type = "due_date_change"
        params["due_date_changes"] = _parse_due_date_changes(text, base_jobs)

    return build_event_envelope(
        event_type,
        params,
        base_jobs=list(base_jobs or []),
        summary_zh=text,
        planner="rule",
    )


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    from metaforge.events.resolve_event import resolve_event_envelope

    message = params.get("message") or ctx.extras.get("message") or ""
    base_jobs = ctx.custom_data or params.get("base_jobs")
    exec_doc = (ctx.extras or {}).get("production_execution")
    if exec_doc and exec_doc.get("jobs_snapshot"):
        base_jobs = exec_doc["jobs_snapshot"]

    merge_params = dict(params)
    merge_params.setdefault("use_llm", llm_enabled())
    data = resolve_event_envelope(
        message,
        base_jobs=base_jobs,
        params=merge_params,
    )
    et = data.get("event_type") or ""

    if et == "insert_order":
        p = data.setdefault("params", {})
        job = dict(p.get("insert_job") or {})
        if not (job.get("tasks") or []):
            ins_name = job.get("name") or _parse_insert_job_name(message) or "急单"
            p["insert_job"] = _merge_insert_job_from_message(
                message, {"name": ins_name, "priority": job.get("priority") or 100, "tasks": []}
            )

    if exec_doc:
        data["params"] = _apply_execution_defaults(et, data.get("params") or {}, exec_doc)
        data["reschedule_options"] = _merge_execution_reschedule_options(
            data.get("reschedule_options") or {}, exec_doc
        )

    if et == "insert_order":
        params = data.setdefault("params", {})
        job = dict(params.get("insert_job") or {})
        parsed_name = _parse_insert_job_name(message) or ""
        if not str(job.get("name") or "").strip() and parsed_name:
            job["name"] = parsed_name
        if "tasks" not in job or job.get("tasks") is None:
            job["tasks"] = []
        if "priority" not in job:
            job["priority"] = 100
        params["insert_job"] = job
        intake = assess_insert_order_envelope(data, original_message=message)
        if ctx.artifacts is not None:
            ctx.artifacts["insert_job_intake"] = intake
            if intake.get("ready"):
                data = apply_intake_to_envelope(data, intake["draft"])
            ctx.artifacts["event_envelope"] = data
        return ToolResult(
            ok=True,
            data={**data, "insert_job_intake": intake},
            artifacts_key="event_envelope",
        )

    if base_jobs and not data.get("base_jobs"):
        data["base_jobs"] = list(base_jobs)
    if ctx.artifacts is not None:
        ctx.artifacts["event_envelope"] = data
    return ToolResult(ok=True, data=data, artifacts_key="event_envelope")


def register_events_parse_tool() -> None:
    name = "events.parse_event"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh=(
                "从自然语言解析 MES 动态事件为结构化 event_envelope（event_type + params）。"
                "支持：设备故障、插单、改交期、计划停机、物料延迟、优先级/数量变更、撤单。"
                "输入 message；可选 base_jobs。输出供 events.reschedule 直接消费。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "用户自然语言描述"},
                    "base_jobs": {"type": "array", "description": "当前工单列表"},
                    "use_llm": {"type": "boolean", "description": "是否用 LLM 解析，默认随 LLM_ENABLED"},
                },
            },
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
