"""排程业务目标推断测试。"""

from metaforge.scheduling.goals import infer_schedule_goal, pick_best_schedule, should_run_full_compare


def test_infer_makespan_goal():
    g = infer_schedule_goal("我想要最短时间排程")
    assert g.goal_id == "makespan"
    assert g.is_clear
    assert should_run_full_compare(g, "我想要最短时间排程")


def test_infer_tardiness_goal():
    g = infer_schedule_goal("尽量减少拖期")
    assert g.goal_id == "weighted_tardiness_total"
    assert g.strategy_id == "delivery"


def test_named_algorithm_skips_full_compare():
    g = infer_schedule_goal("用遗传算法，时间最短")
    assert not should_run_full_compare(g, "用遗传算法，时间最短")


def test_infer_load_balance_uses_composite_score():
    g = infer_schedule_goal("负载均衡排产")
    assert g.goal_id == "machine_busy_cv"
    assert g.recommend_metric == "score"


def test_pick_best_tied_cv_uses_composite_score():
    results = {
        "spt": {
            "metrics": {"machine_busy_cv": 0.4933},
            "score": 41.5,
            "name": "最短加工时间优先",
        },
        "ts": {
            "metrics": {"machine_busy_cv": 0.4933},
            "score": 10.6,
            "name": "禁忌搜索",
        },
    }
    sid, entry, val = pick_best_schedule(results, recommend_metric="machine_busy_cv")
    assert sid == "ts"
    assert entry["name"] == "禁忌搜索"
    sid2, _, val2 = pick_best_schedule(results, recommend_metric="score")
    assert sid2 == "ts"
    assert val2 == 10.6


def test_pick_best_by_tardiness_metric():
    results = {
        "a": {"metrics": {"weighted_tardiness_total": 10.0}, "name": "A"},
        "b": {"metrics": {"weighted_tardiness_total": 3.0}, "name": "B"},
    }
    sid, entry, val = pick_best_schedule(results, recommend_metric="weighted_tardiness_total")
    assert sid == "b"
    assert val == 3.0
