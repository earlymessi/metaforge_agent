"""LLM 链与解析测试。"""

from metaforge.orchestrator.llm import parsers, prompts


def test_router_prompt():
    sys_prompt = prompts.router_system()
    assert "Intent Router" in sys_prompt or "意图识别" in sys_prompt
    assert "schedule" in sys_prompt
    assert "kitting" in sys_prompt
    assert "whatif" in sys_prompt
    assert "schedule" in sys_prompt


def test_scheduling_prompt_list_and_benchmark():
    sys_prompt = prompts.scheduling_system()
    assert "LIST_SOLVERS" in sys_prompt
    assert "RUN_BENCHMARK" in sys_prompt
    assert "有哪些算法" in sys_prompt


def test_react_reflect_use_structured_prompt():
    from metaforge.agents.scheduling import SchedulingAgentRunner

    react = prompts.react_system(
        agent_id="scheduling",
        name_zh=SchedulingAgentRunner.name_zh,
        allowed_tools=SchedulingAgentRunner.allowed_tools,
    )
    assert "ReAct" in react
    assert "finish" in react
    reflect = prompts.reflect_system(
        agent_id="scheduling",
        name_zh=SchedulingAgentRunner.name_zh,
        allowed_tools=SchedulingAgentRunner.allowed_tools,
    )
    assert "retry" in reflect
    assert "human" in reflect


def test_scheduling_plan_prompt_includes_persist_tools():
    from metaforge.agents.scheduling import SchedulingAgentRunner

    sys_prompt = prompts.plan_system(
        agent_id="scheduling",
        name_zh=SchedulingAgentRunner.name_zh,
        allowed_tools=SchedulingAgentRunner.allowed_tools,
    )
    assert "data.load_plan" in sys_prompt
    assert "data.propose_persist" in sys_prompt


def test_scheduling_prompt_has_reasoning_steps():
    assert "reasoning_steps" in prompts.scheduling_system()


def test_normalize_event_coerces_now_string():
    out = parsers.parse_event(
        {
            "event_type": "machine_breakdown",
            "params": {
                "machine_id": 2,
                "breakdown_start": "now",
                "breakdown_duration": "4h",
            },
        },
        message="3号机坏了",
    )
    assert out["params"]["breakdown_start"] == 0.0
    assert out["params"]["breakdown_duration"] == 4.0
