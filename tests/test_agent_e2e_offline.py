"""Agent E2E 结构测试（离线，不调用 GLM）。"""

from pathlib import Path

import pytest

from metaforge.eval.agent_e2e import (
    _DATA_ROOT,
    _tools_match,
    _tools_one_of,
    load_cases,
    load_fixture,
)


def test_l2_yaml_loads():
    cases = load_cases("preview")
    ids = {c["id"] for c in cases}
    assert len(cases) >= 60
    assert "L2-SCH-01" in ids
    assert "L2-ADV-12" in ids


def test_l3_yaml_loads():
    cases = load_cases("exec")
    ids = {c["id"] for c in cases}
    assert len(cases) == 65
    assert "L3-SCH-01" in ids
    assert "L3-ADV-12" in ids
    assert "L3-SCH-12" in ids


def test_fixtures_exist():
    assert load_fixture("min_jobs")
    mes = load_fixture("mes_baseline")
    assert mes.get("baseline_gantt")
    assert load_fixture("bom_jobs")


def test_tag_filter_scheduling():
    cases = load_cases("preview", tags=["scheduling"])
    assert cases
    assert all("scheduling" in (c.get("tags") or []) for c in cases)


def test_tools_match_helpers():
    assert _tools_match(["a", "b", "c"], ["a", "b"], ordered=False)
    assert not _tools_match(["a"], ["b"], ordered=False)
    assert _tools_one_of(
        ["scheduling.ask_clarification"],
        [["scheduling.ask_clarification"], ["scheduling.parse_intent", "scheduling.run"]],
    )


def test_data_root_layout():
    assert (_DATA_ROOT / "l2_preview.yaml").is_file()
    assert (_DATA_ROOT / "l3_exec.yaml").is_file()
    assert (_DATA_ROOT / "fixtures" / "min_jobs.json").is_file()
