# MetaForge Agentic Manufacturing 全面升级实施方案
> 用途：可直接提供给 Codex / Claude Code / Cursor / 其他 Coding Agent 作为代码改造总规范。  
> 项目定位：从“Multi-Agent 制造排程智能助手”升级为“Agentic Manufacturing / Intelligent Production Decision System（智能生产决策系统）”。  
> 原则：**不为了追新框架而重构，不为了增加 Agent 数量而增加 Agent；优先增强真实制造业务闭环、动态生产状态、跨域决策能力、可恢复执行与评测体系。**

---

## 0. 给 Coding Agent 的执行说明

你正在修改一个已有工程，不是新建 Demo。

开始任何代码修改前必须：

1. 阅读当前仓库结构、README、现有 `docs/`、测试目录以及本文件。
2. 以**当前代码为唯一事实来源**，本文件中的目录名若与仓库实际不一致，以仓库为准。
3. 不允许为了实现新功能破坏现有：
   - 14 个 Solver 注册机制；
   - 6 个现有业务 Agent；
   - 30 个 Tool 白名单体系；
   - `POST /api/orchestrator/run`；
   - `POST /api/orchestrator/stream`；
   - `POST /api/orchestrator/preview`；
   - SSE 流式输出；
   - Session / artifacts / pending state；
   - HITL 落库确认；
   - R0 / R1 / R2 异常重排；
   - REST 看板与 Agent 共用业务内核；
   - 现有 pytest；
   - MongoDB 兼容能力。
4. 优先采用**增量重构**，避免“一次性替换架构”。
5. 每个阶段都必须：
   - 先补测试；
   - 再实现代码；
   - 再跑回归；
   - 最后更新文档。
6. 不允许把排程、甘特计算、交期计算等确定性业务逻辑迁移给 LLM。
7. LLM 只负责：
   - 理解自然语言；
   - 识别意图；
   - 拆解任务；
   - 选择能力；
   - 解释结果；
   - 生成建议；
   - 在受控范围内进行跨域协调。
8. 所有真实业务状态必须来自业务状态层，不得把 Agent Memory 当作真实生产事实。
9. 若一个业务动作可以用确定性 Workflow / Tool 完成，不要强行包装为 Agent。
10. 不要求当前阶段引入 LangGraph。只有在自研运行时无法可靠支持持久化、暂停恢复、复杂长任务时再评估。

---

# 1. 当前系统事实基线

当前系统是一个：

> **制造 APS + Multi-Agent 排程调度平台**

主要技术栈：

- Python
- FastAPI
- Uvicorn
- MongoDB / Motor
- Vue3
- Vite
- Element Plus
- ECharts
- 智谱 GLM（OpenAI Compatible Chat Completions）
- 自研 `LlmNode`
- 自研 Orchestrator
- Plan-and-Solve
- 白名单 Tool Calling
- ReAct / Reflect 可选节点
- JSON 结构化解析
- SSE
- Pydantic
- pytest

当前没有强依赖：

- LangGraph
- LangChain
- AutoGen
- CrewAI

这一点**暂时保留**。

---

# 2. 当前 Agent 架构

当前主要链路：

```text
User
  ↓
Orchestrator
  ↓
Guard / Pending Route Hint
  ↓
GLM Router / Rule Fallback
  ↓
Single Agent Routing
  ↓
Plan
  ↓
Parse
  ↓
Allowed Tools
  ↓
Deterministic Domain Logic
  ↓
Summarize
  ↓
SSE / UI
```

当前已有 6 个专责 Agent：

1. Scheduling Agent
2. Events Agent
3. Kitting Agent
4. Commitment Agent
5. What-if Agent
6. Plans Agent

当前一个请求只路由到一个 Agent。

因此现有结构的本质更接近：

> Router + Domain Agent / Mixture-of-Experts Agent

而不是强协作型 Multi-Agent。

这不是错误，但限制了跨域制造决策场景。

---

# 3. 当前已有核心能力

## 3.1 Agent / LLM 层

已有：

- Router
- Rule fallback
- Router Guard
- `LlmNode`
- Plan-and-Solve
- ReAct
- Reflect
- Summarize
- JSON Structured Output
- Prompt 节点链
- SSE execution trace

---

## 3.2 Tool 层

当前约 30 个 Tool，按业务域注册。

现有主要域：

```text
scheduling.*
data.*
execution.*
events.*
delivery.*
material.*
kitting.*
compare.*
memory.*
```

必须继续保持：

```text
Agent
  ↓
Allowed Tools
  ↓
Domain Service
```

禁止：

```text
Agent
  ↓
直接修改 Mongo
```

---

## 3.3 APS / 排程层

当前已有：

- 6 种策略模板；
- 14 种 Solver；
- 多目标评分；
- due date；
- energy cost；
- machine balance；
- makespan；
- weighted tardiness；
- 工艺路线；
- 候选机台；
- 停机窗口；
- BOM / 物料；
- 插单；
- 故障；
- 改交期；
- 异常重排；
- R0 / R1 / R2；
- 异步排程；
- 甘特；
- 多算法对比；
- 计划库。

---

## 3.4 当前记忆 / 状态能力

现有：

```text
Session
Artifacts
Context
Working Memory
Scheduling Memory
Episodic Memory
Pending Clarification
Insert Job Intake
Pending Route Hint
Cached Plan Steps
HITL Pending Confirm
```

这些能力继续保留。

---

# 4. 当前真实问题

## 4.1 Agent 层比业务决策层更完整

目前：

- Agent 数量多；
- Tool 数量多；
- Prompt 节点多；
- Router / Guard 比较完整；

但真实生产环境中的：

- 设备状态；
- 质量状态；
- WIP；
- 人员；
- 实际执行偏差；
- 动态资源能力；
- 维修影响；
- 生产事件流；

还不够完整。

因此下一步不应优先继续增加 Agent 框架，而应增强：

> **Production Decision Intelligence**

---

## 4.2 现有 Multi-Agent 缺乏真实跨 Agent 协同

当前：

```text
Request
  ↓
Only One Agent
```

复杂场景例如：

> M03 故障 4 小时，同时 A 是重要客户急单，B 物料下午才到，夜班少 2 人。

不应该只由 Events Agent 完成。

真正应该：

```text
Production Supervisor
      ↓
 ┌────┼─────────────┐
 ↓    ↓             ↓
Asset Material Scheduling
 ↓    ↓             ↓
 └────┼─────────────┘
      ↓
 Delivery
      ↓
 Scenario Compare
      ↓
 Recommendation
      ↓
 HITL
```

---

## 4.3 部分 Agent 职责不值得独立为 Agent

以下功能更适合 Tool / Workflow：

### Plans Agent

创建、删除、重命名、复制计划属于确定性 CRUD。

建议逐步变成：

```text
Plan Management Tools
```

而不是核心 Agent。

### What-if Agent

建议逐步转化为：

```text
Scheduling Agent Mode = WHAT_IF
```

What-if 是一种决策模式，而不是必须独立的人格化 Agent。

---

## 4.4 Router Guard 增加说明 Agent 边界有重叠

当前已有多组 Guard：

- 计划库；
- 缺料齐套；
- 改交期重排；
- 工单延期；
- 插单续聊。

如果继续增加 Agent，Guard 会越来越多。

后续应该逐步从：

```text
Intent → Agent
```

升级为：

```text
Intent
  ↓
Task Decomposition
  ↓
Capability Selection
```

---

## 4.5 14 个 Solver 数量已经够多

当前不建议继续增加 Solver。

优先解决：

- 真实约束；
- Solver 策略一致性；
- 多目标优化；
- 生产可执行性；
- Solver 选择逻辑。

尤其当前部分 RL Solver 对多目标权重响应不足。

后续应该把 Solver 划分：

```text
Rule-based
Metaheuristic
Exact / Constraint Programming
Experimental RL
```

RL 先保留为实验路线，不承担默认生产排程。

---

## 4.6 Agent Memory 与生产事实需要彻底分离

Agent Memory：

```text
user preference
conversation
pending task
episodic history
```

不能代替：

```text
machine state
inventory
WIP
current operation
quality hold
maintenance status
actual progress
```

后续必须新增：

> **Factory World State / Production State**

---

# 5. 最终目标架构

目标架构分为五层。

---

## 5.1 第一层：Experience / UI

```text
Vue3 UI
│
├─ APS Center
├─ Production Control Tower
├─ Agent Assistant
├─ Scenario Compare
├─ Execution Monitor
├─ Quality Impact
├─ Asset Health
└─ Delivery Promise
```

---

## 5.2 第二层：Agent Harness

```text
Agent Harness
│
├─ Context Builder
├─ Task Planner
├─ Capability Router
├─ Tool Registry
├─ Policy / Permission
├─ State Manager
├─ Memory Manager
├─ Verification
├─ Retry / Recovery
├─ Checkpoint
├─ HITL
└─ Trace / Evaluation
```

Agent Harness 不绑定具体框架。

---

## 5.3 第三层：Domain Agents

目标 Agent：

```text
Production Supervisor Agent
│
├─ Scheduling Agent
├─ Material Agent
├─ Asset Agent
├─ Quality Agent
├─ Delivery Agent
└─ Workforce Capability
```

注意：

`Workforce` 第一阶段可以不是 LLM Agent，而只是 Resource / Constraint Service。

---

## 5.4 第四层：Deterministic Domain Engine

所有关键业务逻辑必须位于该层。

```text
Scheduling Engine
Constraint Engine
Event Engine
Simulation Engine
Material Engine
Delivery Engine
Asset / Maintenance Engine
Quality Rule Engine
Workforce Constraint Engine
Scenario Engine
```

---

## 5.5 第五层：Factory World State

新增统一生产事实状态：

```text
FactoryState
│
├─ current_time
├─ active_schedule_version
├─ machine_states
├─ active_operations
├─ work_in_process
├─ inventory_state
├─ material_arrivals
├─ workforce_state
├─ maintenance_state
├─ quality_state
├─ active_events
└─ execution_deviations
```

---

# 6. Agent 重构方案

## 6.1 新增 Production Supervisor Agent

职责：

> 负责复杂生产问题的跨域拆解与协调。

它不直接做排程。

它负责：

1. 识别复杂生产事件；
2. 判断需要哪些领域能力；
3. 生成子任务；
4. 调用领域 Agent / Tool；
5. 汇聚结果；
6. 请求 Scenario Engine 生成多个方案；
7. 输出推荐；
8. HITL；
9. 提交执行。

示例：

```text
设备故障
+ 缺料
+ 交期风险

Production Supervisor
       ↓
Asset Impact
       ↓
Material Availability
       ↓
Scheduling Scenarios
       ↓
Delivery Impact
       ↓
Recommendation
```

---

## 6.2 Scheduling Agent

负责：

- 正常排程；
- 动态重排；
- What-if；
- 局部修复；
- 全局重排；
- 约束解释；
- Solver 策略选择；
- Scenario Generation。

What-if 不再必须独立 Agent。

---

## 6.3 Material Agent

负责：

- BOM 展开；
- 静态齐套；
- 动态齐套；
- material pegging；
- 到料预测；
- 缺料影响；
- 替代料建议；
- 对订单影响。

---

## 6.4 Asset Agent

新增。

职责：

- 设备状态；
- 故障；
- 健康度；
- 维护窗口；
- 设备可用性；
- 替代设备；
- 预测性维护；
- 维修影响排程。

---

## 6.5 Quality Agent

新增。

职责：

- quality hold；
- 返工；
- 报废；
- 缺陷率异常；
- 工艺风险；
- 受影响批次；
- 质量事件导致的排程约束变更。

---

## 6.6 Delivery Agent

由现有 Commitment 能力升级。

负责：

- CTP；
- ETA；
- 延期风险；
- 客户承诺；
- 延期传播；
- 订单优先级影响；
- 变更前后承诺对比。

---

## 6.7 Plans Agent

逐步降级。

最终目标：

```text
Plan CRUD → Tools
```

保留自然语言入口即可，不需要独立 Agent。

---

# 7. Factory World State 设计

新增模块建议：

```text
src/metaforge/state/
├─ models.py
├─ store.py
├─ snapshot.py
├─ reducer.py
├─ versioning.py
└─ service.py
```

若仓库已有更合适目录，以现有结构为准。

---

## 7.1 FactoryState 核心模型

建议：

```python
class FactoryState:
    current_time
    active_schedule_version
    machine_states
    active_operations
    work_in_process
    inventory_state
    material_arrivals
    workforce_state
    maintenance_state
    quality_state
    active_events
    execution_deviations
```

---

## 7.2 MachineState

```python
machine_id
status
current_job
current_operation
available_from
health_score
failure_risk
maintenance_due
capabilities
calendar
```

status 建议：

```text
idle
running
down
maintenance
blocked
offline
```

---

## 7.3 OperationExecutionState

```python
operation_id
job_id
machine_id
planned_start
planned_end
actual_start
actual_end
progress
status
```

status：

```text
waiting
ready
running
completed
blocked
hold
cancelled
```

---

## 7.4 QualityState

```python
batch_id
job_id
operation_id
quality_status
defect_rate
hold_reason
rework_required
scrap_quantity
risk_level
```

---

## 7.5 WorkforceState

```python
worker_id
shift
skills
certifications
available
assigned_machine
```

---

# 8. 事件驱动生产闭环

当前事件更多是：

```text
User → Event
```

目标升级：

```text
MES / Simulation / User / Sensor
        ↓
Event Source
        ↓
Event Normalizer
        ↓
Impact Detector
        ↓
Decision Trigger
        ↓
Agent / Workflow
```

---

## 8.1 Event Envelope

统一事件模型：

```python
EventEnvelope:
    event_id
    event_type
    source
    timestamp
    entity_type
    entity_id
    severity
    payload
    detected_by
    confidence
    requires_decision
```

source：

```text
user
mes
simulation
sensor
qms
wms
system
```

---

## 8.2 建议扩展事件类型

现有 8 类继续保留。

新增：

```text
operation_delay
operation_early_finish
machine_health_risk
quality_hold
quality_release
rework_required
scrap_detected
worker_absence
skill_shortage
material_arrival_update
inventory_shortage
capacity_overload
schedule_deviation
```

---

# 9. Actual vs Plan 偏差检测

新增核心能力：

> 计划—执行—偏差—重排闭环。

---

## 9.1 Deviation Detector

新增：

```text
Execution State
     +
Baseline Schedule
     ↓
Deviation Detector
```

识别：

- 开工延迟；
- 完工延迟；
- 提前完工；
- WIP 堵塞；
- 设备异常；
- 订单风险；
- Bottleneck shift。

---

## 9.2 建议输出

```python
Deviation:
    deviation_id
    type
    entity
    planned_value
    actual_value
    delta
    severity
    downstream_jobs
    estimated_delivery_impact
```

---

## 9.3 自动决策规则

```text
minor deviation
    ↓
monitor only

medium deviation
    ↓
local repair

critical deviation
    ↓
scenario generation
    ↓
HITL
```

规则必须配置化。

---

# 10. Schedule Explainability

新增：

> 为什么延期？为什么系统推荐这个方案？

---

## 10.1 Delay Attribution

示例：

```text
Order-A 延期 6.2h

M03 故障           +3.0h
M06 排队           +1.4h
Material-X 晚到    +1.2h
Setup              +0.6h
```

---

## 10.2 数据模型

```python
DelayCause:
    cause_type
    entity_id
    contribution
    evidence
    upstream_event_id
```

---

## 10.3 Tool

新增：

```text
schedule.explain_delay
schedule.trace_constraint
schedule.explain_change
```

---

# 11. CTP 智能接单

CTP = Capable-to-Promise。

这是后续最高优先级业务功能之一。

---

## 11.1 目标

用户输入：

> 客户希望 8 月 15 日交付 500 件 Product-A，可以承诺吗？

系统需要综合：

- BOM；
- Routing；
- 当前库存；
- 预计到料；
- 设备容量；
- 现有排程；
- 优先级；
- 交期影响；
- 产能；
- 停机；
- 人员资源。

---

## 11.2 流程

```text
New Order Request
      ↓
Expand BOM / Routing
      ↓
Material Check
      ↓
Capacity Check
      ↓
Virtual Scheduling
      ↓
Impact Existing Orders
      ↓
Delivery Risk
      ↓
Scenario Compare
      ↓
Promise Recommendation
```

---

## 11.3 Tool

建议：

```text
delivery.ctp_check
delivery.earliest_commit_date
delivery.promise_risk
delivery.promise_scenarios
```

---

## 11.4 返回格式

```json
{
  "requested_due_date": "...",
  "earliest_commit_date": "...",
  "feasible": true,
  "risk_level": "low",
  "bottlenecks": [],
  "material_risks": [],
  "affected_orders": [],
  "recommended_promise_date": "...",
  "alternatives": []
}
```

---

# 12. Material Pegging

当前物料齐套继续升级。

不要只回答：

> 缺不缺料。

需要回答：

> 哪个订单需要什么料，这个料分配给了谁，缺料会影响谁。

---

## 12.1 Pegging 数据模型

```python
MaterialPeg:
    material_id
    source
    quantity
    allocated_job
    allocated_operation
    required_time
    available_time
    shortage
```

---

## 12.2 Tool

```text
material.pegging
material.trace_shortage
material.find_affected_orders
material.find_substitutes
```

---

# 13. Maintenance-aware Scheduling

这是推荐的高价值场景。

---

## 13.1 模拟设备遥测

第一阶段不接真实 PLC。

新增模拟：

```text
machine_id
timestamp
temperature
vibration
current
load
health_score
```

---

## 13.2 健康模型

可以先使用：

```text
规则
+
简单异常检测
```

无需立刻上深度学习。

输出：

```python
MachineHealth:
    machine_id
    health_score
    anomaly_score
    failure_risk
    recommended_maintenance_window
```

---

## 13.3 决策场景

```text
M03 failure_risk = 0.78
      ↓
Asset Agent
      ↓
Scenario A:
现在维护 2h

Scenario B:
继续运行
风险未来停机 6h
      ↓
Scheduling Simulation
      ↓
Delivery Impact
      ↓
Recommendation
```

---

# 14. Quality-aware Scheduling

新增质量事件驱动生产调整。

---

## 14.1 第一阶段事件

```text
quality_hold
quality_release
rework_required
scrap_detected
defect_rate_alert
```

---

## 14.2 典型流程

```text
QMS Event
   ↓
Quality Agent
   ↓
Affected Batch / Product
   ↓
Constraint Update
   ↓
Scheduling Agent
   ↓
Reschedule
   ↓
Delivery Impact
```

---

## 14.3 Tool

```text
quality.get_status
quality.hold_batch
quality.release_batch
quality.assess_impact
quality.create_rework_route
```

高风险写操作必须 HITL。

---

# 15. Workforce Constraint

第一阶段不需要独立 Agent。

直接作为 Resource Constraint。

新增：

- shift；
- skill；
- certification；
- availability。

示例：

```text
Operation A
requires:
  skill = welding
  certification = CERT-01
```

排程必须：

```text
machine available
AND
qualified worker available
```

---

# 16. 真实 APS 约束增强

优先加入：

## P0

- Sequence-dependent setup
- Alternative machine
- Machine calendar
- Planned downtime
- Material availability
- Worker availability
- Tooling requirement

## P1

- Secondary resources
- Operation overlap
- Transport time
- Buffer / WIP capacity
- Batch / lot constraints

## P2

- AGV / logistics
- Carbon constraint
- stochastic duration
- robust scheduling

---

# 17. Solver 层改造

不再继续增加 Solver 数量。

新增：

```text
SolverPolicy
```

负责：

> 根据问题规模、约束、实时性要求选择 Solver。

---

## 17.1 Solver 分类

```text
Rule Heuristic
Metaheuristic
Constraint / Exact
Experimental RL
```

建议未来补一个：

```text
CP-SAT / OR-Tools
```

作为约束密集场景基线。

---

## 17.2 SolverPolicy 输入

```python
problem_size
constraint_complexity
required_latency
optimization_goal
event_type
need_optimality
```

---

## 17.3 SolverPolicy 输出

```python
primary_solver
fallback_solver
time_budget
stop_condition
```

---

# 18. Scenario Engine

这是未来 Agentic Decision 的核心。

新增：

```text
src/metaforge/scenario/
```

职责：

1. Clone FactoryState；
2. Apply hypothetical change；
3. Run scheduling；
4. Calculate KPI；
5. Compare scenario；
6. Return ranked alternatives。

---

## 18.1 Scenario 数据模型

```python
Scenario:
    scenario_id
    name
    assumptions
    state_snapshot
    actions
    schedule
    kpis
    risks
```

---

## 18.2 KPI

至少：

```text
makespan
weighted_tardiness
affected_orders
energy_cost
machine_busy_cv
schedule_changes
setup_time
worker_overtime
delivery_risk
```

---

## 18.3 Scenario Comparison

```text
Scenario A
local repair

Scenario B
alternative machine

Scenario C
overtime

        ↓
Compare
        ↓
Recommendation
```

LLM 可以解释排名。

排名本身尽量基于确定性 KPI。

---

# 19. Durable Agent Run

暂不要求 LangGraph。

先补自研运行时缺失能力。

---

## 19.1 AgentRun

新增：

```python
AgentRun:
    run_id
    session_id
    user_request
    status
    current_step
    plan
    tool_calls
    artifacts
    state_snapshot
    checkpoint
    retry_count
    pending_input
    pending_approval
    created_at
    updated_at
```

---

## 19.2 状态机

```text
CREATED
  ↓
PLANNING
  ↓
EXECUTING
  ↓
WAITING_INPUT
  ↓
RESUME

或

WAITING_APPROVAL
  ↓
RESUME

最终：

COMPLETED
FAILED
CANCELLED
```

---

## 19.3 要求

支持：

- crash recovery；
- retry；
- resume；
- idempotency；
- step replay；
- execution trace。

---

# 20. Checkpoint

每个关键 Step 后写 checkpoint。

例如：

```text
Route
Plan
Tool 1
Tool 2
Scenario Generate
HITL
Persist
```

Checkpoint 最少保存：

```text
run_id
step_id
state
artifact refs
tool result refs
timestamp
```

---

# 21. Idempotency

高风险 Tool 必须支持幂等。

尤其：

```text
persist
delete
update
reschedule apply
quality hold
maintenance action
```

建议：

```text
idempotency_key
```

避免 Retry 重复执行。

---

# 22. Permission / Policy

当前白名单 Tool 继续保留。

增加 Tool 风险等级：

```text
READ_ONLY
CALCULATE
SIMULATE
WRITE
HIGH_RISK
```

---

## 22.1 Policy

例如：

```text
READ_ONLY
→ automatic

SIMULATE
→ automatic

WRITE
→ HITL optional

HIGH_RISK
→ HITL required
```

---

# 23. HITL 升级

当前落库确认继续扩展。

需要支持：

```text
approve
reject
edit_and_approve
```

HITL 对象：

```python
ApprovalRequest:
    approval_id
    run_id
    action
    summary
    impact
    risk
    payload
    expires_at
```

---

# 24. Context Engineering

新增统一 Context Builder。

不要每个 Agent 自己拼 Prompt。

---

## 24.1 Context 组成

```text
System Policy
User Request
FactoryState Summary
Relevant Plan
Relevant Events
Task State
Tool Results
Agent Memory
Business Constraints
```

---

## 24.2 Context Budget

必须限制：

- 完整甘特；
- 大 BOM；
- 大库存；
- 全量 MachineState；

进入 LLM。

先结构化压缩。

---

## 24.3 Factory Context Summary

新增：

```text
context.build_factory_summary
```

例如：

```text
当前：
- 12 台设备，2 台停机
- 8 个在制订单
- 3 单存在交期风险
- M03 为瓶颈
- MAT-102 缺料
```

---

# 25. Memory 重新定义

保留当前：

```text
working
scheduling
episodic
```

但重新明确：

## Agent Memory

可以存：

- 用户偏好；
- 最近策略；
- 最近任务；
- 历史情景。

## Factory State

必须单独存：

- 机器状态；
- 库存；
- 工单；
- 实际执行；
- 质量；
- 维护。

Factory State 优先级永远高于 Agent Memory。

---

# 26. Evaluation 升级

当前 L2 / L3 回归继续保留。

新增四类 Eval。

---

## 26.1 Routing Eval

```text
intent
expected capability
actual capability
```

---

## 26.2 Planning Eval

检查：

```text
Tool 是否合理
是否越权
步骤是否多余
是否遗漏关键域
```

---

## 26.3 Execution Eval

```text
tool success rate
retry rate
fallback rate
run completion rate
```

---

## 26.4 Business Eval

这是以后最重要的。

例如：

### 故障场景

```text
是否识别 affected jobs
是否产生至少 2 个 scenario
是否正确计算延期
是否需要 HITL
```

### CTP

```text
是否考虑 capacity
是否考虑 material
是否影响已有订单
promise date 是否可执行
```

---

# 27. Observability

Agent 执行记录：

```text
run_id
agent
capability
model
prompt_version
tool_calls
latency
token_usage
retry
fallback
status
```

业务执行记录：

```text
schedule_version
solver
event
state_before
state_after
kpi_before
kpi_after
```

---

# 28. 前端：Production Control Tower

新增页面：

```text
Production Control Tower
```

布局建议：

## 顶部

- 当前计划版本；
- 生产时间；
- Active Orders；
- Delay Risk；
- Machine Availability；
- Active Events。

## 中间

- 当前甘特；
- Actual vs Plan；
- 关键异常；
- Bottleneck。

## 右侧

- Agent Recommendation；
- Scenario A/B/C；
- HITL。

## 底部

- Event Timeline；
- Decision Log。

---

# 29. Flagship Case 1：设备故障智能处置

这是必须优先完成的完整场景。

---

## 输入

```text
M03 发生故障，预计停机 180 分钟。
```

或者由模拟 Event Stream 自动产生。

---

## 流程

```text
Machine Breakdown
       ↓
FactoryState Update
       ↓
Supervisor
       ↓
Asset Agent
       ↓
Affected Operations
       ↓
Material Check
       ↓
Scheduling Scenarios
       ↓
Delivery Assessment
       ↓
Scenario Compare
       ↓
Recommendation
       ↓
HITL
       ↓
Apply New Schedule
```

---

## 至少三个方案

### A

Local Repair

### B

Alternative Machine

### C

Overtime / Shift Adjustment

---

## 验收

必须返回：

- 影响订单；
- 延期；
- 新甘特；
- KPI；
- 推荐方案；
- 推荐原因；
- 风险；
- HITL。

---

# 30. Flagship Case 2：CTP 智能接单

输入：

```text
客户新增 Product-A 500 件，
希望 8 月 15 日交付。
```

系统：

```text
BOM
↓
Material
↓
Routing
↓
Capacity
↓
Virtual Schedule
↓
Current Order Impact
↓
Promise Date
```

返回：

- feasible；
- earliest date；
- risk；
- bottleneck；
- missing material；
- affected orders；
- alternatives。

---

# 31. Flagship Case 3：预测性维护 + 排程

输入来自模拟遥测。

```text
M03 failure risk = 78%
```

生成：

```text
立即维护
VS
推迟维护
```

两套 Scenario。

输出：

- downtime；
- affected jobs；
- delivery；
- cost；
- failure risk；
- recommendation。

---

# 32. Flagship Case 4：质量异常 + 动态重排

输入：

```text
Batch B001 quality hold
```

流程：

```text
Quality Event
↓
Affected WIP
↓
Hold
↓
Rework / Alternative Routing
↓
Reschedule
↓
Delivery Impact
```

---

# 33. 分阶段实施路线

不要一次性完成全部。

---

# Phase 0：代码审计与事实统一

目标：

> 先修文档 / 代码事实不一致。

任务：

1. 扫描：
   - agents；
   - tools；
   - solver registry；
   - events；
   - memory；
   - orchestrator；
   - state；
   - tests。
2. 自动生成能力清单。
3. 检查：
   - BOM 是否真的进入 Solver；
   - MCP 当前到底做到什么程度；
   - Audit 是否真实可用；
   - RL 权重是否一致。
4. 更新 README / docs。

验收：

```text
docs/current-capabilities.md
```

必须成为单一事实源。

---

# Phase 1：Factory World State

目标：

> 建立统一真实生产状态层。

实现：

- FactoryState；
- MachineState；
- OperationExecutionState；
- InventoryState；
- QualityState；
- WorkforceState；
- Snapshot；
- Version。

先不改 Agent。

验收：

```text
GET /api/factory/state
GET /api/factory/snapshot
```

---

# Phase 2：Execution Deviation

实现：

- Actual vs Plan；
- deviation detector；
- event generation；
- severity；
- downstream impact。

验收：

模拟：

```text
Operation delay 60min
```

系统自动产生：

```text
schedule_deviation
```

---

# Phase 3：Scenario Engine

实现：

- state clone；
- hypothetical action；
- schedule；
- KPI；
- compare。

API：

```text
POST /api/scenarios/run
POST /api/scenarios/compare
```

---

# Phase 4：Schedule Explainability

实现：

```text
delay attribution
constraint trace
schedule change explanation
```

API：

```text
GET /api/schedule/{id}/explain
```

---

# Phase 5：Agent 边界重构

新增：

```text
ProductionSupervisorAgent
AssetAgent
QualityAgent
```

调整：

```text
WhatIfAgent
→ Scheduling Mode

PlansAgent
→ Plan Tools
```

注意：

第一步允许兼容旧 Agent，不要直接删除。

---

# Phase 6：真实 Multi-Agent Case

完成：

> Machine Breakdown Intelligent Response

必须真实跨：

```text
Asset
Scheduling
Delivery
```

Material 可选。

---

# Phase 7：CTP

完成：

```text
delivery.ctp_check
```

增加 Agent 卡片。

---

# Phase 8：Maintenance-aware Scheduling

模拟 telemetry。

增加：

- Health Score；
- Failure Risk；
- Maintenance Window；
- Scenario Compare。

---

# Phase 9：Quality-aware Scheduling

增加：

- Hold；
- Release；
- Rework；
- Quality Impact。

---

# Phase 10：Durable Run

增加：

```text
AgentRun
Checkpoint
Resume
Retry
Idempotency
```

如果实现复杂度明显增加，再评估 LangGraph。

---

# Phase 11：Permission / HITL

完成：

```text
risk level
approval policy
audit
```

---

# Phase 12：Production Control Tower

整合：

```text
Plan
Execution
Deviation
Event
Agent
Scenario
Decision
```

---

# 34. LangGraph 使用原则

当前阶段：

> 不重构到 LangGraph。

满足以下任意情况再评估：

1. 自研 Checkpoint / Resume 维护成本过高；
2. 长任务分支越来越多；
3. WAITING_INPUT / WAITING_APPROVAL 状态复杂；
4. crash recovery 难以维护；
5. 需要 time travel；
6. 需要多个并行子图；
7. 状态转移 bug 明显增加。

届时使用 Adapter：

```text
AgentRuntime
├─ NativeRuntime
└─ LangGraphRuntime
```

不要业务代码直接依赖 LangGraph。

---

# 35. MCP 使用原则

MCP 不是当前第一优先级。

只有需要对接真实：

- MES；
- ERP；
- QMS；
- WMS；
- EAM；
- 文件系统；
- 外部知识库；

再把 Tool Adapter MCP 化。

内部 Python Tool 继续保留。

---

# 36. 不要做的事情

禁止为了“技术栈好看”做：

- 再加 10 个 Agent；
- 再加 10 个 Solver；
- 全面迁 LangGraph；
- 全面迁 AutoGen；
- 全面 MCP 化；
- 把 APS 算法交给 LLM；
- 把 Factory State 塞进聊天 Memory；
- 做完整 MES；
- 做完整 QMS；
- 做完整 EAM；
- 做完整 WMS。

项目始终聚焦：

> Production Decision Intelligence

---

# 37. 推荐最终产品定位

项目名可升级为：

> **Agentic Manufacturing Production Decision System**

中文：

> **制造生产智能决策 Multi-Agent 系统**

或：

> **面向离散制造的 Agentic APS 与生产决策系统**

---

# 38. 最终系统能力图

```text
                        User / MES / QMS / Sensor
                                  │
                                  ▼
                            Event / Request
                                  │
                                  ▼
                       Production Supervisor
                                  │
          ┌───────────────────────┼────────────────────────┐
          ▼                       ▼                        ▼
     Scheduling                Material                  Asset
          │                       │                        │
          └───────────────┬───────┼───────────────┬────────┘
                          ▼                       ▼
                       Quality                 Delivery
                          │                       │
                          └───────────┬───────────┘
                                      ▼
                               Scenario Engine
                                      │
                              ┌───────┼───────┐
                              ▼       ▼       ▼
                              A       B       C
                              │       │       │
                              └───────┼───────┘
                                      ▼
                               Recommendation
                                      │
                                      ▼
                                    HITL
                                      │
                                      ▼
                               Apply Decision
                                      │
                                      ▼
                               Factory State
                                      │
                                      ▼
                            Execution Monitoring
                                      │
                                      └─────→ New Event
```

形成真正闭环：

```text
Observe
   ↓
Detect
   ↓
Understand
   ↓
Simulate
   ↓
Recommend
   ↓
Approve
   ↓
Act
   ↓
Monitor
```

---

# 39. Coding Agent 每阶段输出要求

每完成一个 Phase，需要输出：

## 1. Changed Files

```text
file
purpose
```

## 2. Architecture Change

简述新架构。

## 3. API Change

列出新增 / 修改 API。

## 4. Data Model

列出 Schema。

## 5. Tests

列出：

```text
unit
integration
e2e
```

## 6. Backward Compatibility

说明：

- 是否破坏旧接口；
- 是否影响旧前端；
- 是否影响旧 Agent；
- 是否迁移数据库。

## 7. Known Limitations

禁止隐藏问题。

---

# 40. 测试最低要求

所有新增功能：

```text
pytest
```

至少包含：

- happy path；
- invalid input；
- missing state；
- Tool failure；
- timeout；
- retry；
- duplicate execution；
- HITL reject；
- recovery。

---

# 41. Flagship E2E 测试

必须最终新增：

```text
test_machine_breakdown_decision_flow
test_ctp_decision_flow
test_quality_hold_reschedule
test_maintenance_scenario
test_agent_run_resume
test_event_auto_trigger
```

---

# 42. 最终验收标准

项目完成后必须能真实演示：

## Case A：正常排程

用户：

> 按交付优先重新排今天计划。

系统：

```text
理解
→ Solver
→ 甘特
→ Delivery
```

---

## Case B：复杂故障

系统自动：

```text
Event
→ Impact
→ Multi-Agent
→ Scenario
→ Recommend
→ HITL
→ Apply
```

---

## Case C：新订单

用户：

> 明天来一个新订单，能不能 15 号交？

系统：

```text
CTP
→ Material
→ Capacity
→ Scheduling
→ Delivery
```

---

## Case D：质量异常

```text
Quality Hold
→ Impact
→ Rework
→ Reschedule
```

---

## Case E：设备健康风险

```text
Telemetry
→ Failure Risk
→ Maintenance Scenario
→ Schedule Scenario
```

---

# 43. 最终面试可解释能力

完成上述改造后，项目必须可以回答：

1. 为什么没有直接用 LangGraph？
2. 什么情况下你会切 LangGraph？
3. 为什么 Plans 不值得做 Agent？
4. Multi-Agent 怎么协作？
5. Factory State 和 Memory 有什么区别？
6. Agent 如何知道生产发生变化？
7. 为什么不让 LLM 算甘特？
8. Tool 怎么做权限控制？
9. Tool 失败怎么办？
10. 长任务怎么恢复？
11. 如何避免重复执行？
12. 如何做 HITL？
13. 如何做 CTP？
14. 如何处理设备故障？
15. 如何处理缺料？
16. 如何处理质量 Hold？
17. 如何解释订单延期原因？
18. 多个重排方案怎么比较？
19. 为什么保留 RL 但不让它成为默认 Solver？
20. 项目怎么做评测？
21. 如何证明 Agent 真正带来价值？
22. 如何从“聊天助手”升级成“生产决策系统”？

---

# 44. 最重要的开发原则

任何后续修改都围绕下面一句话判断：

> **这个功能是否让系统更接近真实生产决策，而不是仅仅让 Agent 技术栈看起来更复杂？**

若答案是否定的，优先级降低。

最终目标不是：

```text
更多 Agent
更多 Prompt
更多 Framework
```

而是：

```text
更真实的状态
+
更真实的约束
+
更真实的异常
+
跨域影响分析
+
多方案仿真
+
可靠执行
+
人工可控
+
可评测
```

---

# 45. 推荐 Coding Agent 第一轮执行指令

将下面内容直接作为第一轮任务：

```text
请先不要直接修改业务代码。

阅读当前仓库，并以《MetaForge Agentic Manufacturing 全面升级实施方案.md》为目标文档，对现有系统完成 Phase 0 架构审计。

要求：

1. 扫描 agents、tools、orchestrator、memory、solver_registry、events、execution、Mongo models、API、frontend、tests。
2. 输出当前真实架构。
3. 列出当前实际 Agent 数量与职责。
4. 列出当前实际 Tool 注册表。
5. 列出当前 Solver。
6. 核实 BOM/Material 是否真正进入排程求解过程，而不是仅做排程后分析。
7. 核实 MCP 当前实现程度。
8. 核实 Audit / RBAC 当前实现程度。
9. 核实 RL Solver 是否响应策略 weights。
10. 核实 Session / HITL / pending state / plan cache / SSE 当前实现。
11. 找出文档与代码不一致项。
12. 不要根据旧文档猜实现，只认代码。
13. 新建 docs/current-capabilities.md，作为当前系统单一事实源。
14. 给出 Phase 1 Factory World State 的具体文件级实施计划，但暂时不要实现 Phase 1。
15. 执行现有测试并记录 baseline。

输出：
- 当前架构图
- 能力矩阵
- 差距
- 风险
- 测试 baseline
- Phase 1 文件级改造计划
```

---

# 46. 第二轮 Coding Agent 指令

Phase 0 确认后：

```text
现在执行 Phase 1：Factory World State。

要求：

1. 不破坏现有 production_execution。
2. 将其逐步抽象为统一 FactoryState。
3. 新增 MachineState、OperationExecutionState、InventoryState、MaintenanceState、QualityState、WorkforceState。
4. FactoryState 必须支持 snapshot 和 version。
5. 现有 baseline_gantt / sim_time 必须能够映射进入 FactoryState。
6. 不迁移 Agent Memory。
7. 新增 GET /api/factory/state。
8. 新增 GET /api/factory/snapshot。
9. 新增单测。
10. 保持旧 API 兼容。

完成后：
- 跑完整 pytest
- 更新 docs/current-capabilities.md
- 输出数据库兼容说明
```

---

# 47. 第三轮 Coding Agent 指令

```text
执行 Phase 2：Actual vs Plan Deviation Detection。

目标：
让系统不依赖用户主动告诉 Agent“生产出问题了”，而能够根据执行态自动产生事件。

要求：

1. 对比 baseline schedule 与 actual execution state。
2. 检测 start delay、finish delay、early finish、blocked、machine down。
3. 生成统一 EventEnvelope。
4. 增加 severity。
5. 计算 downstream affected jobs。
6. 对超过阈值的 deviation 自动标记 requires_decision=true。
7. 不允许自动直接落新计划。
8. 新增测试。
9. 提供一个 simulation API 方便演示 execution progress。
```

---

# 48. 第四轮 Coding Agent 指令

```text
执行 Phase 3：Scenario Engine。

必须支持：
- Clone FactoryState
- Apply hypothetical action
- Run scheduling
- Calculate KPIs
- Compare scenarios

优先完成设备故障场景：

A. Local Repair
B. Alternative Machine
C. Global Reschedule

所有 scenario 不得直接覆盖 active FactoryState。

只有 HITL approve 后才能 apply。
```

---

# 49. 后续 Coding Agent 工作顺序

严格按：

```text
Phase 0
↓
Factory State
↓
Deviation
↓
Scenario Engine
↓
Explainability
↓
Agent Boundary Refactor
↓
Machine Breakdown Flagship
↓
CTP
↓
Maintenance
↓
Quality
↓
Durable Run
↓
Policy / HITL
↓
Control Tower
```

不要跳过底层状态模型直接堆 Agent。

---

# 50. 完成状态定义

这个项目真正完成升级，不以：

> “增加了多少 Agent”

为标准。

而以是否完成下面闭环为标准：

```text
生产事实进入系统
        ↓
系统发现偏差
        ↓
判断影响
        ↓
调用多个领域能力
        ↓
生成多个决策方案
        ↓
定量比较
        ↓
给出推荐及解释
        ↓
人工审批
        ↓
执行
        ↓
产生新的生产状态
        ↓
继续监控
```

如果这个闭环成立，项目才真正从：

> Multi-Agent Scheduling Assistant

升级成：

> **Agentic Manufacturing Production Decision System**
