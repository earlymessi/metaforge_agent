"""插单工单多轮补全：校验、追问文案、规则/LLM 合并用户补充。"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Optional, Tuple

_MACHINE_RE = re.compile(r"(\d+)\s*号?\s*机")
_MACHINE_CN_RE = re.compile(r"([一二三四五六七八九十两\d]+)\s*号?\s*机")
_CN_DIGIT = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _chinese_machine_number(text: str) -> Optional[int]:
    m = _MACHINE_CN_RE.search(text or "")
    if not m:
        return None
    raw = (m.group(1) or "").strip()
    if raw.isdigit():
        return int(raw)
    if raw in _CN_DIGIT:
        return _CN_DIGIT[raw]
    if raw.startswith("十") and len(raw) == 2 and raw[1] in _CN_DIGIT:
        return 10 + _CN_DIGIT[raw[1]]
    if raw.endswith("十") and len(raw) == 2 and raw[0] in _CN_DIGIT:
        return _CN_DIGIT[raw[0]] * 10
    return None
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(小时|h|分钟|min)?", re.I)
_TASK_COUNT_RE = re.compile(r"(\d+)\s*道?\s*工序")
_INSERT_NAME_RE = re.compile(r"插单[「『\"']?([^」』\"'\s,，]+)")
_INSERT_MSG_RE = re.compile(
    r"插单|插入(?:订单|工单)|新增(?:订单|工单)|"
    r"(?:订单|工单).*(?:插入|新增)|"
    r"\d+\s*(?:小时|h|H)?\s*(?:后|之后|以后).*(?:插入|插单|订单|工单)",
    re.I,
)
_NEW_ORDER_RE = re.compile(
    r"新增(?:订单|工单)[「『\"']?([^」』\"'\s,，]+)|"
    r"(?:订单|工单)[「『\"']?([a-zA-Z0-9_\u4e00-\u9fff]{1,20})[」』\"']?(?:\s|$|，|,)",
    re.I,
)

# 与 parse_event.default_insert_job 一致，用于识别「未确认的系统占位」
_STUB_DURATION = 5.0
_STUB_MACHINE = 0


def default_insert_job(name: str = "急单") -> Dict[str, Any]:
    return {
        "name": name or "急单",
        "priority": 100,
        "tasks": [{"name": "Op-1", "machine_id": _STUB_MACHINE, "duration": _STUB_DURATION}],
    }


def message_looks_like_insert_order(text: str) -> bool:
    return bool(_INSERT_MSG_RE.search((text or "").strip()))


def parse_insert_job_name(text: str) -> str:
    m = _INSERT_NAME_RE.search(text or "")
    if m:
        return m.group(1).strip()
    m = _NEW_ORDER_RE.search(text or "")
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    return ""


def _parse_machine_id(text: str, default: int = -1) -> int:
    m = _MACHINE_RE.search(text or "")
    if m:
        return max(0, int(m.group(1)) - 1)
    cn = _chinese_machine_number(text)
    if cn is not None:
        return max(0, cn - 1)
    return default


def _parse_duration(text: str, default: Optional[float] = None) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(小时|h|分钟|min)\b", text or "", re.I)
    if not m:
        return default
    val = float(m.group(1))
    unit = (m.group(2) or "小时").lower()
    if unit in ("分钟", "min"):
        return val / 60.0
    return val


def is_stub_insert_job(job: Optional[Dict[str, Any]]) -> bool:
    """是否为系统自动占位（未经过用户确认的工艺假设）。"""
    if not job or not isinstance(job, dict):
        return True
    tasks = job.get("tasks") or []
    if len(tasks) != 1:
        return False
    t = tasks[0] if isinstance(tasks[0], dict) else {}
    return (
        float(t.get("duration") or 0) == _STUB_DURATION
        and int(t.get("machine_id") if t.get("machine_id") is not None else -1) == _STUB_MACHINE
        and str(t.get("name") or "Op-1") == "Op-1"
    )


def validate_insert_job(job: Optional[Dict[str, Any]], *, allow_stub: bool = False) -> Tuple[bool, List[str]]:
    """返回 (是否可重排, 缺失/待确认字段键)。"""
    missing: List[str] = []
    if not job or not isinstance(job, dict):
        return False, ["name", "tasks"]

    name = str(job.get("name") or "").strip()
    if not name:
        missing.append("name")

    tasks = job.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        missing.append("tasks")
        return False, missing

    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            missing.append(f"tasks[{i}]")
            continue
        dur = t.get("duration")
        if dur is None or float(dur) <= 0:
            missing.append(f"tasks[{i}].duration")
        mid = t.get("machine_id")
        opts = t.get("machine_options")
        if mid is None and not opts:
            missing.append(f"tasks[{i}].machine_id")

    if not allow_stub and is_stub_insert_job(job):
        if "tasks" not in missing:
            missing.append("tasks_confirmed")

    # 去重保序
    seen = set()
    uniq = []
    for k in missing:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return len(uniq) == 0, uniq


def build_insert_job_question(
    missing: List[str],
    draft: Optional[Dict[str, Any]] = None,
    *,
    event_summary: str = "",
) -> str:
    draft = draft or {}
    name = draft.get("name") or "（未命名）"
    parts: List[str] = []
    if event_summary:
        parts.append(event_summary.strip())
    parts.append(f"插单「{name}」还缺少以下信息，请在本对话中补充（可一次说全，也可分多条）：")

    hints: List[str] = []
    if "name" in missing:
        hints.append("• 工单名称（如：订单a、急单）")
    if "tasks" in missing or any(k.startswith("tasks[") for k in missing):
        hints.append("• 工序：每道加工机台（如 3号机→机台ID 2）与时长（如 5小时）")
    if "tasks_confirmed" in missing:
        hints.append(
            "• 请明确工序细节，或回复「确认默认：1道工序、0号机、5小时」以使用系统占位工艺"
        )
    if any("duration" in k for k in missing):
        hints.append("• 各工序加工时长（小时）")
    if any("machine_id" in k for k in missing):
        hints.append("• 各工序机台编号（用户口语 N 号机 = ID N-1）")

    if not hints:
        hints.append("• 工序列表：机台 + 时长；例如「2道工序，都在3号机，分别5小时和3小时」")

    parts.append("\n".join(hints))
    parts.append("\n示例：「3号机5小时，优先级100」或「2道工序：3号机5h + 4号机3h」")
    return "\n".join(parts)


def merge_insert_job_followup(
    message: str,
    draft: Optional[Dict[str, Any]],
    *,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """将用户补充话术合并进插单草稿（规则优先，可选 LLM）。"""
    job = copy.deepcopy(draft) if draft else default_insert_job("")
    text = (message or "").strip()
    tl = text.lower()

    if not job.get("name"):
        parsed_name = parse_insert_job_name(text)
        if parsed_name:
            job["name"] = parsed_name

    if re.search(r"确认默认|使用默认|默认工艺|按默认", text):
        job["_user_confirmed_stub"] = True
        if not job.get("name") or job.get("name") == "":
            job["name"] = "急单"
        if not job.get("tasks"):
            job["tasks"] = default_insert_job(job["name"])["tasks"]
        return job

    pri_m = re.search(r"优先级\s*(\d+)", text)
    if pri_m:
        job["priority"] = int(pri_m.group(1))

    due_m = re.search(r"交期\s*(\d+(?:\.\d+)?)", text)
    if due_m:
        job["due_date"] = float(due_m.group(1))

    task_count_m = _TASK_COUNT_RE.search(text)
    machine_id = _parse_machine_id(text, default=-1)
    duration = _parse_duration(text)

    segments = re.split(r"[+＋、,，；;]\s*", text)
    task_specs: List[Dict[str, Any]] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        mid = _parse_machine_id(seg, default=-1)
        dur = _parse_duration(seg)
        if mid >= 0 or dur is not None:
            task_specs.append(
                {
                    "name": f"Op-{len(task_specs) + 1}",
                    "machine_id": mid if mid >= 0 else _STUB_MACHINE,
                    "duration": float(dur if dur is not None else 1.0),
                }
            )

    if task_specs:
        job["tasks"] = task_specs
    elif task_count_m or (machine_id >= 0 and duration is not None):
        n = int(task_count_m.group(1)) if task_count_m else 1
        mid = machine_id if machine_id >= 0 else _STUB_MACHINE
        dur = float(duration if duration is not None else 1.0)
        job["tasks"] = [
            {"name": f"Op-{i + 1}", "machine_id": mid, "duration": dur} for i in range(max(1, n))
        ]
    elif duration is not None and job.get("tasks"):
        tasks = job["tasks"]
        if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
            tasks[0]["duration"] = float(duration)
    elif machine_id >= 0 and job.get("tasks"):
        tasks = job["tasks"]
        if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
            tasks[0]["machine_id"] = machine_id

    if use_llm and validate_insert_job(job, allow_stub=job.get("_user_confirmed_stub"))[1]:
        llm_job = _merge_insert_job_with_llm(text, job)
        if llm_job:
            job = llm_job

    return job


def _merge_insert_job_with_llm(message: str, draft: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from metaforge.orchestrator.llm_config import llm_enabled

    if not llm_enabled():
        return None
    try:
        from metaforge.orchestrator.llm import invoke

        raw = invoke(
            "insert_job_followup",
            message=message,
            draft=draft,
        )
        if not isinstance(raw, dict):
            return None
        merged = copy.deepcopy(draft)
        if raw.get("name"):
            merged["name"] = str(raw["name"]).strip()
        if raw.get("priority") is not None:
            merged["priority"] = int(raw["priority"])
        if raw.get("due_date") is not None:
            merged["due_date"] = float(raw["due_date"])
        tasks = raw.get("tasks")
        if isinstance(tasks, list) and tasks:
            norm_tasks = []
            for i, t in enumerate(tasks):
                if not isinstance(t, dict):
                    continue
                mid = t.get("machine_id")
                if mid is None and t.get("machine_label"):
                    mid = _parse_machine_id(str(t.get("machine_label")), 0)
                norm_tasks.append(
                    {
                        "name": t.get("name") or f"Op-{i + 1}",
                        "machine_id": int(mid if mid is not None else 0),
                        "duration": float(t.get("duration") or 1.0),
                    }
                )
            if norm_tasks:
                merged["tasks"] = norm_tasks
        if raw.get("confirm_default_stub"):
            merged["_user_confirmed_stub"] = True
        return merged
    except Exception:
        return None


def assess_insert_order_envelope(
    envelope: Dict[str, Any],
    *,
    original_message: str = "",
) -> Dict[str, Any]:
    """评估 insert_order 信封是否可进入 reschedule。"""
    et = envelope.get("event_type")
    if et != "insert_order":
        return {"status": "not_applicable", "ready": True}

    params = dict(envelope.get("params") or {})
    insert_job = params.get("insert_job")
    if not insert_job:
        name = parse_insert_job_name(original_message) or ""
        insert_job = {"name": name, "priority": 100, "tasks": []}

    allow_stub = bool(params.get("_user_confirmed_stub") or (insert_job or {}).get("_user_confirmed_stub"))
    ready, missing = validate_insert_job(insert_job, allow_stub=allow_stub)

    draft = copy.deepcopy(insert_job)
    if draft.get("_user_confirmed_stub"):
        draft.pop("_user_confirmed_stub", None)

    summary = str(envelope.get("summary_zh") or original_message or "")[:120]
    question = build_insert_job_question(missing, draft, event_summary=summary if not ready else "")

    return {
        "status": "ready" if ready else "need_input",
        "ready": ready,
        "missing_fields": missing,
        "question_zh": question,
        "draft": draft,
        "event_type": et,
        "params_snapshot": {k: v for k, v in params.items() if k != "insert_job"},
    }


def apply_intake_to_envelope(envelope: Dict[str, Any], draft: Dict[str, Any]) -> Dict[str, Any]:
    env = copy.deepcopy(envelope)
    params = dict(env.get("params") or {})
    clean = copy.deepcopy(draft)
    clean.pop("_user_confirmed_stub", None)
    params["insert_job"] = clean
    if draft.get("_user_confirmed_stub"):
        params["_user_confirmed_stub"] = True
    env["params"] = params
    return env
