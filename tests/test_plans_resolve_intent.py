"""计划意图解析：LLM 优先 → 精确规则 → 短语兜底。"""

from metaforge.plans.intent import parse_plan_intent, rule_fallback_plan_intent, should_navigate_aps
from metaforge.plans.resolve_intent import intent_to_plan_steps, resolve_plan_intent


def test_rule_create_navigates_aps():
    p = parse_plan_intent("新建计划试产01")
    assert p["action"] == "create"
    assert p.get("navigate_aps") is True


def test_rule_delete_no_navigate():
    p = parse_plan_intent("删除计划旧版")
    assert p["action"] == "delete"
    assert "navigate_aps" not in p


def test_rule_rename_navigates():
    p = parse_plan_intent("重命名计划A为计划B")
    assert p["action"] == "rename"
    assert p.get("navigate_aps") is True


def test_rule_list_no_navigate():
    p = parse_plan_intent("列出所有计划")
    assert p["action"] == "list"
    assert "navigate_aps" not in p


def test_rule_no_fuzzy_match():
    assert parse_plan_intent("用遗传算法排产") is None
    assert parse_plan_intent("查看一下排程结果") is None


def test_fallback_view_named_plan():
    fb = rule_fallback_plan_intent("查看计划 sss")
    assert fb["action"] == "view"
    assert fb["query"] == "sss"
    assert fb.get("navigate_aps") is True


def test_intent_steps_bind_navigate():
    steps = intent_to_plan_steps({"action": "view", "query": "sss", "navigate_aps": True})
    assert steps[0].tool == "data.bind_plan"
    assert steps[0].params.get("navigate_aps") is True


def test_intent_steps_delete_no_navigate_tool():
    steps = intent_to_plan_steps({"action": "delete", "query": "x"})
    assert steps[0].tool == "data.delete_plan"


def test_should_navigate_aps_matrix():
    assert should_navigate_aps("create")
    assert should_navigate_aps("view")
    assert not should_navigate_aps("delete")
    assert not should_navigate_aps("list")


def test_resolve_rule_layer(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "0")
    intent, planner = resolve_plan_intent("新建计划abc")
    assert planner == "rule"
    assert intent["action"] == "create"
    assert intent["plan_name"] == "abc"
