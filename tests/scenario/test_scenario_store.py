from metaforge.scenario.store import ScenarioStore
from metaforge.scenario.presets import list_preset_scenarios


def test_scenario_crud_roundtrip():
    store = ScenarioStore()
    for p in list_preset_scenarios():
        store.create(p)
    assert len(store.list()) >= 3
    s = store.list()[0]
    s2 = store.get(s["id"])
    assert s2 is not None
    assert s2["name"] == s["name"]
    assert isinstance(s2["steps"], list)


def test_scenario_update_and_delete():
    store = ScenarioStore()
    created = store.create(
        {
            "name": "custom",
            "steps": [{"event_type": "machine_breakdown", "params": {"machine_id": 1}}],
        }
    )
    updated = store.update(
        created["id"],
        {
            "name": "custom-2",
            "steps": [{"event_type": "due_date_change", "params": {"due_date_changes": []}}],
        },
    )
    assert updated["name"] == "custom-2"
    assert store.delete(created["id"]) is True
    assert store.get(created["id"]) is None
