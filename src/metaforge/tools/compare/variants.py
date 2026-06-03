"""compare.variants — 多方案 what-if 对比。"""

from __future__ import annotations

from typing import Any, Dict, List

from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool, run_tool


def _best_entry(results: Dict[str, Any]) -> tuple:
    best_sid = None
    best_entry: Dict[str, Any] = {}
    best_score = float("inf")
    for sid, entry in (results or {}).items():
        if entry.get("error"):
            continue
        sc = float(entry.get("best_score") or entry.get("score") or 0)
        if sc > 0 and sc < best_score:
            best_score = sc
            best_sid = sid
            best_entry = entry
    if best_sid is None and results:
        best_sid = next(iter(results.keys()))
        best_entry = results[best_sid]
    return best_sid, best_entry


def _metric_value(entry: Dict[str, Any], metric: str) -> float:
    metrics = entry.get("metrics") or {}
    if metric == "makespan":
        return float(metrics.get("makespan") or entry.get("makespan") or 0)
    if metric == "weighted_tardiness_total":
        return float(metrics.get("weighted_tardiness_total") or 0)
    return float(entry.get("best_score") or entry.get("score") or 0)


def _run_single_variant(
    variant: Dict[str, Any],
    ctx: ToolContext,
) -> Dict[str, Any]:
    label = variant.get("label") or variant.get("variant_id") or "variant"
    sched = variant.get("scheduling") or {}
    event = variant.get("event")

    sub = ToolContext(
        custom_data=ctx.custom_data,
        benchmark_file=ctx.benchmark_file,
        weights=sched.get("weights") or ctx.weights,
        enforce_material=bool(sched.get("enforce_material", ctx.enforce_material)),
        random_seed=sched.get("random_seed", ctx.random_seed),
        artifacts={},
        extras=dict(ctx.extras),
    )
    sub.extras["resource_config"] = ctx.extras.get("resource_config")
    if sched.get("problem"):
        sub.extras["problem"] = sched["problem"]
    elif ctx.extras.get("problem"):
        sub.extras["problem"] = ctx.extras["problem"]

    interp = {
        "solvers": sched.get("solvers") or ["spt", "ts"],
        "weights": sched.get("weights") or ctx.weights,
        "strategy_id": sched.get("strategy_id"),
        "enforce_material": sched.get("enforce_material"),
    }
    sub.artifacts["interpretation"] = interp

    if event:
        envelope = {
            "event_type": event.get("event_type"),
            "base_jobs": ctx.custom_data or event.get("base_jobs") or [],
            "params": event.get("params") or {},
            "reschedule_options": {
                "solvers": sched.get("solvers") or ["spt"],
                "weights": sched.get("weights"),
                "random_seed": sched.get("random_seed"),
                "resource_config": ctx.extras.get("resource_config"),
            },
        }
        r = run_tool("events.reschedule", {"event_envelope": envelope}, sub)
        if not r.ok:
            return {"label": label, "error": r.error}
        results = (r.data or {}).get("results") or sub.artifacts.get("schedule_results") or {}
    else:
        r = run_tool(
            "scheduling.run",
            {
                "solvers": sched.get("solvers"),
                "weights": sched.get("weights"),
                "random_seed": sched.get("random_seed"),
            },
            sub,
        )
        if not r.ok:
            return {"label": label, "error": r.error}
        results = sub.artifacts.get("schedule_results") or (r.data or {}).get("results") or {}

    sid, entry = _best_entry(results)
    return {
        "label": label,
        "variant_id": variant.get("variant_id") or label,
        "best_solver": sid,
        "schedule_result": entry,
        "results": results,
        "metrics": entry.get("metrics") or {},
        "makespan": _metric_value(entry, "makespan"),
        "best_score": float(entry.get("best_score") or entry.get("score") or 0),
    }


def compare_variant_summaries(
    summaries: List[Dict[str, Any]],
    *,
    recommend_metric: str = "best_score",
) -> Dict[str, Any]:
    valid = [s for s in summaries if not s.get("error")]
    if not valid:
        return {
            "variants": summaries,
            "recommendation": None,
            "recommendation_reason_zh": "所有方案均未成功执行。",
            "insignificant_diff": False,
        }

    def key_fn(s: Dict[str, Any]) -> float:
        if recommend_metric == "makespan":
            return float(s.get("makespan") or 0)
        return float(s.get("best_score") or 0)

    ranked = sorted(valid, key=key_fn)
    best = ranked[0]
    worst = ranked[-1]
    makespans = [float(s.get("makespan") or 0) for s in valid if float(s.get("makespan") or 0) > 0]
    insignificant = False
    if len(makespans) >= 2:
        lo, hi = min(makespans), max(makespans)
        if lo > 0 and (hi - lo) / lo < 0.01:
            insignificant = True

    reason = (
        f"推荐方案「{best.get('label')}」（{recommend_metric}={key_fn(best):.4f}），"
        f"最优算法 {best.get('best_solver')}。"
    )
    if insignificant:
        reason += " 各方案 makespan 差异不足 1%，方案差异不显著。"

    return {
        "variants": summaries,
        "recommendation": best.get("variant_id") or best.get("label"),
        "recommended_label": best.get("label"),
        "recommendation_reason_zh": reason,
        "insignificant_diff": insignificant,
        "ranking": [
            {
                "label": s.get("label"),
                "makespan": s.get("makespan"),
                "best_score": s.get("best_score"),
                "best_solver": s.get("best_solver"),
            }
            for s in ranked
        ],
    }


def _handle(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    variants: List[Dict[str, Any]] = list(params.get("variants") or [])
    if not variants:
        return ToolResult(ok=False, error="variants required")

    recommend_metric = str(params.get("recommend_metric") or "best_score")
    summaries: List[Dict[str, Any]] = []
    for v in variants:
        summaries.append(_run_single_variant(v, ctx))

    what_if = compare_variant_summaries(summaries, recommend_metric=recommend_metric)
    if ctx.artifacts is not None:
        ctx.artifacts["what_if"] = what_if
        rec_label = what_if.get("recommended_label")
        for s in summaries:
            if s.get("label") == rec_label and s.get("results"):
                ctx.artifacts["schedule_results"] = s["results"]
    return ToolResult(ok=True, data=what_if, artifacts_key="what_if")


def register_compare_variants_tool() -> None:
    name = "compare.variants"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="对多个排程/重排方案进行对比并给出推荐",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=_handle,
        )
    )
