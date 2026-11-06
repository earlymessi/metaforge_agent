"""Orchestrate FAB research-lab solve experiments."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metaforge.fab.loader import load_scenario
from metaforge.fab.research.batch_construct import run_batch_construct
from metaforge.fab.research.dedication import run_dedication_method
from metaforge.fab.research.methods import get_method, list_methods
from metaforge.fab.research.timelink_dispatch import run_timelink_method
from metaforge.fab.to_planning import pack_to_planning
from metaforge.strategy.evaluator import evaluate_candidates
from metaforge.strategy.models import SchedulingStrategy

PHYSICS_BLURBS = {
    "photolithography": "natural bias → overlay 风险 → 关键层后后续光刻必须粘同一 stepper",
    "etch_timelink": "清洗/刻蚀后表面时效 → 工序间 max_lag 硬时间窗",
    "diffusion_furnace": "配方交叉污染 + 热场同步 → 同族批处理且批内同步起止",
}


def _merge_model(planning: Dict[str, Any], model: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not model:
        return planning
    out = dict(planning)
    if model.get("jobs") is not None:
        out["jobs"] = list(model["jobs"])
    if model.get("machines") is not None:
        out["machines"] = list(model["machines"])
    if model.get("strategy_defaults") is not None:
        out["strategy_defaults"] = dict(model["strategy_defaults"])
    if model.get("fab_meta") is not None:
        base_meta = dict(out.get("fab_meta") or {})
        base_meta.update(dict(model["fab_meta"]))
        out["fab_meta"] = base_meta
    return out


def _run_preprocess_solver(
    card: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    *,
    fab_meta: Dict[str, Any],
    strategy_defaults: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    preprocess = card["preprocess"]
    solver_id = card.get("solver_id")
    solver_params = params.get("solver_params")

    if preprocess == "dedication_bind":
        return run_dedication_method(
            jobs, solver_id=str(solver_id or "spt"), solver_params=solver_params
        )
    if preprocess == "timelink_slack":
        return run_timelink_method(
            jobs,
            fab_meta=fab_meta,
            strategy_defaults=strategy_defaults,
            mode="slack",
            solver_id=str(solver_id or "spt"),
            solver_params=solver_params,
        )
    if preprocess == "timelink_edd":
        return run_timelink_method(
            jobs,
            fab_meta=fab_meta,
            strategy_defaults=strategy_defaults,
            mode="edd",
            solver_id=str(solver_id or "edd"),
            solver_params=solver_params,
        )
    if preprocess == "batch_construct":
        return run_batch_construct(jobs, fab_meta=fab_meta)
    raise ValueError(f"unknown preprocess: {preprocess}")


def run_research_solve(
    scenario_id: str,
    method: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    model: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    params = params or {}
    card = get_method(method)
    if card is None:
        raise ValueError(f"unknown FAB research method: {method}")

    pack = load_scenario(scenario_id)
    planning = _merge_model(pack_to_planning(pack), model)
    area = str((planning.get("fab_meta") or {}).get("area") or pack.area)
    if card["area"] != area:
        raise ValueError(
            f"method {method!r} is for area {card['area']!r}, "
            f"model/scenario area is {area!r}"
        )

    jobs = list(planning["jobs"])
    strategy_defaults = dict(planning.get("strategy_defaults") or {})
    fab_meta = dict(planning.get("fab_meta") or {})
    trace: List[Dict[str, str]] = []
    if model:
        trace.append(
            {
                "step": "model_override",
                "detail": "using editable model draft from research lab",
            }
        )

    trace.append(
        {
            "step": "physics",
            "detail": PHYSICS_BLURBS.get(area, area)
            + f"；refs={', '.join(pack.physics_refs[:3])}",
        }
    )
    hard_types = [c.get("type") for c in strategy_defaults.get("hard_constraints") or []]
    trace.append(
        {
            "step": "constraints",
            "detail": f"registered hard={hard_types}",
        }
    )
    trace.append(
        {
            "step": "method_compose",
            "detail": (
                f"preprocess={card['preprocess']}; "
                f"reuses={card.get('reuses')}; "
                f"family={card.get('family')}"
            ),
        }
    )

    result = _run_preprocess_solver(
        card,
        jobs,
        fab_meta=fab_meta,
        strategy_defaults=strategy_defaults,
        params=params,
    )
    if card["preprocess"] == "dedication_bind":
        encode_detail = "; ".join(result.get("bind_notes") or []) + f"; solver={result.get('solver_id')}"
    elif card["preprocess"].startswith("timelink"):
        encode_detail = "; ".join(result.get("timelink_notes") or []) + f"; solver={result.get('solver_id')}"
    else:
        encode_detail = "; ".join(result.get("batch_notes") or [])
    trace.append({"step": "encode_decode", "detail": encode_detail or method})

    strategy = SchedulingStrategy.from_dict(strategy_defaults)
    eval_jobs = result.get("jobs") or jobs
    candidate = {
        "schedule_id": result.get("schedule_id") or method,
        "gantt_data": result.get("gantt_data") or [],
        "metrics": result.get("metrics") or {},
        "fab_batches": result.get("fab_batches"),
    }
    evaluation = evaluate_candidates(
        strategy,
        [candidate],
        jobs=eval_jobs,
        domain="fab",
        fab_meta=fab_meta,
    )
    hard_ok = bool((evaluation.get("ranking") or [{}])[0].get("hard_ok"))
    n_viol = len(evaluation.get("hard_violations") or [])
    trace.append({"step": "hard_check", "detail": f"hard_ok={hard_ok}; violations={n_viol}"})
    mk = (result.get("metrics") or {}).get("makespan")
    trace.append({"step": "metrics", "detail": f"makespan={mk}"})

    return {
        "domain": "fab",
        "scenario_id": pack.scenario_id,
        "area": area,
        "method": card["id"],
        "method_title": card.get("title"),
        "method_family": card.get("family"),
        "reuses": card.get("reuses"),
        "model_snapshot": {
            "jobs": eval_jobs,
            "machines": planning.get("machines") or [],
            "constraints_hard": strategy_defaults.get("hard_constraints") or [],
            "constraints_soft": strategy_defaults.get("soft_constraints") or [],
            "fab_meta": fab_meta,
            "physics_refs": list(pack.physics_refs),
            "out_of_scope": list(pack.out_of_scope),
            "title": pack.title,
        },
        "method_trace": trace,
        "schedule": {
            "gantt_data": result.get("gantt_data") or [],
            "metrics": result.get("metrics") or {},
            "fab_batches": result.get("fab_batches"),
            "schedule_id": result.get("schedule_id") or method,
            "fab_hard_ok": hard_ok,
        },
        "fab_evaluation": evaluation,
        "params": params,
    }


def run_research_compare(
    scenario_id: str,
    methods: List[str],
    *,
    model: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run multiple FAB methods on the same model; return ranked summary."""
    if not methods:
        raise ValueError("methods list is empty")
    rows = []
    details = []
    for mid in methods:
        out = run_research_solve(scenario_id, mid, model=model, params=params)
        hard_ok = bool(out.get("schedule", {}).get("fab_hard_ok"))
        mk = (out.get("schedule", {}).get("metrics") or {}).get("makespan")
        viol = len((out.get("fab_evaluation") or {}).get("hard_violations") or [])
        rows.append(
            {
                "method": out["method"],
                "title": out.get("method_title"),
                "family": out.get("method_family"),
                "reuses": out.get("reuses"),
                "fab_hard_ok": hard_ok,
                "makespan": mk,
                "violations": viol,
            }
        )
        details.append(out)

    # legal first, then lower makespan
    def _key(r: Dict[str, Any]):
        mk = r.get("makespan")
        try:
            mkf = float(mk)
        except (TypeError, ValueError):
            mkf = 1e18
        return (0 if r.get("fab_hard_ok") else 1, mkf)

    ranking = sorted(rows, key=_key)
    return {
        "domain": "fab",
        "scenario_id": scenario_id,
        "ranking": ranking,
        "results": details,
        "recommendation": ranking[0]["method"] if ranking else None,
    }


__all__ = ["list_methods", "run_research_solve", "run_research_compare", "get_method"]
