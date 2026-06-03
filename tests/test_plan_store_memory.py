"""内存 plan_store 单测。"""

from metaforge.services import plan_store
from metaforge.services.plan_store_memory import InMemoryPlanCollection, seed_default_e2e_plans


def test_in_memory_plan_crud():
    configure = plan_store.configure_plan_store
    configure(InMemoryPlanCollection())
    doc, err = plan_store.create_plan(plan_name="E2E-Unit", jobs=[])
    assert err is None and doc and doc.get("id")
    pid = doc["id"]
    got, err2 = plan_store.get_plan(pid)
    assert err2 is None and got["plan_name"] == "E2E-Unit"
    listed, err3 = plan_store.list_plans()
    assert err3 is None and any(p["id"] == pid for p in listed)


def test_seed_default_e2e_plans():
    configure = plan_store.configure_plan_store
    configure(InMemoryPlanCollection())
    ids = seed_default_e2e_plans([])
    assert ids.get("E2E-Persist-Base")
