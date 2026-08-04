# MetaForge 智能排产 Multi-Agent 新设计实现文档

> 用途：直接提供给 Codex / Claude Code / Cursor 等 Coding Agent，作为现有 MetaForge 项目的下一阶段重构与实现规范。  
> 核心目标：在保留现有 APS Solver、生产看板仿真、R0/R1/R2 动态重排等能力的基础上，将系统从“固定模板 + 单 Agent 路由式排产”升级为“参数化智能排产 + Multi-Agent 协作决策 + 生产执行仿真 + 动态重调度”。

---

# 1. 改造目标

本轮改造只聚焦三件事：

1. **先把正常生产计划排好**
   - 智能排产是系统主线。
   - Multi-Agent 首先服务于排产前问题分析、策略生成、求解器选择和排产后方案评估。
   - LLM 不直接计算甘特图。

2. **排产策略从固定模板升级为参数化策略**
   - 保留现有策略模板。
   - 新增权重、硬约束、软约束、资源偏好等可配置参数。
   - 支持用户自然语言自动生成策略参数。

3. **保留现有生产执行仿真与动态重排**
   - 没有真实 MES，不伪造 MES 集成。
   - 使用 Production Execution Simulator 倍速执行排程。
   - 动态事件可以人工录入，也可以自动仿真。
   - 保留并强化 R0 / R1 / R2 对比。

---

# 2. 总体产品流程

```text
生产数据配置
      ↓
智能 Multi-Agent 排产
      ↓
推荐生产计划
      ↓
人工确认
      ↓
Production Execution Simulator
      ↓
生产看板倍速执行
      ↓
动态事件 / 执行偏差
      ↓
Multi-Agent 分析与重调度
      ↓
R0 原计划
R1 不干预
R2 智能重排
      ↓
人工选择 / 确认
      ↓
继续仿真执行
```

系统主线必须明确：

```text
先排好计划
    ↓
再执行计划
    ↓
最后处理异常
```

不要把动态异常设计成系统的第一主角。

---

# 3. 智能排产输入设计

智能排产采用：

> **结构化生产数据 + 自然语言生产目标**

双输入模式。

## 3.1 结构化生产数据

### Order / Job

```text
job_id
product_id
quantity
due_date
priority
customer_level
release_time
```

可扩展：

```text
customer_id
order_value
batch
business_priority
```

### Routing / Process

```text
product_id
operations[]
operation_id
sequence
standard_duration
eligible_machines[]
required_skill
required_tool
setup_family
```

### Resource

```text
machines
machine_calendar
planned_downtime
machine_capability
worker_shift
worker_skill
tooling
```

当前没有人员 / 工装真实数据时，可以使用模拟配置。

### Material

```text
BOM
inventory
material_arrival
material_availability
```

如果当前代码已经支持 BOM 约束，则直接复用现有实现。

### Current Production State

正常初始排产允许为空。

滚动重排时可包含：

```text
current_time
WIP
running_operations
completed_operations
frozen_operations
machine_state
```

## 3.2 自然语言生产目标

示例：

```text
给明天订单排一个生产计划，
优先保证客户 A 和客户 B 按期交付，
普通订单允许适当延期，
尽量减少换型，
M03 不要长期满负荷，
暂时不重点考虑能耗。
```

LLM 不直接生成甘特。

LLM 要把这句话转换成结构化 SchedulingStrategy。

---

# 4. 智能排产输出设计

智能排产输出必须是一个完整的：

> **Production Plan Package**

而不是只返回 Agent 文本。

## 4.1 推荐排程

```text
recommended_schedule
gantt
schedule_id
schedule_version
solver
strategy
```

## 4.2 核心 KPI

至少：

```text
makespan
weighted_tardiness_total
late_order_count
energy_cost
machine_busy_cv
setup_changeover_count
```

如果当前没有 setup 指标，可在本轮加入。

## 4.3 重点订单结果

```text
job_id
due_date
estimated_completion
delay
risk
```

## 4.4 瓶颈分析

```text
bottleneck_machine
utilization
queue_time
affected_jobs
```

## 4.5 推荐理由

LLM 根据：

```text
目标
+
约束
+
KPI
+
候选计划差异
```

生成业务解释。

## 4.6 备选方案

建议至少提供：

```text
Recommended
Alternative A
Alternative B
```

不要为了展示强行跑所有 14 Solver。

---

# 5. Multi-Agent 设计

本阶段智能排产使用以下 7 个 Agent。

## 5.1 Planning Supervisor Agent

职责：

```text
理解用户最终排产目标
拆解排产任务
调度其他 Agent
管理 Agent 依赖
汇总 AgentResult
生成最终决策上下文
```

Supervisor 不直接算排程。

## 5.2 Order Agent

职责：

```text
分析订单池
识别关键订单
识别临期订单
识别已延期订单
分析客户优先级
生成订单侧排产要求
```

输入：

```text
jobs
user_goal
```

输出示例：

```json
{
  "critical_orders": ["A12", "A19"],
  "due_risk_orders": ["B03"],
  "priority_adjustments": {
    "A12": 10,
    "A19": 8
  },
  "reasoning_summary": {
    "A12": "重点客户且24小时内到期"
  }
}
```

## 5.3 Constraint Agent

职责：

将生产数据整理为 Solver 可消费的：

```text
Hard Constraints
Soft Constraints
```

Hard Constraints 示例：

```text
工序前后关系
设备可加工能力
物料可用时间
停机窗口
冻结工序
人员技能
工装唯一占用
关键订单必须按期
```

Soft Constraints 示例：

```text
减少换型
负载均衡
降低能耗
减少拖期
减少计划变化
```

## 5.4 Resource Agent

职责：

分析：

```text
设备利用率
瓶颈设备
候选设备
剩余产能
资源冲突
计划停机
资源负载风险
```

输出示例：

```json
{
  "bottleneck_machines": ["M03"],
  "high_load_machines": {
    "M03": 0.92
  },
  "alternative_capacity": {
    "M05": 0.45
  }
}
```

## 5.5 Strategy Agent

职责：

根据：

```text
用户生产目标
+
Order Agent
+
Constraint Agent
+
Resource Agent
```

生成本次真正的排产策略。

这是本轮核心升级。

## 5.6 Solver Agent

职责：

根据排产问题特点决定：

```text
solver
solver parameters
time budget
fallback solver
number of candidate schedules
```

Solver Agent 不运行算法本身。

它调用 APS Solver Tool。

## 5.7 Evaluation Agent

职责：

比较 Solver 返回的候选排程。

不能只按单一 score 排名。

综合：

```text
业务目标
硬约束
交期
makespan
负载
setup
energy
计划稳定性
```

输出：

```text
recommended_schedule_id
ranking
tradeoff_analysis
recommendation_reason
```

---

# 6. Multi-Agent 协作链路

```text
                  Planning Supervisor
                           │
              ┌────────────┼─────────────┐
              ▼            ▼             ▼
         Order Agent  Constraint Agent Resource Agent
              └────────────┼─────────────┘
                           ▼
                     Strategy Agent
                           ▼
                      Solver Agent
                           ▼
                      APS Solvers
                           ▼
                    Candidate Plans
                           ▼
                    Evaluation Agent
                           ▼
                  Planning Supervisor
                           ▼
                   Production Plan
```

第一批：

```text
Order Agent
Constraint Agent
Resource Agent
```

允许并行。

后续：

```text
Strategy
→ Solver
→ Evaluation
```

串行。

---

# 7. Agent 通信协议

Agent 不允许直接硬编码调用其他 Agent。

禁止：

```python
order_agent.call(strategy_agent)
```

统一通过：

```text
TaskState
+
Orchestrator / Supervisor
```

通信。

## 7.1 AgentTask

```python
AgentTask = {
    "task_id": "...",
    "agent_id": "resource",
    "objective": "分析本次排产的设备资源与瓶颈",
    "inputs": {
        "jobs": "...",
        "factory_state": "..."
    },
    "dependencies": []
}
```

## 7.2 AgentResult

```python
AgentResult = {
    "agent_id": "resource",
    "status": "success",
    "summary": "...",
    "artifacts": {},
    "warnings": [],
    "recommended_next_agents": []
}
```

## 7.3 PlanningTaskState

```python
PlanningTaskState = {
    "task_id": "...",
    "user_goal": "...",
    "production_input": {},
    "artifacts": {
        "order_analysis": {},
        "constraint_analysis": {},
        "resource_analysis": {},
        "strategy": {},
        "solver_policy": {},
        "candidate_schedules": [],
        "evaluation": {}
    },
    "completed_agents": [],
    "pending_agents": [],
    "current_stage": "...",
    "recommended_schedule_id": None
}
```

优先复用项目已有：

```text
Session
artifacts
working state
pending state
```

不要重新造完全独立的 Memory 系统。

---

# 8. 排产策略升级：模板 + 参数化 + LLM 自动生成

现有策略模板继续保留：

```text
balanced
delivery
cost
balance_load
makespan
throughput
```

模板变成：

> Strategy Preset

而不是最终策略本身。

---

# 9. SchedulingStrategy 数据模型

建议定义统一模型：

```python
class SchedulingStrategy:
    strategy_id: str | None
    base_template: str | None
    objectives: dict
    hard_constraints: list
    soft_constraints: list
    critical_orders: list
    machine_preferences: dict
    machine_limits: dict
    overtime_policy: dict | None
    freeze_policy: dict | None
    solver_preferences: dict | None
    generated_by: str
    explanation: str
```

---

# 10. Objectives 参数

当前至少支持：

```text
makespan
weighted_tardiness_total
energy_cost
machine_busy_cv
```

建议新增：

```text
setup_changeover
schedule_stability
```

示例：

```json
{
  "makespan": 1.0,
  "weighted_tardiness_total": 2.5,
  "energy_cost": 0.05,
  "machine_busy_cv": 12.0,
  "setup_changeover": 1.8,
  "schedule_stability": 0.5
}
```

---

# 11. Hard Constraints

例如：

```json
[
  {
    "type": "order_due_required",
    "job_id": "A12",
    "due_date": "..."
  },
  {
    "type": "machine_unavailable",
    "machine_id": "M03",
    "start": "...",
    "end": "..."
  }
]
```

Hard Constraint 不允许只存在 Prompt 中。

必须进入确定性 Constraint / Solver 层。

---

# 12. Soft Constraints

例如：

```json
[
  {
    "type": "avoid_machine_overload",
    "machine_id": "M03",
    "target_utilization": 0.85,
    "penalty": 1.5
  },
  {
    "type": "reduce_changeover",
    "weight": 1.8
  }
]
```

---

# 13. Strategy Agent 示例

用户：

```text
明天订单很多，
重点保证客户A和客户B按期，
普通订单可以稍微延期，
尽量减少换型，
M03不要超负荷，
能耗暂时不重要。
```

Strategy Agent 输出：

```json
{
  "base_template": "delivery",
  "objectives": {
    "makespan": 1.0,
    "weighted_tardiness_total": 2.5,
    "energy_cost": 0.05,
    "machine_busy_cv": 12.0,
    "setup_changeover": 1.8
  },
  "hard_constraints": [
    {
      "type": "order_on_time",
      "job_id": "A"
    },
    {
      "type": "order_on_time",
      "job_id": "B"
    }
  ],
  "soft_constraints": [
    {
      "type": "avoid_machine_overload",
      "machine_id": "M03"
    }
  ],
  "generated_by": "llm",
  "explanation": "优先保证重点客户交期，并抑制瓶颈设备M03负载，同时减少换型。"
}
```

---

# 14. 前端策略配置

排产页面增加三种模式。

## Mode A：快速模板

```text
综合平衡
交付优先
成本优先
负载均衡
最短周期
吞吐优先
```

## Mode B：参数化配置

允许用户调整：

```text
完工时间
交期拖期
能耗
设备均衡
换型
计划稳定性
```

以及：

```text
关键订单
设备限制
是否允许加班
冻结范围
```

## Mode C：AI 智能策略

自然语言输入：

```text
描述你希望这次生产计划重点考虑什么...
```

点击：

```text
AI生成策略
```

系统展示：

```text
识别出的业务目标
生成的权重
Hard Constraints
Soft Constraints
推荐 Solver 策略
```

用户确认后才执行排程。

不允许 LLM 输出后直接无提示执行。

---

# 15. Solver Agent 设计

Solver Agent 根据：

```text
problem_size
constraint_complexity
optimization_goal
required_latency
strategy
```

产生 SolverPolicy。

## 15.1 SolverPolicy

```python
class SolverPolicy:
    primary_solvers: list[str]
    fallback_solver: str | None
    time_budget_seconds: float
    max_candidates: int
    parameters: dict
    reason: str
```

示例：

```json
{
  "primary_solvers": ["ts", "ga"],
  "fallback_solver": "edd",
  "time_budget_seconds": 8,
  "max_candidates": 3,
  "parameters": {},
  "reason": "当前为中等规模、交期约束较强的问题，优先使用TS/GA生成高质量候选解。"
}
```

---

# 16. Solver 使用原则

当前已有 14 个 Solver，不再继续增加数量作为主要目标。

建议分组：

```text
Rule Heuristic
- SPT
- LPT
- MWKR
- MOPNR
- EDD

Metaheuristic
- TS
- GA
- SA
- ACO

Experimental RL
- Q
- DQN
- PPO
- Neuroevo
```

后续如需要，可以增加：

```text
OR-Tools CP-SAT
```

作为复杂约束问题基线。

---

# 17. RL Solver 原则

如果 RL Solver 当前不支持动态多目标 weights：

```text
不要伪装成完全支持参数化策略。
```

必须：

1. 在 Solver Catalog 中标识能力；
2. Solver Agent 判断是否适用；
3. Evaluation 中记录 limitation。

示例：

```json
{
  "solver": "ppo",
  "supports_dynamic_objectives": false
}
```

---

# 18. Evaluation Agent

输入：

```text
user_goal
SchedulingStrategy
candidate schedules
KPIs
constraints
```

输出：

```python
EvaluationResult = {
    "recommended_schedule_id": "...",
    "ranking": [],
    "tradeoffs": [],
    "constraint_checks": [],
    "recommendation_reason": "..."
}
```

原则：

```text
Hard Constraint Violation
→ 淘汰
```

再比较：

```text
KPI
+
业务目标
```

LLM 主要用于：

```text
Trade-off Explanation
Recommendation Explanation
```

不要让 LLM 随意推翻硬约束检查。

---

# 19. 智能排产结果前端

推荐布局：

```text
┌─────────────────────────────────────────────┐
│ AI 推荐生产计划                              │
│ 推荐方案：Scenario B                         │
│ 推荐理由：重点订单全部按期，换型减少...        │
├─────────────────────────────────────────────┤
│ 甘特图                                      │
├─────────────────────────────────────────────┤
│ KPI                                         │
│ Makespan | 延期 | 换型 | 负载 | 能耗          │
├─────────────────────────────────────────────┤
│ 重点订单                                    │
├─────────────────────────────────────────────┤
│ 瓶颈设备                                    │
├─────────────────────────────────────────────┤
│ Alternative A | Recommended B | Alternative C│
└─────────────────────────────────────────────┘
```

用户点击：

```text
采用该计划
```

后写入生产计划库。

---

# 20. Production Execution Simulator

当前已有生产看板倍速执行计划的能力，应继续保留。

不要命名为真实 MES。

建议统一命名：

> Production Execution Simulator

中文：

> 生产执行仿真器

---

# 21. 仿真流程

```text
Production Plan
      ↓
Start Simulation
      ↓
Simulation Clock
      ↓
waiting
→ running
→ completed
```

速度建议：

```text
1x
5x
10x
50x
```

看板展示至少：

```text
仿真时间
计划版本
当前订单
当前工序
设备运行状态
WIP
计划进度
实际进度
预计完成时间
甘特进度
```

---

# 22. 动态事件录入

继续保留用户人工录入。

建议支持：

```text
设备故障
插单
物料延期
交期调整
订单取消
数量变化
优先级变化
计划停机
质量异常
人员缺岗
```

---

# 23. 自动扰动仿真

新增可选：

```text
自动异常仿真
```

两种模式：

### Random

随机生成异常。

### Scenario Script

按固定脚本：

```text
10:30 M03 failure 180min
13:00 Material-X delay 120min
15:00 Job-A operation overrun 30min
```

更适合 Demo 和测试。

---

# 24. 动态异常 Multi-Agent

动态情况不是第一主线。

异常发生后复用智能排产能力。

例如：

```text
Machine Breakdown
      ↓
Asset Analysis
      ↓
Planning Supervisor
      ↓
Resource / Constraint
      ↓
Strategy
      ↓
Solver
      ↓
Evaluation
      ↓
Delivery Impact
```

---

# 25. R0 / R1 / R2

必须保留现有设计。

## R0

```text
原始生产计划
```

## R1

```text
异常发生
+
不采取重新调度
```

让延迟自然传播。

## R2

```text
异常发生
+
智能重新调度
```

---

# 26. R0 / R1 / R2 前端比较

```text
┌────────────┬────────────┬────────────┐
│ R0 原计划   │ R1 不干预   │ R2 智能重排 │
├────────────┼────────────┼────────────┤
│ 甘特图      │ 甘特图      │ 甘特图      │
│ 延期 0      │ 延期 4      │ 延期 1      │
│ 100         │ 126         │ 108         │
└────────────┴────────────┴────────────┘
```

同时给出：

```text
受影响订单
延迟
KPI变化
调整工序数量
推荐原因
```

---

# 27. 本轮不重点实现的内容

暂缓：

```text
预测性维护深度模型
完整 QMS
完整 MES
真实 IoT
复杂 RBAC
全面 MCP 化
全面 LangGraph 重构
大量新增 Agent
大量新增 Solver
```

本轮核心只有：

```text
智能排产
+
参数化策略
+
Multi-Agent 排产协作
+
生产仿真
+
动态重排
```

---

# 28. 实施阶段

## Phase 0：代码审计

Coding Agent 先核实：

```text
当前 Scheduling Agent
现有 6 个 Agent
30 Tools
6 Strategy Templates
14 Solvers
weights
BOM
production execution
R0/R1/R2
preview
SSE
Session
HITL
```

必须以代码为准。

## Phase 1：SchedulingStrategy 参数化

实现：

```text
SchedulingStrategy model
Objectives
Hard Constraints
Soft Constraints
Critical Orders
Resource Preference
```

兼容原 6 模板。

## Phase 2：智能排产 Multi-Agent

增加 / 重构：

```text
PlanningSupervisorAgent
OrderAgent
ConstraintAgent
ResourceAgent
StrategyAgent
SolverAgent
EvaluationAgent
```

注意：

不要一次删除旧 Agent。

采用新 API / Feature Flag 逐步切换。

## Phase 3：Agent 通信

增加统一：

```text
AgentTask
AgentResult
PlanningTaskState
```

支持：

```text
Order + Constraint + Resource 并行
↓
Strategy
↓
Solver
↓
Evaluation
```

## Phase 4：SolverPolicy

实现：

```text
solver capability
solver selection
solver parameters
time budget
candidate number
fallback
```

## Phase 5：Evaluation

实现：

```text
hard constraint validation
candidate ranking
tradeoff explanation
recommendation
```

## Phase 6：前端智能排产

增加：

```text
Quick Template
Parameter Mode
AI Strategy Mode
```

增加智能排产结果页。

## Phase 7：Production Simulator 对接

推荐计划确认后：

```text
Apply Plan
↓
Production Simulator
```

## Phase 8：动态事件 + R0/R1/R2

复用现有能力。

增加：

```text
自动异常脚本
```

---

# 29. 推荐 API

根据现有 API 风格调整，不要求机械照搬。

## 智能排产分析

```text
POST /api/planning/analyze
```

## AI 策略生成

```text
POST /api/planning/strategy/generate
```

## 智能排产

```text
POST /api/planning/run
```

## 预览

```text
POST /api/planning/preview
```

## 确认计划

```text
POST /api/planning/confirm
```

## 仿真

```text
POST /api/simulation/start
POST /api/simulation/pause
POST /api/simulation/resume
POST /api/simulation/speed
GET  /api/simulation/state
```

## 动态事件

尽量兼容已有：

```text
POST /api/events/*
```

---

# 30. 测试要求

至少新增：

```text
test_ai_strategy_generation
test_parameterized_strategy
test_critical_order_constraint
test_agent_parallel_analysis
test_solver_policy_selection
test_candidate_schedule_evaluation
test_template_backward_compatibility
test_simulation_start_from_recommended_plan
test_dynamic_event_r0_r1_r2
```

---

# 31. 第一批黄金测试场景

## Case 1：正常智能排产

输入：

```text
订单 A / B / C
设备 M01-M05
A 是重点客户
```

自然语言：

```text
优先保证A订单，
其他订单兼顾整体完工时间。
```

验证完整链路：

```text
Order Agent
Constraint Agent
Resource Agent
Strategy Agent
Solver Agent
Evaluation Agent
```

## Case 2：参数化策略

用户：

```text
交期最重要，
换型第二重要，
能耗暂时忽略，
M03负载不要超过85%。
```

验证 LLM 正确生成：

```text
objective weights
soft constraint
machine preference
```

## Case 3：生产仿真

智能排产完成：

```text
Confirm
↓
Start Simulation
↓
10x
```

计划正确执行。

## Case 4：设备故障

仿真到中途：

```text
M03故障180min
```

输出：

```text
R0
R1
R2
```

并展示 KPI 对比。

---

# 32. Coding Agent 第一轮执行 Prompt

```text
请阅读仓库和《MetaForge 智能排产 Multi-Agent 新设计实现文档.md》。

本轮不要直接大规模修改代码。

先完成现状审计，并输出：

1. 当前智能排产完整链路。
2. 当前 6 个策略模板如何进入 scheduling.run。
3. weights 是否真正影响每类 Solver。
4. 当前 14 Solver 的能力矩阵。
5. 当前自然语言排产到底能解析哪些参数。
6. 当前 Agent 是否一个请求只执行一个 Agent。
7. 当前 Session / artifacts 是否可以作为 PlanningTaskState 基础。
8. 当前 Production Execution Simulator 的真实实现。
9. 当前 R0/R1/R2 实现。
10. 当前前端排产输入与结果展示。

然后给出 Phase 1：
SchedulingStrategy 参数化的文件级修改计划。

不要根据文档猜代码。
以仓库代码为唯一事实来源。
```

---

# 33. Coding Agent 第二轮执行 Prompt

```text
执行 Phase 1：SchedulingStrategy 参数化。

要求：

1. 保留现有 6 个 Strategy Template。
2. 新增统一 SchedulingStrategy model。
3. 模板需要能够转换为 SchedulingStrategy。
4. 支持 objectives。
5. 支持 hard_constraints。
6. 支持 soft_constraints。
7. 支持 critical_orders。
8. 支持 machine_preferences。
9. 现有 scheduling.run 保持兼容。
10. 不修改 Solver 算法逻辑，除非为了接收已经支持的参数。
11. 新增单元测试。
12. 跑完整回归测试。
```

---

# 34. Coding Agent 第三轮执行 Prompt

```text
执行 Phase 2-3：智能排产 Multi-Agent。

实现：

PlanningSupervisorAgent
OrderAgent
ConstraintAgent
ResourceAgent
StrategyAgent
SolverAgent
EvaluationAgent

要求：

1. Agent 不直接互相调用。
2. 使用 AgentTask / AgentResult / PlanningTaskState。
3. Order / Constraint / Resource 允许并行。
4. Strategy 必须消费前三者 artifacts。
5. SolverAgent 只选择算法与参数，不计算甘特。
6. APS Solver 继续走原确定性 Tool。
7. Evaluation 先做 hard constraint validation，再比较 KPI。
8. LLM 只负责业务解释，不得绕过确定性 constraint validation。
9. 保留旧 orchestrator 兼容。
10. 新链路通过独立入口或 feature flag 启用。
```

---

# 35. Coding Agent 第四轮执行 Prompt

```text
执行 Phase 4-6：

1. SolverPolicy。
2. 候选排程评估。
3. AI Strategy 前端。
4. 参数化策略前端。
5. 智能排产结果页面。

要求：

最终用户可以选择：

A. 快速模板
B. 参数化策略
C. AI自然语言策略

AI策略生成后必须先展示给用户确认，
不能直接执行排程。

排程完成后显示：

推荐甘特
KPI
重点订单
瓶颈
推荐原因
Alternative A/B
```

---

# 36. 最终验收

本轮改造完成后，必须能够演示：

```text
用户配置生产数据
       ↓
输入自然语言生产目标
       ↓
Order / Constraint / Resource Agent
       ↓
Strategy Agent 参数化策略
       ↓
Solver Agent 选择求解器
       ↓
APS Solver
       ↓
Evaluation Agent
       ↓
推荐生产计划
       ↓
确认
       ↓
倍速生产执行仿真
       ↓
录入动态事件
       ↓
R0 / R1 / R2
       ↓
智能重排
```

系统升级是否成功，不看：

```text
Agent 数量
Prompt 数量
Framework 数量
```

而看是否真正实现：

> **业务目标 → 参数化排产策略 → 多 Agent 分析 → Solver 求解 → 方案评价 → 可执行生产计划 → 仿真验证 → 异常重排**
