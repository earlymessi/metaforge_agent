from metaforge.strategy.pipeline import run_planning


def test_run_planning_with_preset_id_skips_nl_generate(monkeypatch):
    calls = {"generate": 0}

    def boom(**kwargs):
        calls["generate"] += 1
        raise AssertionError("generate_strategy should not be called when preset_id set")

    monkeypatch.setattr("metaforge.strategy.pipeline.generate_strategy", boom)

    def fake_finish(run_id, *, strategy, jobs, problem):
        return {
            "status": "COMPLETED",
            "run_id": run_id,
            "package": {
                "recommended_schedule_id": "edd",
                "strategy": strategy.to_dict(),
            },
        }

    monkeypatch.setattr("metaforge.strategy.pipeline._finish_planning", fake_finish)

    out = run_planning(
        user_goal="",
        jobs=[{"job_id": "A", "due_date": 20, "tasks": [{"machine_id": 0, "duration": 1}]}],
        machines=["0"],
        skip_strategy_hitl=True,
        preset_id="delivery",
    )
    assert calls["generate"] == 0
    assert out["status"] == "COMPLETED"
    assert out["package"]["strategy"]["base_template"] == "delivery"
    assert out["package"]["strategy"]["generated_by"] == "preset"


def test_run_planning_unknown_preset_raises():
    import pytest

    with pytest.raises(ValueError, match="Unknown preset"):
        run_planning(
            user_goal="",
            jobs=[],
            machines=[],
            skip_strategy_hitl=True,
            preset_id="not_a_real_preset",
        )
