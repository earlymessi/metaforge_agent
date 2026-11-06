# ToolExecutor + Memory 边界 实现计划

> **面向 AI 代理的工作者：** 必需子技能：executing-plans 或 subagent-driven-development。

**目标：** 落地统一 ToolExecutor 与 State/Memory 边界检查；`run_tool` 委托 Executor。

**规格：** [`../specs/2026-08-09-tool-executor-memory-boundary-design.md`](../specs/2026-08-09-tool-executor-memory-boundary-design.md)

---

### 任务 1：ToolExecutor

- [x] `harness/tool_executor.py` + `tests/harness/test_tool_executor.py`
- [x] deny / ask / allow、required 校验、timeout、retry、events
- [x] `registry.run_tool` 委托 `execute_tool`

### 任务 2：Memory 边界

- [x] `memory/boundary.py` + 测试
- [x] `MemoryManager.set_working` / `patch_working` 接入 check
- [x] 更新 plans/README 索引

### 验收

- [x] `pytest tests/harness tests/strategy/test_planning_tools.py` 绿
- [x] ask 无批准 → needs_hitl；skip_strategy_hitl 可跑通 planning.run
