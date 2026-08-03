from metaforge.planning_collab.summarize import summarize_agent_result


def test_summarize_returns_none_on_failure():
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("down")

    assert summarize_agent_result({"critical_orders": ["A"]}, llm_client=Boom()) is None


def test_summarize_returns_none_without_client():
    assert summarize_agent_result({"critical_orders": ["A"]}, llm_client=None) is None


def test_summarize_ok():
    class Ok:
        def complete(self, *a, **k):
            return "重点保证A"

    assert "A" in (summarize_agent_result({"critical_orders": ["A"]}, llm_client=Ok()) or "")
