from metaforge.events_collab.trace import build_events_trace


def test_build_events_trace_minimal():
    tr = build_events_trace(
        status="success",
        stages=["parse", "reschedule", "explain"],
        event_type="machine_breakdown",
        tool_log=[{"tool": "events.reschedule", "ok": True}],
        warnings=[],
    )
    assert tr["status"] == "success"
    assert tr["event_type"] == "machine_breakdown"
    assert "events.reschedule" in [x["tool"] for x in tr["tool_log"]]
    assert tr["stages"] == ["parse", "reschedule", "explain"]
