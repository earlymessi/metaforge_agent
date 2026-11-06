# ToolExecutor + State/Memory 边界 设计规范

> 日期：2026-08-09  
> 状态：已批准（对话确认）  
> 范围：第一档 #2 Tool 工程化、#5 State/Memory 边界；智能排产主线优先  
> 前置：S5 薄 Harness（Runtime / Context / Skill）

---

## 1. 目标

1. **ToolExecutor**：统一 `lookup → risk → 入参校验 → 执行(timeout/retry) → 出参校验 → RunEvent`，替代「裸调 handler」。
2. **Memory 边界**：区分 TaskState / Session Memory / 业务事实，禁止把甘特、库存等当作 Memory 权威源。

## 2. ToolExecutor

- 入口：`metaforge.harness.tool_executor.execute_tool`；`tools.registry.run_tool` 委托之。
- **deny**：永不执行。
- **ask**：无批准则 `ok=False` 且 `data.needs_hitl=True`；批准来源：`ctx.extras.tool_approved`、`params._tool_approved`、或 `skip_strategy_hitl=True`（显式跳过策略 HITL 的排产调用）。
- **allow**：直接执行。
- Schema：无 jsonschema 依赖时做轻量校验（required + 基础 type）；过宽 `object` 仅要求 dict。
- timeout：`ThreadPoolExecutor` + `timeout_seconds`；retry：读 `retry_policy.max_retries`。

## 3. State / Memory

| 层 | 存什么 | 不存什么 |
|----|--------|----------|
| PlanningTaskState | 一次排产 artifacts、阶段 | 长期偏好 |
| Session Memory | working 澄清、scheduling 偏好、episodic 摘要 | 整表 jobs/gantt/库存权威副本 |
| Mongo/Service | 订单、设备、计划、甘特 | — |

提供 `classify_payload` / `check_memory_write`；`MemoryManager` 写入时记录 warnings；`METAFORGE_MEMORY_STRICT=1` 时对事实键写入 raise。

## 4. 非目标

全面补全所有 Tool 的精细 schema；MCP；通信协议大改；LangGraph。
