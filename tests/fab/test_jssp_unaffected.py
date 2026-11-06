"""Guardrails: FAB types must not leak into classic JSSP catalogs."""

from metaforge.fab.catalog import FAB_HARD_CONSTRAINT_TYPES, FAB_SOFT_CONSTRAINT_TYPES
from metaforge.strategy.catalog import (
    HARD_CONSTRAINT_TYPES,
    SOFT_CONSTRAINT_TYPES,
    list_constraint_catalog,
)


def test_fab_hard_types_not_in_jssp_catalog():
    overlap = HARD_CONSTRAINT_TYPES & FAB_HARD_CONSTRAINT_TYPES
    assert not overlap, f"FAB hard types leaked into JSSP catalog: {overlap}"


def test_fab_soft_types_not_in_jssp_catalog():
    overlap = SOFT_CONSTRAINT_TYPES & FAB_SOFT_CONSTRAINT_TYPES
    assert not overlap, f"FAB soft types leaked into JSSP catalog: {overlap}"


def test_default_list_constraint_catalog_has_no_fab_domain():
    catalog = list_constraint_catalog()
    types = {e["type"] for e in catalog}
    assert types.isdisjoint(FAB_HARD_CONSTRAINT_TYPES)
    assert types.isdisjoint(FAB_SOFT_CONSTRAINT_TYPES)
    for entry in catalog:
        assert entry.get("domain") != "fab"


def test_default_catalog_snapshot_size():
    # classic catalog size stable (isolation smoke)
    catalog = list_constraint_catalog()
    hard = [e for e in catalog if e["kind"] == "hard"]
    soft = [e for e in catalog if e["kind"] == "soft"]
    assert len(hard) == len(HARD_CONSTRAINT_TYPES)
    assert len(soft) == len(SOFT_CONSTRAINT_TYPES)
