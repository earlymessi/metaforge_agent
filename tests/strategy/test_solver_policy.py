from metaforge.strategy.models import SchedulingStrategy
from metaforge.strategy.adapters import strategy_to_solver_inputs
from metaforge.strategy.solver_policy import build_solver_policy
from metaforge.strategy.capability_matrix import get_capability


def test_adapter_maps_objectives_to_weights():
    s = SchedulingStrategy(objectives={"makespan": 1.0, "weighted_tardiness_total": 2.5})
    weights, hints = strategy_to_solver_inputs(s)
    assert weights["weighted_tardiness_total"] == 2.5
    assert "resource_config_patch" in hints or isinstance(hints, dict)


def test_rl_marked_no_dynamic_weights():
    cap = get_capability("ppo")
    assert cap["supports_dynamic_weights"] is False
    assert cap["family"] == "rl"


def test_policy_prefers_metaheuristic_for_delivery():
    s = SchedulingStrategy(
        base_template="delivery",
        objectives={"weighted_tardiness_total": 2.0, "makespan": 0.8},
    )
    policy = build_solver_policy(s, n_jobs=10)
    assert policy.max_candidates <= 3
    assert "ppo" not in policy.primary_solvers or get_capability("ppo")["supports_dynamic_weights"]
    assert policy.fallback_solver is not None
