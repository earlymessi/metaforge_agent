from metaforge.strategy.run_state import create_run, get_run
from metaforge.strategy.hitl import approve_strategy, reject_strategy, edit_and_approve
from metaforge.strategy.models import Constraint, SchedulingStrategy


def test_approve_moves_to_running_or_ready():
    run = create_run(user_goal="test")
    run["strategy_draft"] = SchedulingStrategy(
        base_template="balanced", objectives={"makespan": 1.0}
    ).to_dict()
    run["status"] = "WAITING_APPROVAL"
    out = approve_strategy(run["run_id"])
    assert out["status"] in ("RUNNING", "APPROVED", "SOLVING")
    assert get_run(run["run_id"])["strategy_approved"] is not None


def test_reject_cancels():
    run = create_run(user_goal="test")
    out = reject_strategy(run["run_id"], reason="nope")
    assert out["status"] in ("CANCELLED", "FAILED")


def test_edit_and_approve_replaces_draft():
    run = create_run(user_goal="test")
    edited = SchedulingStrategy(
        base_template="delivery",
        objectives={"makespan": 0.8, "weighted_tardiness_total": 2.0},
    )
    out = edit_and_approve(run["run_id"], edited.to_dict(), jobs=[], machines=[])
    assert out["strategy_approved"]["base_template"] == "delivery"


def test_edit_and_approve_validation_failure_stays_waiting():
    run = create_run(user_goal="test")
    invalid = SchedulingStrategy(
        hard_constraints=[Constraint(type="order_on_time", params={"job_id": "MISSING"})],
    )
    out = edit_and_approve(run["run_id"], invalid.to_dict(), jobs=[], machines=[])
    assert out["status"] == "WAITING_APPROVAL"
    assert out.get("validation_errors")
