from metaforge.fab.catalog import FAB_HARD_CONSTRAINT_TYPES
from metaforge.strategy.catalog import HARD_CONSTRAINT_TYPES, list_constraint_catalog
from metaforge.strategy.guardrails import validate_strategy
from metaforge.strategy.models import Constraint, SchedulingStrategy


def test_fab_type_rejected_without_domain():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="photo_machine_dedication", params={})]
    )
    ok, errors, _ = validate_strategy(
        s, jobs=[{"job_id": "L1"}], machines=[{"id": "P1"}], allow_simulated=True
    )
    assert ok is False
    assert any("photo_machine_dedication" in e for e in errors)


def test_fab_type_accepted_with_domain_fab():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="photo_machine_dedication", params={})]
    )
    ok, errors, _ = validate_strategy(
        s,
        jobs=[{"job_id": "L1"}],
        machines=[{"id": "P1"}],
        allow_simulated=True,
        domain="fab",
    )
    assert ok is True, errors


def test_catalog_default_excludes_fab():
    types = {e["type"] for e in list_constraint_catalog()}
    assert types.isdisjoint(FAB_HARD_CONSTRAINT_TYPES)
    assert HARD_CONSTRAINT_TYPES.issubset(types)


def test_catalog_fab_includes_fab_types():
    types = {e["type"] for e in list_constraint_catalog(domain="fab")}
    assert FAB_HARD_CONSTRAINT_TYPES.issubset(types)
