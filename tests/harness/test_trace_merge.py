from metaforge.harness.trace import merge_run_trace


def test_merge_keeps_legacy_blocks_and_events():
    merged = merge_run_trace(
        run_id="r1",
        run_events=[{"type": "agent.start", "agent_id": "order"}],
        collab_trace={
            "type": "collab_trace",
            "collab_run_id": "c1",
            "strategy_trace": {"type": "strategy_trace", "run_id": "p1"},
        },
    )
    assert merged["type"] == "run_trace"
    assert merged["event_count"] == 1
    assert merged["collab_trace"]["collab_run_id"] == "c1"
    assert merged["strategy_trace"]["run_id"] == "p1"
