"""
交期承诺预测（排程完成后的只读评估）。

说明：本模块不修改甘特工序时间，不参与 compare_solvers 的求解过程。
仅在得到 schedule 后，将 predicted_completion 与 job.due_date 对比得到风险等级。
例外：若选用 EDD 等规则算法，due_date 会作为排序键；多目标权重含拖期时会影响算法评分。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _completion_times_by_job(schedule: List[Dict[str, Any]]) -> Dict[int, float]:
    comp: Dict[int, float] = {}
    for op in schedule or []:
        jid = int(op["job_id"])
        comp[jid] = max(float(op["end"]), comp.get(jid, 0.0))
    return comp


def _risk_assessment(
    *,
    predicted: float,
    due_date: Optional[float],
    priority: float,
    total_proc: float,
    due_date_explicit: bool,
) -> tuple[str, str, float]:
    """
    返回: (risk_level, risk_reason, tardiness)
    risk_level: on_time | low | medium | high | critical | unknown
    """
    if due_date is None:
        return "unknown", "未设置交期，仅展示预测完工（不约束排产）", 0.0

    due = float(due_date)
    tardy = max(0.0, float(predicted) - due)
    slack = due - float(predicted)
    proc = max(total_proc, 1.0)

    if tardy <= 1e-9:
        buffer_ratio = slack / proc
        if buffer_ratio >= 0.2:
            return "on_time", "按期交付，缓冲充足", 0.0
        if buffer_ratio >= 0.05:
            return "low", "可按期交付，缓冲偏小", 0.0
        return "low", "卡点按期，建议关注后续扰动", 0.0

    ratio = tardy / max(due, 1.0)
    proc_ratio = tardy / proc

    # 自动交期仅作参考时，评估略放宽（交期已在 refine_auto_due_dates 中放大）
    relax = 1.15 if not due_date_explicit else 1.0

    if tardy <= 8 * relax and (ratio <= 0.08 * relax or proc_ratio <= 0.55 * relax):
        return "low", f"略晚于交期 {tardy:.1f}h，影响有限", tardy
    if ratio <= 0.12 * relax or proc_ratio <= 1.0 * relax:
        return "medium", f"轻度延期 {tardy:.1f}h", tardy
    if ratio <= 0.28 * relax or proc_ratio <= 2.0 * relax:
        tag = "（交期为系统估算）" if not due_date_explicit else ""
        return "high", f"明显延期 {tardy:.1f}h{tag}", tardy
    tag = "（交期为系统估算，建议填写客户交期）" if not due_date_explicit else ""
    return "critical", f"严重延期 {tardy:.1f}h，需协调产能或调整交期{tag}", tardy


def compute_delivery_predictions(
    schedule: List[Dict[str, Any]],
    problem: Any,
    *,
    job_name_map: Optional[Dict[int, str]] = None,
    machine_busy_cv: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """基于甘特结果与工单交期，生成交期承诺预测列表（按 job_id 排序）。"""
    completion = _completion_times_by_job(schedule)
    jobs = getattr(problem, "jobs", [])
    predictions: List[Dict[str, Any]] = []

    load_cv = float(machine_busy_cv) if machine_busy_cv is not None else None

    for jid in sorted(completion.keys()):
        predicted = completion[jid]
        job_obj = jobs[jid] if 0 <= jid < len(jobs) else None
        due_date = getattr(job_obj, "due_date", None) if job_obj else None
        due_explicit = bool(getattr(job_obj, "due_date_explicit", True)) if job_obj else True
        priority = float(getattr(job_obj, "priority", 10) or 10) if job_obj else 10.0
        arrival = float(getattr(job_obj, "arrival_time", 0) or 0) if job_obj else 0.0
        total_proc = sum(t.duration for t in job_obj.tasks) if job_obj else 0.0

        risk_level, risk_reason, tardy = _risk_assessment(
            predicted=predicted,
            due_date=due_date,
            priority=priority,
            total_proc=total_proc,
            due_date_explicit=due_explicit,
        )

        if load_cv is not None and load_cv > 0.45 and risk_level == "on_time":
            risk_level = "low"
            risk_reason = f"{risk_reason}；产线负载不均衡(CV={load_cv:.2f})"

        name = (job_name_map or {}).get(jid)
        if not name and schedule:
            for op in schedule:
                if int(op.get("job_id", -1)) == jid and op.get("job_name"):
                    name = op["job_name"]
                    break
        if not name:
            name = f"工单-{jid}"

        due_label = (
            f"承诺交期 {float(due_date):.1f}"
            if due_date is not None
            else "未设交期"
        )
        if due_date is not None and not due_explicit:
            due_label = f"参考交期 {float(due_date):.1f}（未填客户交期，按负载估算）"

        predictions.append(
            {
                "job_id": jid,
                "job_name": name,
                "priority": priority,
                "arrival_time": arrival,
                "due_date": None if due_date is None else float(due_date),
                "due_date_explicit": due_explicit,
                "predicted_completion": float(predicted),
                "tardiness": float(tardy),
                "slack": None if due_date is None else float(due_date) - float(predicted),
                "risk_level": risk_level,
                "risk_reason": risk_reason,
                "commitment_text": f"{due_label}，预计 {predicted:.1f} 完成",
            }
        )

    return predictions


def build_commitment_changes(
    before: List[Dict[str, Any]],
    after: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """对比重排前后的交期承诺变化。"""
    before_map = {int(x["job_id"]): x for x in before}
    after_map = {int(x["job_id"]): x for x in after}
    all_ids = sorted(set(before_map.keys()) | set(after_map.keys()))
    changes = []
    for jid in all_ids:
        b = before_map.get(jid)
        a = after_map.get(jid)
        old_c = float(b["predicted_completion"]) if b else None
        new_c = float(a["predicted_completion"]) if a else None
        if old_c is None or new_c is None:
            continue
        delta = new_c - old_c
        old_risk = b.get("risk_level") if b else None
        new_risk = a.get("risk_level") if a else None
        changes.append(
            {
                "job_id": jid,
                "job_name": (a or b).get("job_name", f"工单-{jid}"),
                "old_completion": old_c,
                "new_completion": new_c,
                "delta": round(delta, 4),
                "old_risk": old_risk,
                "new_risk": new_risk,
                "risk_improved": _risk_rank(new_risk) < _risk_rank(old_risk),
                "risk_worsened": _risk_rank(new_risk) > _risk_rank(old_risk),
            }
        )
    changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return changes


def _risk_rank(level: Optional[str]) -> int:
    order = {"on_time": 0, "low": 1, "medium": 2, "high": 3, "critical": 4, "unknown": 5}
    return order.get(str(level or "unknown"), 5)
