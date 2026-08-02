from metaforge.strategy.models import Constraint, SchedulingStrategy
from metaforge.strategy.guardrails import validate_strategy


def test_unknown_hard_type_rejected():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="not_a_real_type", params={"job_id": "A"})]
    )
    ok, errors, _ = validate_strategy(s, jobs=[{"job_id": "A"}], machines=["M01"], allow_simulated=True)
    assert ok is False
    assert any("not_a_real_type" in e for e in errors)


def test_order_on_time_missing_job_rejected():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="order_on_time", params={"job_id": "Z99"})]
    )
    ok, errors, _ = validate_strategy(s, jobs=[{"job_id": "A12"}], machines=["M01"], allow_simulated=True)
    assert ok is False


def test_skill_required_injects_simulated_when_allowed():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="skill_required", params={"job_id": "A12", "skill": "weld"})]
    )
    ok, errors, fixed = validate_strategy(
        s, jobs=[{"job_id": "A12"}], machines=["M01"], workers=[], allow_simulated=True
    )
    assert ok is True
    assert "skill_required" in (fixed.provenance.get("simulated_fields") or [])
