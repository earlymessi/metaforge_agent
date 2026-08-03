from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from metaforge.strategy.catalog import SOFT_FOLDS_INTO
from metaforge.strategy.models import Constraint, SchedulingStrategy
from metaforge.utils.metrics import compute_composite_score


def _job_due_dates(jobs: Optional[Iterable[Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for item in jobs or []:
        if not isinstance(item, dict):
            continue
        jid = item.get("job_id") or item.get("id") or item.get("name")
        due = item.get("due_date")
        if jid is not None and due is not None:
            out[str(jid)] = float(due)
    return out


def _completion_from_gantt(gantt: Iterable[Any]) -> Dict[str, float]:
    completion: Dict[str, float] = {}
    for op in gantt or []:
        if not isinstance(op, dict):
            continue
        jid = op.get("job_id", op.get("job"))
        if jid is None:
            continue
        end = op.get("end", op.get("finish"))
        if end is None:
            continue
        key = str(jid)
        completion[key] = max(completion.get(key, 0.0), float(end))
    return completion


def _resolve_completion(candidate: Dict[str, Any]) -> Dict[str, float]:
    raw = candidate.get("completion_by_job")
    if isinstance(raw, dict) and raw:
        return {str(k): float(v) for k, v in raw.items()}
    return _completion_from_gantt(candidate.get("gantt_data") or [])


def _due_date_for_job(
    job_id: str,
    constraint: Constraint,
    job_dues: Dict[str, float],
) -> Optional[float]:
    if "due_date" in constraint.params and constraint.params["due_date"] is not None:
        return float(constraint.params["due_date"])
    return job_dues.get(job_id)


def _intervals_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def _check_order_on_time(
    constraint: Constraint,
    completion_by_job: Dict[str, float],
    job_dues: Dict[str, float],
) -> List[Dict[str, Any]]:
    job_id = str(constraint.params.get("job_id", ""))
    due = _due_date_for_job(job_id, constraint, job_dues)
    if due is None:
        return [
            {
                "type": "order_on_time",
                "job_id": job_id,
                "message": f"order_on_time: missing due_date for job {job_id!r}",
            }
        ]
    completion = completion_by_job.get(job_id)
    if completion is None:
        return [
            {
                "type": "order_on_time",
                "job_id": job_id,
                "due_date": due,
                "message": f"order_on_time: no completion time for job {job_id!r}",
            }
        ]
    if completion > due + 1e-9:
        return [
            {
                "type": "order_on_time",
                "job_id": job_id,
                "due_date": due,
                "completion": completion,
                "message": f"order_on_time: job {job_id!r} completed at {completion} > due {due}",
            }
        ]
    return []


def _check_machine_unavailable(
    constraint: Constraint,
    gantt: Iterable[Any],
    warnings: List[str],
) -> Tuple[List[Dict[str, Any]], bool]:
    params = constraint.params
    machine_id = params.get("machine_id")
    if machine_id is None:
        warnings.append("machine_unavailable: missing machine_id; skipped")
        return [], False

    start = params.get("start", params.get("unavailable_start"))
    end = params.get("end", params.get("unavailable_end"))
    if start is None or end is None:
        warnings.append(f"machine_unavailable: missing window for machine {machine_id!r}; skipped")
        return [], False

    gantt_list = list(gantt or [])
    if not gantt_list:
        warnings.append(f"machine_unavailable: no gantt_data for machine {machine_id!r}; skipped")
        return [], False

    unavail_start = float(start)
    unavail_end = float(end)
    violations: List[Dict[str, Any]] = []
    has_timing = False

    for op in gantt_list:
        if not isinstance(op, dict):
            continue
        mid = op.get("machine_id", op.get("machine"))
        if mid is None or str(mid) != str(machine_id):
            continue
        op_start = op.get("start")
        op_end = op.get("end", op.get("finish"))
        if op_start is None or op_end is None:
            continue
        has_timing = True
        if _intervals_overlap(float(op_start), float(op_end), unavail_start, unavail_end):
            violations.append(
                {
                    "type": "machine_unavailable",
                    "machine_id": str(machine_id),
                    "window": [unavail_start, unavail_end],
                    "operation": {
                        "start": float(op_start),
                        "end": float(op_end),
                    },
                    "message": (
                        f"machine_unavailable: machine {machine_id!r} scheduled during "
                        f"[{unavail_start}, {unavail_end}]"
                    ),
                }
            )

    if not has_timing:
        warnings.append(f"machine_unavailable: gantt lacks start/end for machine {machine_id!r}; skipped")
        return [], False

    return violations, True


def _check_hard_constraints(
    strategy: SchedulingStrategy,
    candidate: Dict[str, Any],
    *,
    job_dues: Dict[str, float],
    warnings: List[str],
) -> Tuple[bool, List[Dict[str, Any]]]:
    completion_by_job = _resolve_completion(candidate)
    gantt = candidate.get("gantt_data") or []
    violations: List[Dict[str, Any]] = []

    for constraint in strategy.hard_constraints:
        ctype = constraint.type

        if ctype == "order_on_time":
            violations.extend(_check_order_on_time(constraint, completion_by_job, job_dues))
            continue

        if ctype == "machine_unavailable":
            found, checked = _check_machine_unavailable(constraint, gantt, warnings)
            violations.extend(found)
            if not checked:
                continue
            continue

        if ctype in ("frozen_operations", "skill_required", "tooling_exclusive", "precedence"):
            warnings.append(f"{ctype}: insufficient data for deterministic check; skipped")
            continue

        warnings.append(f"unknown hard constraint {ctype!r}; skipped")

    return len(violations) == 0, violations


def _objective_weights(strategy: SchedulingStrategy) -> Dict[str, float]:
    known = {
        "makespan",
        "weighted_tardiness_total",
        "energy_cost",
        "machine_busy_cv",
        "setup_changeover",
        "schedule_stability",
    }
    return {k: float(v) for k, v in strategy.objectives.items() if k in known}


def _soft_penalty_folds_into_objective(constraint: Constraint, objectives: Dict[str, float]) -> bool:
    folded = SOFT_FOLDS_INTO.get(constraint.type)
    if folded is None:
        return False
    return folded in objectives


def _compute_soft_penalties(
    strategy: SchedulingStrategy,
    candidate: Dict[str, Any],
) -> Tuple[float, List[Dict[str, Any]]]:
    total = 0.0
    details: List[Dict[str, Any]] = []

    for constraint in strategy.soft_constraints:
        if _soft_penalty_folds_into_objective(constraint, strategy.objectives):
            continue

        penalty = constraint.penalty
        if penalty is None:
            penalty = 0.0

        amount = float(penalty)
        total += amount
        if amount > 0:
            details.append(
                {
                    "type": constraint.type,
                    "penalty": amount,
                    "schedule_id": candidate.get("schedule_id"),
                }
            )

    return total, details


def _recommendation_reason(
    recommended_id: Optional[str],
    ranking: List[Dict[str, Any]],
    all_illegal: bool,
) -> str:
    if all_illegal or recommended_id is None:
        return "无合法候选：全部方案违反硬约束。"
    best = next((row for row in ranking if row["schedule_id"] == recommended_id), None)
    score = best["score"] if best else "?"
    return f"推荐方案「{recommended_id}」：满足全部硬约束，综合得分最低（{score:.4f}）。"


def evaluate_candidates(
    strategy: SchedulingStrategy,
    candidates: List[Dict[str, Any]],
    *,
    jobs: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    job_dues = _job_due_dates(jobs)
    warnings: List[str] = []
    ranking: List[Dict[str, Any]] = []
    all_hard_violations: List[Dict[str, Any]] = []
    all_soft_penalties: List[Dict[str, Any]] = []

    weights = _objective_weights(strategy)

    for candidate in candidates:
        schedule_id = candidate.get("schedule_id") or candidate.get("solver") or ""
        metrics = dict(candidate.get("metrics") or {})

        hard_ok, hard_violations = _check_hard_constraints(
            strategy,
            candidate,
            job_dues=job_dues,
            warnings=warnings,
        )
        for violation in hard_violations:
            all_hard_violations.append({"schedule_id": schedule_id, **violation})

        soft_total, soft_details = _compute_soft_penalties(strategy, candidate)
        all_soft_penalties.extend(soft_details)

        base_score = compute_composite_score(metrics, weights=weights)
        score = base_score + soft_total

        ranking.append(
            {
                "schedule_id": schedule_id,
                "score": score,
                "hard_ok": hard_ok,
                "soft_penalties": soft_details,
                "metrics": metrics,
            }
        )

    ranking.sort(key=lambda row: row["score"])

    legal = [row for row in ranking if row["hard_ok"]]
    recommended_id = legal[0]["schedule_id"] if legal else None
    all_illegal = bool(candidates) and not legal

    return {
        "recommended_schedule_id": recommended_id,
        "ranking": ranking,
        "hard_violations": all_hard_violations,
        "soft_penalties": all_soft_penalties,
        "recommendation_reason": _recommendation_reason(recommended_id, ranking, all_illegal),
        "warnings": warnings,
    }
