from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from metaforge.utils.metrics import compute_composite_score


def evaluate_sequence_multiobjective(
    problem: Any,
    sequence: List[int],
    *,
    weights: Optional[Dict[str, float]] = None,
    resource_config: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float, Dict[str, Any]]:
    """
    用于搜索算法内部的“快速多目标评估”（越小越好）。

    返回: (score, makespan, metrics)
    - score: 综合评分（权重加权和）
    - makespan: 真实完工时间（用于历史曲线/展示）
    - metrics: 分目标指标（可用于调试/分析）

    说明：
    - 保持与 `JobShopProblem.evaluate/get_schedule` 一致的时序模拟逻辑
    - 指标口径尽量与 `utils/metrics.py` 一致，但为了搜索效率，不构造完整甘特数据
    """
    num_jobs = problem.num_jobs
    num_machines = problem.num_machines
    jobs = problem.jobs

    job_counts = [len(j.tasks) for j in jobs]
    job_ptr = [0] * num_jobs
    job_ready = [0.0] * num_jobs
    machine_ready = [0.0] * num_machines
    machine_busy = [0.0] * num_machines

    # 能耗（可选）
    machine_powers = None
    hourly_prices = None
    if resource_config:
        machine_powers = resource_config.get("machine_powers") or {}
        hourly_prices = list(resource_config.get("hourly_prices") or [])

    def price_at(t: float) -> float:
        if not hourly_prices:
            return 0.0
        return float(hourly_prices[int(math.floor(t)) % 24])

    energy_cost = 0.0

    for job_idx in sequence:
        if job_idx < 0 or job_idx >= num_jobs:
            continue
        op_idx = job_ptr[job_idx]
        if op_idx >= job_counts[job_idx]:
            continue

        task = jobs[job_idx].tasks[op_idx]
        candidates = task.candidate_machines() if hasattr(task, "candidate_machines") else [task.machine_id]
        if not candidates:
            continue
        preferred_machine = getattr(task, "machine_id", None)
        mid = candidates[0]
        best_ready = machine_ready[mid]
        for cand in candidates[1:]:
            ready = machine_ready[cand]
            if ready < best_ready:
                best_ready = ready
                mid = cand
            elif ready == best_ready:
                if preferred_machine is not None and cand == preferred_machine and mid != preferred_machine:
                    mid = cand
                elif cand < mid and mid != preferred_machine:
                    mid = cand
        start = max(machine_ready[mid], job_ready[job_idx])
        if hasattr(problem, "_earliest_feasible_start"):
            start = problem._earliest_feasible_start(mid, start)
        end = start + task.duration

        job_ready[job_idx] = end
        machine_ready[mid] = end
        machine_busy[mid] += float(task.duration)
        job_ptr[job_idx] += 1

        # 能耗按小时分段积分（与 metrics.py 的简化口径一致）
        if machine_powers is not None and hourly_prices:
            power = float(machine_powers.get(str(mid), 0.0))
            if power > 0:
                t = float(start)
                e = float(end)
                while t < e:
                    next_hour = math.floor(t) + 1.0
                    seg_end = min(e, next_hour)
                    duration = seg_end - t
                    energy_cost += power * price_at(t) * duration
                    t = seg_end

    makespan = float(max(machine_ready) if machine_ready else 0.0)

    # tardiness（基于 job.due_date）
    tardiness_total = 0.0
    weighted_tardiness_total = 0.0
    for jid in range(num_jobs):
        due = getattr(jobs[jid], "due_date", None)
        if due is None:
            continue
        t = max(0.0, float(job_ready[jid]) - float(due))
        tardiness_total += t
        prio = float(getattr(jobs[jid], "priority", 10) or 10)
        weighted_tardiness_total += t * max(0.1, prio / 10.0)

    # 负载均衡（CV）
    busy_list = [b for b in machine_busy if b > 0]
    mean_busy = (sum(busy_list) / len(busy_list)) if busy_list else 0.0
    std_busy = (
        math.sqrt(sum((x - mean_busy) ** 2 for x in busy_list) / len(busy_list))
        if busy_list
        else 0.0
    )
    machine_busy_cv = (std_busy / mean_busy) if mean_busy > 1e-9 else 0.0

    metrics = {
        "makespan": makespan,
        "tardiness_total": float(tardiness_total),
        "weighted_tardiness_total": float(weighted_tardiness_total),
        "energy_cost": float(energy_cost) if (machine_powers is not None and hourly_prices) else None,
        "machine_busy_cv": float(machine_busy_cv),
    }

    score = float(compute_composite_score(metrics, weights=weights))
    return score, makespan, metrics

