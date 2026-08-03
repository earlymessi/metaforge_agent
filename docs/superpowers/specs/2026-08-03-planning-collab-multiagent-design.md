# MetaForge S2：Planning Collab Multi-Agent 设计规范

> 日期：2026-08-03  
> 状态：待用户审查  
> 范围：用 Supervisor + Order/Constraint/Resource **替换排产（scheduling）主路径**；规则产出结构 + LLM 可选摘要；复用 S1 strategy pipeline  
> 前置：[`2026-08-03-parameterized-scheduling-strategy-design.md`](2026-08-03-parameterized-scheduling-strategy-design.md)（S1 已闭环）  
> 依据：实现文档 Multi-Agent 章节 + 2026-08-03 头脑风暴确认  

---

## 1. 执行摘要

在 S1（参数化策略 + 评价闭环 + HITL）之上，引入 **Planning Supervisor** 编排三个**分析型** Agent：

```text
Order + Constraint + Resource（可并行，规则为主）
        → 可选 LLM reasoning_summary（失败跳过）
        → 汇总 PlanningTaskState.artifacts
        → S1 generate_strategy → S1 pipeline（HITL / Solver / Evaluator）
```

**本轮目标：** 替换旧 **scheduling** 主责路径（含 Orchestrator 对 scheduling 意图的路由、旧 `SchedulingAgentRunner` 主流程）。  
**本轮不替换：** events / kitting / commitment / whatif / plans —— 记入同构迁移 backlog，**明确不做永久双轨**。

**不做：** 把 Strategy/Solver/Evaluation 再拆成独立 LLM Agent（仍用 S1 模块）；不上 LangGraph；Agent 之间禁止直接互调。

---

## 2. 已确认决策

| 决策项 | 结论 |
|---|---|
| S2 范围 | 最小协作：Supervisor + 三分析 → S1 |
| 分析实现 | 规则产出结构化 artifacts；LLM 只写 `reasoning_summary` |
| LLM 摘要失败 | 跳过摘要，不阻塞流水线 |
| 集成方式 | 新建 `planning.collab`；路由切换替换 scheduling |
| 旧 scheduling | 验收后删除，不永久并行 |
| 其余五 Agent | Backlog：按同一架构依次替换 |
| 落法 | A：collab 模块 + 路由切换（非塞进旧 scheduling.py，非先造完整 Runtime） |

---

## 3. 架构

```text
用户 / APS / Orchestrator（intent=scheduling）
              │
              ▼
     Planning Supervisor（metaforge.planning_collab）
              │
     AgentTask ×3（依赖空，可并行）
     ┌────────┼────────┐
     ▼        ▼        ▼
  Order    Constraint  Resource
  （规则）   （规则）    （规则）
     │        │         │
     └─ LLM 摘要（可选，失败→空）─┘
              ▼
     PlanningTaskState.artifacts
              ▼
     S1：generate_strategy（消费分析 artifacts）
              ▼
     S1：pipeline（HITL → problem_resolve → SolverPolicy
                  → Solvers → Evaluator → Package）
```

### 3.1 边界

| 单元 | 职责 | 非职责 |
|---|---|---|
| Supervisor | 建 State、调度 Task、汇总、调用 S1、Trace | 算甘特、选具体工序时间 |
| Order Agent | 关键/临期/延期、priority_adjustments | 写硬约束全集 |
| Constraint Agent | 提出 hard/soft 候选（类型 ∈ S1 catalog） | 运行 Solver |
| Resource Agent | 瓶颈/负载/替代产能粗估 | 改设备日历真源 |
| S1 strategy.* | 策略生成、HITL、求解、评价 | 订单池业务分析 |

### 3.2 与现有六 Agent 关系

- **scheduling**：本轮被 collab 路径**替换**。  
- **events / kitting / commitment / whatif / plans**：本轮**保留**；规格 §10 记录迁移顺序与同构要求。

---

## 4. 通信协议

Agent **不得** `other_agent.call(...)`。统一：

### 4.1 AgentTask

```text
task_id: str
agent_id: order | constraint | resource
objective: str
inputs: dict          # jobs, user_goal, factory_state 子集
dependencies: list[str]  # S2 三分析默认 []
```

### 4.2 AgentResult

```text
agent_id: str
status: success | failed | skipped
summary: str                 # 短规则摘要
artifacts: dict              # 结构化产出（唯一下游输入）
warnings: list[str]
reasoning_summary: str | None  # 仅 LLM；可空
```

### 4.3 PlanningTaskState

```text
task_id / run_id
user_goal
production_input: { jobs, machines, ... }
artifacts: {
  order_analysis,
  constraint_analysis,
  resource_analysis,
  strategy,              # S1
  solver_policy,         # S1
  candidate_schedules,   # S1
  evaluation             # S1
}
completed_agents: list
pending_agents: list
current_stage: analyze | strategy | hitl | solve | evaluate | done
warnings: list
```

优先挂到现有 Session / run_state / artifacts，不新建独立 Memory 系统。

---

## 5. 三分析 Agent 产出契约

### 5.1 Order → `order_analysis`

```json
{
  "critical_orders": ["A"],
  "due_risk_orders": ["B"],
  "overdue_orders": [],
  "priority_adjustments": {"A": 10},
  "reasoning_summary": null
}
```

规则示例：按 `due_date` 临近窗口、`priority`/`customer`、用户目标中的「保证X按期」关键词。

### 5.2 Constraint → `constraint_analysis`

```json
{
  "hard_constraints": [{"type": "order_on_time", "job_id": "A"}],
  "soft_constraints": [{"type": "reduce_changeover"}],
  "reasoning_summary": null
}
```

类型必须 ∈ S1 `HARD_CONSTRAINT_TYPES` / `SOFT_CONSTRAINT_TYPES`；非法类型丢弃并 warning。

### 5.3 Resource → `resource_analysis`

```json
{
  "bottleneck_machines": ["0"],
  "high_load_machines": {"0": 0.9},
  "alternative_capacity": {"1": 0.4},
  "reasoning_summary": null
}
```

规则：基于工序 machine 占用粗估；无日历时允许启发式，标记 warning。

### 5.4 喂给 S1 Generator

Context Builder / `generate_strategy` 增加可选参数：`order_analysis` / `constraint_analysis` / `resource_analysis`。  
合并规则：分析中的 `critical_orders` / hard/soft **优先并入**策略草稿，再经 S1 guardrails 校验。

---

## 6. Supervisor 流程

1. 创建 `PlanningTaskState`  
2. 并发（或线程池/asyncio，实现可选串行等价）执行三 `AgentTask`  
3. 写入 artifacts；对成功者可选调用 `summarize_agent_result`（LLM）；失败则 `reasoning_summary=null`  
4. 单 Agent `status=failed`：默认**降级继续**（缺该 artifacts + warning）；`COLLAB_FAIL_CLOSED=1` 时整单失败  
5. 调用 S1 `generate_strategy`（可 `skip` 后直接 HITL/run，与现网 Flag 对齐）  
6. 调用 S1 `run_planning` / 或已有 approved 策略则 `resume`  
7. Trace：Supervisor 阶段 + 各 AgentResult 摘要 + S1 strategy_trace  

---

## 7. API 与路由替换

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/planning/collab/run` | 一键：分析 →（可选 HITL）→ S1 求解包装 |
| POST | `/api/planning/collab/analyze` | 仅三分析，返回 artifacts |
| GET | `/api/planning/collab/runs/{id}` | 查询 TaskState |

**路由切换：**

- Orchestrator：`intent=scheduling` → collab（`PLANNING_COLLAB_V1` 默认 `1`）  
- APS「智能排产」：改调 collab（或 collab 内部再调 S1）  
- Flag=`0`：短暂回退旧 scheduling（仅迁移窗口）  

**删除门槛（scheduling）：**

1. collab e2e 与路由测试通过  
2. APS / 助手默认入口已切  
3. 文档与 registry 更新  
4. 然后删除：`agents/scheduling.py` 主责实现、过时 pipeline 转发、遗留 `/api/agent/schedule`（若无其他依赖）  

共享 Tool（`scheduling.run` 等）可保留供 collab/S1 调用，或改为 `planning.*` 包装——以「无死引用」为准。

---

## 8. 错误处理

| 情况 | 行为 |
|---|---|
| 规则分析异常 | 该 Agent failed；默认降级 |
| LLM 摘要超时/非法 | 跳过摘要 |
| S1 guardrails 失败 | 沿用 S1（不进入求解） |
| S1 无 problem | 沿用 S1 `problem_resolve` |
| 全分析失败且 fail-closed | collab run FAILED |

---

## 9. 测试要求

1. Order/Constraint/Resource 规则快照（固定 jobs + goal）  
2. Supervisor 汇总后三 artifacts 键齐全  
3. Mock LLM 摘要失败 → 仍可进入 S1 且有 recommended（skip HITL）  
4. Orchestrator/路由：scheduling 意图命中 collab  
5. e2e：collab → skip HITL → `built_from_jobs` + recommended  
6. Flag 关闭时回退行为（若实现回退）  

---

## 10. 同构迁移 Backlog（S2 不实现）

按同一模式（Supervisor 或领域编排 + AgentTask/Result + 规则/Tool 确定性核心）依次替换，**替换完成即删旧路径**：

| 顺序 | 领域 | 备注 |
|---|---|---|
| 1 | events | 异常重排 R0/R1/R2 |
| 2 | kitting | 齐套 |
| 3 | commitment | 交期承诺 |
| 4 | whatif | 方案对比 |
| 5 | plans | 计划管理 |

每领域单独规格 + 计划；禁止「新旧 Agent 永久并行」。

---

## 11. 文件级计划（实现阶段）

**新建**

```text
src/metaforge/planning_collab/__init__.py
src/metaforge/planning_collab/protocol.py      # AgentTask/Result/State
src/metaforge/planning_collab/supervisor.py
src/metaforge/planning_collab/agents/order.py
src/metaforge/planning_collab/agents/constraint.py
src/metaforge/planning_collab/agents/resource.py
src/metaforge/planning_collab/summarize.py      # LLM 摘要，失败返回 None
tests/planning_collab/test_*.py
```

**修改**

```text
src/metaforge/strategy/context_builder.py / generator.py  # 消费分析 artifacts
tests/main.py                                            # collab API
orchestrator/router 或 scheduling 路由入口                 # 切到 collab
docs/多智能体开发进度.md / README.md                      # 进度与 backlog
agents/registry_meta.py                                  # scheduling 指向 collab 或标记 replaced
```

**删除（验收后）**

```text
旧 scheduling 主责 Runner 路径、无引用的遗留 NL 排程入口
```

---

## 12. 验收标准

1. scheduling 意图默认走 collab，不再依赖旧 SchedulingAgentRunner 主流程。  
2. 三分析规则 artifacts 稳定可测；摘要可空。  
3. 分析输出能改善/约束 S1 策略（至少 critical_orders / hard 约束进入 guardrails）。  
4. 端到端可产出合法 Package（复用 S1）。  
5. 文档列出五 Agent 迁移 backlog。  
6. 旧 scheduling 主路径按门槛删除或已提交删除 PR。  

---

## 13. 规格自检

| 项 | 结果 |
|---|---|
| 占位符 | 无 TODO 实现洞；backlog 为明确后续子项目 |
| 一致性 | 与 S1 复用、替换 scheduling、摘要可跳过全文一致 |
| 范围 | 单规格可覆盖一个实现计划；七 Agent 全量与五领域替换已外提 |
| 模糊性 | 降级默认、Flag 默认开、删除门槛已写明 |

---

## 14. 参考

- S1 规格与计划：`docs/superpowers/specs/2026-08-03-parameterized-scheduling-strategy-design.md`  
- 实现愿景：`MetaForge_Intelligent_Scheduling_MultiAgent_Implementation.md` §5–7  
- 现行 Agent 基类：`src/metaforge/agents/base.py`  
