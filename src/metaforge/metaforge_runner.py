import inspect

from metaforge.utils.solver_registry import (
    build_run_kwargs,
    get_solver_spec,
    instantiate_solver,
    resolve_solver_id,
)


def run_solver(solver_name, problem, track_schedule=True, dynamic_events=None, **kwargs):
    """
    通用求解器运行入口（基于 SolverRegistry）。

    Parameters
    ----------
    solver_name : str
        求解器 ID，见 ``GET /api/solvers/catalog``。
    problem : JobShopProblem
    track_schedule, dynamic_events :
        保留兼容；当前由 problem / run 内部处理。
    **kwargs :
        weights, resource_config, random_seed, solver_params 及算法特有参数。
    """
    del track_schedule, dynamic_events

    solver_id = resolve_solver_id(solver_name)
    spec = get_solver_spec(solver_id)
    solver_params = kwargs.pop("solver_params", None)

    solver = instantiate_solver(solver_id, problem, solver_params=solver_params)
    run_kwargs = build_run_kwargs(solver_id, solver_params=solver_params, **kwargs)

    run_sig = inspect.signature(solver.run)
    run_names = set(run_sig.parameters.keys()) - {"self"}
    filtered = {k: v for k, v in run_kwargs.items() if k in run_names}

    raw = solver.run(**filtered)
    if isinstance(raw, dict):
        raw.setdefault("solver_id", solver_id)
        raw.setdefault("optimization_mode", spec.optimization_mode)
    return raw
