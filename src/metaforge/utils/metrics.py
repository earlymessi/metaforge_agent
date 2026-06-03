from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


ScheduleOp = Dict[str, Any]


def _completion_times_by_job(schedule: Iterable[ScheduleOp]) -> Dict[int, float]:
    completion: Dict[int, float] = {}
    for op in schedule:
        jid = int(op.get("job_id", op.get("job", -1)))
        if jid < 0:
            continue
        end = float(op["end"])
        prev = completion.get(jid, 0.0)
        if end > prev:
            completion[jid] = end
    return completion


def _busy_time_by_machine(schedule: Iterable[ScheduleOp]) -> Dict[int, float]:
    busy: Dict[int, float] = {}
    for op in schedule:
        mid = int(op.get("machine_id", op.get("machine", -1)))
        if mid < 0:
            continue
        dur = float(op["end"]) - float(op["start"])
        if dur < 0:
            continue
        busy[mid] = busy.get(mid, 0.0) + dur
    return busy


def _energy_cost(
    schedule: Iterable[ScheduleOp],
    *,
    machine_powers: Dict[str, float],
    hourly_prices: List[float],
) -> float:
    """
    按“时间单位=小时”的简化模型计算能耗成本：

    cost = Σ(功率kW * 该小时电价 * 在该小时内的加工时长h)
    """
    if not hourly_prices:
        return 0.0

    def price_at(t: float) -> float:
        # 将时间映射到 [0, 23]，超出部分按循环处理（便于长周期仿真）
        idx = int(math.floor(t)) % 24
        return float(hourly_prices[idx])

    total = 0.0
    for op in schedule:
        mid = int(op.get("machine_id", op.get("machine", -1)))
        if mid < 0:
            continue

        power = float(machine_powers.get(str(mid), 0.0))
        if power <= 0:
            continue

        start = float(op["start"])
        end = float(op["end"])
        if end <= start:
            continue

        t = start
        while t < end:
            next_hour = math.floor(t) + 1.0
            seg_end = min(end, next_hour)
            duration = seg_end - t
            total += power * price_at(t) * duration
            t = seg_end

    return float(total)


def compute_schedule_metrics(
    schedule: List[ScheduleOp],
    problem: Any,
    *,
    resource_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    基于 gantt_data(schedule) 计算多目标指标。

    schedule 期望为 `JobShopProblem.get_schedule()` 的输出：
    - job_id, machine_id, start, end, priority(可选)
    同时兼容部分 solvers/可视化的字段别名：job/machine/operation。
    """
    if not schedule:
        return {
            "makespan": 0,
            "tardiness_total": 0.0,
            "weighted_tardiness_total": 0.0,
            "energy_cost": None,
            "machine_busy_mean": 0.0,
            "machine_busy_std": 0.0,
            "machine_busy_cv": 0.0,
        }

    completion = _completion_times_by_job(schedule)
    makespan = max(completion.values()) if completion else max(float(op["end"]) for op in schedule)

    # tardiness：基于 Job.due_date（JobShopProblem.jobs 中已有）
    tardy_total = 0.0
    weighted_tardy_total = 0.0
    jobs = getattr(problem, "jobs", [])
    for jid, c in completion.items():
        due = None
        prio = None
        if 0 <= jid < len(jobs):
            job_obj = jobs[jid]
            due = getattr(job_obj, "due_date", None)
            prio = getattr(job_obj, "priority", None)
        if due is None:
            continue
        t = max(0.0, float(c) - float(due))
        tardy_total += t
        # priority 默认 10，按比例加权（100 加急会更敏感）
        p = float(prio) if prio is not None else float(schedule[0].get("priority", 10) or 10)
        weighted_tardy_total += t * max(0.1, p / 10.0)

    # 负载均衡：机器忙碌时间的离散程度
    busy = _busy_time_by_machine(schedule)
    busy_list = list(busy.values())
    mean_busy = sum(busy_list) / len(busy_list) if busy_list else 0.0
    std_busy = (
        math.sqrt(sum((x - mean_busy) ** 2 for x in busy_list) / len(busy_list))
        if busy_list
        else 0.0
    )
    cv_busy = (std_busy / mean_busy) if mean_busy > 1e-9 else 0.0

    from metaforge.services.resource_config import effective_resource_config

    energy = None
    cfg = effective_resource_config(resource_config)
    machine_powers = cfg.get("machine_powers") or {}
    hourly_prices = list(cfg.get("hourly_prices") or [])
    try:
        energy = _energy_cost(
            schedule,
            machine_powers=machine_powers,
            hourly_prices=hourly_prices,
        )
    except Exception:
        energy = None

    return {
        "makespan": float(makespan),
        "tardiness_total": float(tardy_total),
        "weighted_tardiness_total": float(weighted_tardy_total),
        "energy_cost": None if energy is None else float(energy),
        "machine_busy_mean": float(mean_busy),
        "machine_busy_std": float(std_busy),
        "machine_busy_cv": float(cv_busy),
    }


def compute_composite_score(
    metrics: Dict[str, Any],
    *,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    计算综合评分（越小越好）。

    评分为加权和，默认权重偏向 makespan，同时考虑交期与负载均衡。
    - makespan：主目标
    - weighted_tardiness_total：交期违约惩罚（优先级加权）
    - energy_cost：可选（若缺失则视为 0）
    - machine_busy_cv：负载离散系数
    """
    w = {
        "makespan": 1.0,
        "weighted_tardiness_total": 0.5,
        "energy_cost": 0.05,
        "machine_busy_cv": 10.0,
    }
    if weights:
        for k, v in weights.items():
            try:
                w[k] = float(v)
            except Exception:
                continue

    makespan = float(metrics.get("makespan", 0.0))
    tardy = float(metrics.get("weighted_tardiness_total", 0.0))
    energy = metrics.get("energy_cost", 0.0)
    energy = float(energy) if energy is not None else 0.0
    cv = float(metrics.get("machine_busy_cv", 0.0))

    return (
        w["makespan"] * makespan
        + w["weighted_tardiness_total"] * tardy
        + w["energy_cost"] * energy
        + w["machine_busy_cv"] * cv
    )


def compute_bottleneck_report(
    schedule: List[ScheduleOp],
    problem: Any,
) -> Dict[str, Any]:
    """
    基于排程结果识别瓶颈机台与延期贡献较大的工单。
    """
    if not schedule:
        return {"machines": [], "tardiness_contributors": [], "bottleneck_machine_id": None}

    busy = _busy_time_by_machine(schedule)
    completion = _completion_times_by_job(schedule)
    makespan = max(completion.values()) if completion else max(float(op["end"]) for op in schedule)

    machines_report = []
    max_busy = -1.0
    bottleneck_mid = None
    for mid, busy_h in sorted(busy.items(), key=lambda x: x[0]):
        util = (busy_h / makespan) if makespan > 1e-9 else 0.0
        machines_report.append(
            {
                "machine_id": int(mid),
                "busy_time": round(float(busy_h), 4),
                "utilization": round(float(util), 4),
            }
        )
        if busy_h > max_busy:
            max_busy = busy_h
            bottleneck_mid = int(mid)

    tardy_rows = []
    jobs = getattr(problem, "jobs", [])
    for jid, c in completion.items():
        due = None
        job_name = f"Job-{jid}"
        if 0 <= jid < len(jobs):
            job_obj = jobs[jid]
            due = getattr(job_obj, "due_date", None)
            job_name = getattr(job_obj, "name", None) or job_name
        if due is None:
            continue
        tard = max(0.0, float(c) - float(due))
        if tard > 1e-9:
            tardy_rows.append(
                {
                    "job_id": int(jid),
                    "job_name": job_name,
                    "due_date": float(due),
                    "completion": round(float(c), 4),
                    "tardiness": round(float(tard), 4),
                }
            )
    tardy_rows.sort(key=lambda x: x["tardiness"], reverse=True)

    return {
        "machines": machines_report,
        "tardiness_contributors": tardy_rows[:20],
        "bottleneck_machine_id": bottleneck_mid,
        "makespan": round(float(makespan), 4),
    }

