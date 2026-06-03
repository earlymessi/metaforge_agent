"""能耗配置与指标计算。"""

from metaforge.services.resource_config import default_resource_config, effective_resource_config
from metaforge.utils.metrics import compute_schedule_metrics


def test_energy_cost_computed_without_explicit_config():
    schedule = [
        {"job_id": 0, "machine_id": 0, "start": 0.0, "end": 5.0},
        {"job_id": 0, "machine_id": 1, "start": 5.0, "end": 12.0},
    ]
    metrics = compute_schedule_metrics(schedule, problem=type("P", (), {"jobs": []})())
    assert metrics["energy_cost"] is not None
    assert metrics["energy_cost"] > 0


def test_effective_resource_config_merges_partial():
    cfg = effective_resource_config({"machine_powers": {"0": 9.0}})
    assert cfg["machine_powers"]["0"] == 9.0
    assert len(cfg["hourly_prices"]) == 24


def test_infer_cost_goal_uses_composite_score():
    from metaforge.scheduling.goals import infer_schedule_goal

    g = infer_schedule_goal("成本优先排产")
    assert g.goal_id == "energy_cost"
    assert g.strategy_id == "cost"
    assert g.recommend_metric == "score"
