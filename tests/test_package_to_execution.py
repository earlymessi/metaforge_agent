from metaforge.services.package_to_execution import extract_recommended_gantt


def test_extract_recommended_gantt_from_package():
    package = {
        "recommended_schedule_id": "edd",
        "evaluation": {
            "recommended_schedule_id": "edd",
            "candidates": [
                {"schedule_id": "edd", "solver": "edd", "gantt_data": [{"Job": "A", "Start": 0, "Finish": 2}]},
            ],
        },
    }
    solver_id, gantt = extract_recommended_gantt(package=package, candidates=None)
    assert solver_id == "edd"
    assert len(gantt) == 1


def test_extract_fails_without_recommendation():
    import pytest
    with pytest.raises(ValueError, match="recommended"):
        extract_recommended_gantt(package={"recommended_schedule_id": None}, candidates=[])
