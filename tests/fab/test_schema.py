from pathlib import Path

import pytest

from metaforge.fab.loader import list_scenario_files, list_scenario_ids, load_scenario, scenarios_dir
from metaforge.fab.schema import validate_scenario_dict


def test_scenarios_dir_exists():
    assert scenarios_dir().is_dir()


def test_three_scenario_packs_load():
    ids = set(list_scenario_ids())
    assert "fab_photo_dedication_v1" in ids
    assert "fab_etch_timelink_v1" in ids
    assert "fab_diffusion_batch_v1" in ids
    for sid in (
        "fab_photo_dedication_v1",
        "fab_etch_timelink_v1",
        "fab_diffusion_batch_v1",
    ):
        pack = load_scenario(sid)
        assert pack.domain == "fab"
        assert pack.scenario_id == sid
        assert pack.entities.get("lots")


def test_all_yaml_files_valid():
    files = list_scenario_files()
    assert len(files) >= 3
    for path in files:
        pack = load_scenario(path.stem)
        assert pack.scenario_id


def test_reject_jssp_shaped_payload():
    ok, errors = validate_scenario_dict(
        {
            "schema_version": "1",
            "scenario_id": "x",
            "domain": "jssp",
            "area": "photolithography",
            "title": "bad",
            "entities": {"machines": [{"id": "M0"}], "lots": [{"id": "L1"}]},
            "constraints_hard": [{"type": "order_on_time"}],
        }
    )
    assert ok is False
    assert any("domain" in e for e in errors)
    assert any("order_on_time" in e or "unknown" in e for e in errors)


def test_path_traversal_rejected():
    with pytest.raises(ValueError):
        load_scenario("../secrets")
