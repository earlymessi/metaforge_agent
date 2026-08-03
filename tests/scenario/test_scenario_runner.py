from metaforge.scenario.runner import run_scenario


def test_runner_stops_on_step_failure():
    calls = []

    def fake_dispatch(envelope):
        event_type = envelope.get("event_type")
        calls.append(event_type)
        if event_type == "machine_breakdown":
            raise RuntimeError("boom")
        return {"ok": True, "impact_report": {"r0": True}}

    scenario = {
        "id": "s1",
        "name": "two-step",
        "steps": [
            {"event_type": "machine_breakdown", "params": {"machine_id": 0}},
            {"event_type": "due_date_change", "params": {}},
        ],
    }
    out = run_scenario(scenario, envelope={"base_jobs": [{"name": "J1"}]}, dispatch=fake_dispatch)
    assert out["status"] == "failed"
    assert len(out["timeline"]) == 1
    assert out["timeline"][0]["status"] == "failed"
    assert calls == ["machine_breakdown"]


def test_runner_completes_all_steps():
    def fake_dispatch(envelope):
        return {"ok": True, "impact_report": {"event_type": envelope["event_type"]}}

    scenario = {
        "name": "ok",
        "steps": [
            {"event_type": "machine_breakdown", "params": {}},
            {"event_type": "insert_order", "params": {}},
        ],
    }
    out = run_scenario(scenario, envelope={}, dispatch=fake_dispatch)
    assert out["status"] == "completed"
    assert len(out["timeline"]) == 2
    assert out["impact"]["event_type"] == "insert_order"


def test_runner_stops_on_result_error():
    def fake_dispatch(envelope):
        return {"error": "missing jobs"}

    out = run_scenario(
        {"steps": [{"event_type": "machine_breakdown", "params": {}}]},
        dispatch=fake_dispatch,
    )
    assert out["status"] == "failed"
    assert out["timeline"][0]["error"] == "missing jobs"
