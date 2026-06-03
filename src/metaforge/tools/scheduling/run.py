"""scheduling.run — 封装 compare_solvers。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from metaforge.problems.benchmark_loader import load_job_shop_instance
from metaforge.utils.compare_solvers import compare_solvers
from metaforge.utils.problem_builder import apply_downtime_blocks, build_problem_from_custom_jobs
from metaforge.tools.base import ToolContext, ToolResult, ToolSpec
from metaforge.tools.registry import get_tool, register_tool

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "solvers": {"type": "array", "items": {"type": "string"}},
        "weights": {"type": "object"},
        "random_seed": {"type": "integer"},
        "benchmark_file": {"type": "string"},
    },
}

_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {"type": "object"},
        "job_name_map": {"type": "object"},
    },
}


def _benchmarks_dir() -> Path:
    # src/metaforge/tools/scheduling/run.py -> repo root
    root = Path(__file__).resolve().parents[4]
    return root / "tests" / "data" / "benchmarks"


def _handle_scheduling_run(params: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    interp = (ctx.artifacts or {}).get("interpretation") or {}
    if interp.get("intent_type") == "CLARIFICATION" or interp.get("needs_user_reply"):
        return ToolResult(
            ok=False,
            error=interp.get("clarification_question")
            or interp.get("parse_note_zh")
            or "排程目标不明确，请先回答澄清问题后再执行",
        )

    solvers: List[str] = list(params.get("solvers") or [])
    if not solvers:
        solvers = list(interp.get("solvers") or ["spt", "ts"])
    if not solvers:
        return ToolResult(ok=False, error="solvers is required")

    bench_early = params.get("benchmark_file") or ctx.benchmark_file
    if not bench_early:
        interp_early = (ctx.artifacts or {}).get("interpretation") or {}
        bench_early = interp_early.get("benchmark_file")
    custom = ctx.custom_data
    problem_preset = ctx.extras.get("problem")
    if not bench_early and problem_preset is None:
        if not custom or not isinstance(custom, list) or len(custom) == 0:
            return ToolResult(
                ok=False,
                error="当前计划没有工单数据，请先在排程中心添加工单，或绑定含工单的计划后再排产",
            )
        has_tasks = any(
            (getattr(j, "tasks", None) or (j.get("tasks") if isinstance(j, dict) else None))
            for j in custom
        )
        if not has_tasks:
            return ToolResult(
                ok=False,
                error="工单中无工序(tasks)，无法排产，请在排程中心编辑工单",
            )

    weights = params.get("weights") or ctx.weights
    if weights is None:
        interp = (ctx.artifacts or {}).get("interpretation") or {}
        weights = interp.get("weights")

    random_seed = params.get("random_seed", ctx.random_seed)
    resource_config = ctx.extras.get("resource_config")

    problem = ctx.extras.get("problem")
    job_name_map: Dict[int, str] = {}
    job_priority_map: Dict[int, int] = {}

    if problem is None:
        bench = params.get("benchmark_file") or ctx.benchmark_file
        if not bench:
            interp = (ctx.artifacts or {}).get("interpretation") or {}
            bench = interp.get("benchmark_file")
        if bench:
            path = _benchmarks_dir() / bench
            if not path.exists():
                return ToolResult(ok=False, error=f"Benchmark not found: {bench}")
            problem = load_job_shop_instance(str(path), format="orlib")
        elif ctx.custom_data:
            problem, job_name_map, job_priority_map = build_problem_from_custom_jobs(
                ctx.custom_data,
                instance_name="Custom Plan",
            )
        else:
            return ToolResult(ok=False, error="Need problem in extras, custom_data, or benchmark_file")

    apply_downtime_blocks(problem, resource_config)

    results = compare_solvers(
        solvers,
        problem,
        weights=weights,
        resource_config=resource_config,
        random_seed=random_seed,
    )

    data = {
        "results": results,
        "job_name_map": job_name_map,
        "job_priority_map": job_priority_map,
        "solvers": solvers,
    }
    if ctx.artifacts is not None:
        ctx.artifacts["schedule_results"] = results
    return ToolResult(ok=True, data=data, artifacts_key="schedule_results")


def register_scheduling_run_tool() -> None:
    name = "scheduling.run"
    try:
        get_tool(name)
        return
    except KeyError:
        pass
    register_tool(
        ToolSpec(
            name=name,
            description_zh="执行排程对比计算，返回各算法结果",
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            handler=_handle_scheduling_run,
        )
    )
