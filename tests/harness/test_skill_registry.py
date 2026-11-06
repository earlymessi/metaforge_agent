import pytest

from metaforge.harness.skill import (
    SkillSpec,
    clear_skills,
    get_skill,
    invoke_skill,
    register_skill,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_skills()
    yield
    clear_skills()


def test_register_and_invoke_skill():
    register_skill(
        SkillSpec(
            id="demo",
            name_zh="演示",
            allowed_tools=["t1"],
            risk_level="allow",
            entrypoint=lambda **kw: {"ok": True, "goal": kw.get("user_goal")},
        )
    )
    spec = get_skill("demo")
    assert spec.allowed_tools == ["t1"]
    out = invoke_skill("demo", user_goal="交期")
    assert out["ok"] is True
    assert out["skill_id"] == "demo"
    assert out["goal"] == "交期"


def test_unknown_skill_raises():
    with pytest.raises(KeyError, match="unknown skill"):
        get_skill("nope")


def test_planning_collab_skill_registered():
    from metaforge.skills.planning_collab import ensure_registered

    ensure_registered()
    spec = get_skill("planning_collab")
    assert "排产" in spec.name_zh
    assert spec.risk_level == "ask"
