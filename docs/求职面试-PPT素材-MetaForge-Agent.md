# Multi-Agent 制造排程智能体系统：求职面试 PPT 素材

> 适用岗位：Agent 开发工程师  
> 建议时长：约 7 分钟（四个项目总时长 20 分钟）  
> 结构：7 页主讲 + 4 页备份  
> 核心结论：**这不是让大模型“计算甘特图”，而是让 Agent 负责任务理解、决策编排和风险控制，让确定性求解器负责排程计算。**

---

## 一、整体讲述策略

### 面试官听完应该记住什么

1. 我不是简单调用大模型，而是设计了一套可执行、可追踪、可回退的 Agent 工作流。
2. 我知道如何划分 LLM、Agent、Tool、业务服务和数据库之间的责任边界。
3. 我处理过真实 Agent 工程问题：路由歧义、长链路上下文、工具调用约束、HITL、超时回退和端到端评测。
4. Agent 最终连接的是制造排程、异常重调度、物料和交期等真实业务能力，而不是停留在 Demo 对话层。

### 7 分钟时间分配

| 页码 | 内容 | 建议时间 |
|---|---|---:|
| 1 | 项目背景与为什么引入 Agent | 45 秒 |
| 2 | 两层 Multi-Agent 总体架构 | 60 秒 |
| 3 | Supervisor、Plan-and-Solve 与任务拆解 | 60 秒 |
| 4 | Function Calling 式 Tool 执行体系 | 65 秒 |
| 5 | Memory、Context、HITL 与稳定性 | 70 秒 |
| 6 | 动态重排案例与评测结果 | 65 秒 |
| 7 | 代码实现与技术难点 | 55 秒 |

---

# 二、7 页主讲素材

## 第 1 页：传统 APS 能算排程，但难以处理自然语言决策链

### 这一页的任务

用业务问题引出 Agent，回答“为什么不能只做几个 API 或一个聊天机器人”。

### PPT 标题

**传统 APS 能算排程，但难以理解和执行跨系统的业务决策**

### 屏幕文案

- 制造排程输入分散在订单、工艺、设备、物料和生产执行状态中，业务人员很难一次给出完整参数。
- “重新排程”不是一个 API：还包含意图判断、约束分析、策略选择、算法求解、结果解释和人工确认。
- 引入 Agent 的目的不是替代求解器，而是把自然语言需求转成一条可审计、可回退的确定性执行链。

### 建议图示

左侧画业务人员的一句话：

> “3 号机坏了 4 小时，看看哪些订单会延期，给我一个影响最小的重排方案。”

右侧拆成六个动作：

```text
识别故障 → 读取执行态 → 解析事件 → 生成重排 → 对比影响 → 人工确认
```

底部用一句话做边界强调：

> LLM 负责理解与编排，APS Solver 负责甘特图和 KPI 计算。

### 口述稿

这个项目面向离散制造车间排程。传统 APS 已经能够接收结构化参数并运行算法，但用户在实际使用中往往只会说“交付优先排一下”或者“3 号机坏了，帮我重排”。这类需求不仅缺参数，还跨越订单、设备、交期、排程和落库多个环节。如果只接一个大模型，它容易直接编造结果；如果只暴露 API，业务人员又需要理解大量字段。因此我引入 Agent 作为决策编排层：负责识别用户意图、补齐缺失信息、选择业务能力、组织执行顺序和解释结果；真正的甘特图仍由确定性求解器生成。

### 面试追问提醒

如果被问“为什么不是单 Agent”，先不要回答“因为任务复杂”。应回答：

> 单 Agent 同时承担路由、排程、物料、交期和计划库操作，Prompt 与 Tool 白名单会不断膨胀，错误影响面也会扩大。拆成业务域 Agent 后，每个 Agent 只看到自己的工具和上下文，便于限制权限、单独评测和局部降级。

---

## 第 2 页：采用“六岗分诊 + 排程域内协作”的两层架构

### 这一页的任务

讲清楚 Supervisor 与 6 类 Agent 的真实关系，避免被误解为每次请求都会启动 6 个 Agent。

### PPT 标题

**两层架构避免每次请求都唤醒整个 Agent 团队**

### 屏幕文案

- 外层 Router 在 6 个业务 Agent 中单选：排程、异常、齐套、交期、方案对比、计划管理。
- 只有复杂的排程请求进入 Planning Supervisor，再拆给 Order、Constraint、Resource 三个分析 Agent。
- Agent 通过 `AgentTask / AgentResult + artifacts` 协作，不让多个 Agent 自由对话，降低上下文漂移。

### 建议架构图

```text
用户 / APS / 助手
        ↓
Router：GLM 路由 + 规则 Guard
        ↓ 六选一
┌────────┬────────┬────────┬────────┬────────┬────────┐
排程     异常     齐套     交期     What-if  计划管理
 │
 ↓
Planning Supervisor
 │
 ├─ Order Agent：关键订单、临期与优先级
 ├─ Constraint Agent：硬约束、软约束
 └─ Resource Agent：瓶颈、负载与候选资源
        ↓
Strategy → HITL → SolverPolicy → Solvers → Evaluator → Package
```

### Supervisor 的职责

```text
维护 PlanningTaskState
→ 处理 Agent 依赖
→ Order 先执行
→ Constraint 与 Resource 可并行
→ 合并 artifacts
→ 交给策略、求解和评价流水线
```

Supervisor **不直接计算排程**。

### 口述稿

我没有把系统设计成六个 Agent 自由群聊，而是采用两层架构。外层是业务分诊，Router 根据意图只选择一个业务 Agent。这样异常重排不会看到计划库删除工具，计划管理也不会误调用求解器。只有智能排程这类真正需要多视角分析的任务，才进入内层 Supervisor。Supervisor 先调用 Order Agent 分析订单，再将订单分析注入 Constraint Agent；Resource Agent 与 Constraint Agent 可以并行，最后统一合并为 artifacts，交给策略生成、求解器策略和评价模块。这种设计的重点是职责隔离、依赖显式和结果可追踪，而不是追求 Agent 数量。

### 真实代码依据

- 六类业务 Agent 元数据：[`src/metaforge/agents/registry_meta.py`](../src/metaforge/agents/registry_meta.py)
- 外层路由与 Guard：[`src/metaforge/orchestrator/router.py`](../src/metaforge/orchestrator/router.py)
- 内层 Supervisor：[`src/metaforge/planning_collab/supervisor.py`](../src/metaforge/planning_collab/supervisor.py)
- Agent 协议与任务状态：[`src/metaforge/planning_collab/protocol.py`](../src/metaforge/planning_collab/protocol.py)

---

## 第 3 页：Plan-and-Solve 将自然语言变成可预览的任务计划

### 这一页的任务

回答“任务怎么拆”“如何避免 LLM 边想边乱调工具”。

### PPT 标题

**先生成计划、再确定性执行，让每一步都可预览和追踪**

### 屏幕文案

```text
Route → Plan → Parse → Execute → Summarize
```

- Route：GLM 识别业务意图，规则 Guard 纠正高风险误路由。
- Plan：生成 Tool 步骤并通过 Agent 白名单校验；Preview 只展示计划，不产生副作用。
- Execute：Harness 顺序执行 Tool，结果写入 artifacts，供后续步骤和最终摘要使用。

### 用“设备故障”展示任务拆解

用户输入：

> “3 号机坏了 4 小时，按当前生产进度重排。”

对应计划：

```text
1. execution.get_state             读取仿真时钟和原计划
2. events.parse_event              解析 machine_breakdown 参数
3. events.check_insert_job         事件类型统一校验节点
4. events.reschedule               生成 R0/R1/R2
5. delivery.compare_commitment     对比交期变化
6. delivery.explain_impact         生成业务解释
```

### 关键设计选择

项目不是所有链路都交给 LLM 自由规划：

- 开放性较高的需求支持 LLM Plan，并在失败时回退规则计划。
- 排程协作、异常重排等关键业务采用 Supervisor 或固定阶段流水线，保证流程稳定。
- Preview 生成的 Plan 会缓存到请求上下文，Run 阶段复用，避免同一请求重复调用 LLM。

### 口述稿

在任务执行上，我采用 Plan-and-Solve。首先路由到唯一业务 Agent，然后生成一个结构化 Tool 计划，Preview 阶段只返回 Route、Plan 和 Parse 轨迹，不执行有副作用的操作。用户确认执行后，Harness 按步骤调用 Tool，并把每步结果写到 artifacts，最后再组织用户答复。这里我没有把所有流程都交给 LLM：开放性较高的意图可以由 LLM 生成计划，而设备故障、插单和排程协作等关键链路使用固定流水线或 Supervisor。这样同时保留了自然语言灵活性和制造业务所需的确定性。

### 真实代码依据

- Preview 与 Plan 缓存：[`src/metaforge/orchestrator/preview.py`](../src/metaforge/orchestrator/preview.py)
- LLM Plan 节点：[`src/metaforge/orchestrator/llm/chain.py`](../src/metaforge/orchestrator/llm/chain.py)
- 异常固定阶段计划：[`src/metaforge/events_collab/plan_steps.py`](../src/metaforge/events_collab/plan_steps.py)
- 异常执行流水线：[`src/metaforge/events_collab/pipeline.py`](../src/metaforge/events_collab/pipeline.py)

---

## 第 4 页：Tool 层把 LLM 的不确定性隔离在排程计算之外

### 这一页的任务

回答 Function Calling、Tool 接入和 30 个 Tool 如何治理。

### PPT 标题

**Tool Contract 将模型决策转成受控的制造业务调用**

### 屏幕文案

- 项目阶段封装 30 个业务 Tool；当前仓库在此基础上新增 4 个 `planning.*` Tool，共 34 个。
- Tool 统一声明名称、输入/输出 Schema、Handler、风险等级、超时和重试策略。
- LLM 只生成结构化调用意图，白名单和 ToolExecutor 决定“能否执行、如何执行”。

### 建议执行链图

```text
LLM 输出 JSON Plan
        ↓
allowed_tools 白名单校验
        ↓
Tool Registry 查找 ToolSpec
        ↓
Policy Gate：allow / ask(HITL) / deny
        ↓
输入 Schema 校验
        ↓
Handler 执行 + timeout / retry
        ↓
输出 Schema 校验 + RunEvent
        ↓
ToolResult → artifacts
```

### 业务能力如何接入

```text
6 种策略模板
→ 转成多目标 weights / hard / soft constraints
→ SolverPolicy 选择 primary + fallback + time budget
→ 14 类 Solver 统一走 solver_registry
→ Evaluator 先淘汰硬约束违法方案，再按综合指标排序
```

```text
8 类动态事件
→ 标准 event_envelope(event_type + params)
→ dispatch_event_reschedule 分发到对应业务函数
→ 统一返回 schedule_results + impact_report + R0/R1/R2
```

### 关于“Function Calling”的准确口径

当前模型客户端使用 `response_format={"type":"json_object"}`，由自研 Parser、白名单和 ToolExecutor 实现 Function Calling 式调用；没有向模型接口传原生 `tools/tool_calls` 参数。

面试时建议说：

> 我实现的是一套自研的结构化 Function Calling 执行链：模型输出 JSON Tool Plan，系统完成白名单校验、Schema 校验、策略门禁和确定性执行。

不要说：

> 我直接使用了模型厂商原生 Function Calling。

### 口述稿

Tool 层是项目里最关键的隔离层。项目阶段有 30 个业务 Tool，当前仓库后续增加了 4 个 planning Tool。每个 Tool 都通过 ToolSpec 描述输入、输出和处理函数，Agent 只能选择 allowed_tools 中的工具。执行时先经过风险门禁，再校验输入 Schema，然后处理超时、重试和异常，最后校验输出并生成运行事件。求解器和业务规则也不是写进 Prompt，而是通过 Tool 和服务接入：6 个策略模板先映射成 SolverPolicy，再从 14 个求解器中选择主求解器和兜底求解器；8 类异常事件则统一归一化为 event_envelope 后分发。这样即使模型判断存在波动，排程计算仍然可复现。

### 真实代码依据

- Tool 类型契约：[`src/metaforge/tools/base.py`](../src/metaforge/tools/base.py)
- Tool 注册与执行入口：[`src/metaforge/tools/registry.py`](../src/metaforge/tools/registry.py)
- 风险、Schema、超时与重试：[`src/metaforge/harness/tool_executor.py`](../src/metaforge/harness/tool_executor.py)
- LLM Tool 白名单解析：[`src/metaforge/orchestrator/llm/parsers.py`](../src/metaforge/orchestrator/llm/parsers.py)
- 14 个求解器注册表：[`src/metaforge/utils/solver_registry.py`](../src/metaforge/utils/solver_registry.py)
- 8 类事件分发：[`src/metaforge/services/event_reschedule.py`](../src/metaforge/services/event_reschedule.py)

---

## 第 5 页：上下文工程的重点是边界正确，而不是把历史全部塞给模型

### 这一页的任务

把 Memory、Context Engineering、HITL、重试与回退讲成一套稳定性设计。

### PPT 标题

**三层 Memory + Context Compiler 保证长链路任务连续且不污染业务事实**

### 屏幕文案

- Session：保存 `session_id`、上下文、artifacts 和最近 Agent，默认 TTL 1 小时。
- Task State：保存 working、pending clarification、PlanningTaskState 和一次任务的分析 artifacts。
- Business Facts：计划、MES 执行态、甘特、工单和库存由 Mongo/业务服务维护，Memory 不作为事实权威。

### 建议图示

```text
短期会话 Session
  session_id / artifacts / context / TTL
             ↕
任务状态 Task
  working / pending / PlanningTaskState
             ↕ 只保存引用和摘要
业务事实 Business Facts
  plan / MES / gantt / jobs / inventory / MongoDB
```

### Context Engineering 细节

- 用户目标最多保留 500 字；订单按交期与优先级排序后最多取 30 条摘要。
- Prompt 只传订单关键字段、机台 ID、约束目录以及 BOM/甘特数量，不传整张甘特图。
- 生成稳定 `context_hash`，用于 Preview、Run 和多 Agent 协作中的一致性追踪。
- 最终 summarize 只读取限定 artifacts 字段、最近 8 个 Tool 步骤，并将摘要截断到约 3000 字符。
- Preview 生成的 Plan 写入 `cached_plan_steps`，Run 直接复用。

### HITL 与异常稳定性

| 风险点 | 设计 |
|---|---|
| 信息不完整 | 返回 `need_input / pending_clarification`，记录 pending route，下一轮继续原 Agent |
| 策略可能不合理 | `WAITING_APPROVAL`，支持 approve、reject、edit_and_approve |
| 排程结果要写库 | `propose_persist` 先生成预览和 15 分钟一次性 token，再调用确认接口 |
| GLM 超时或输出错误 | `rule_fallback` 回退规则路由、规则策略或固定计划 |
| Tool 失败 | ToolExecutor 支持 timeout/retry；可选 Reflect 决定 retry、clarify 或 human |
| LLM 改写数值 | R0/R1/R2 已有确定性摘要时禁止 LLM 重写关键数字 |

### 口述稿

长链路任务最容易出现的问题不是模型忘记一句话，而是把会话状态、任务中间态和业务事实混在一起。因此我把 Memory 分成三层：Session 管跨轮上下文，Task State 管当前任务和待补充信息，Mongo 与业务服务保存甘特、工单和库存等事实。Memory Boundary 会阻止把这些事实复制成另一个权威来源。进入模型前，Context Compiler 只保留高价值摘要，例如最多 30 条订单、约束目录和甘特数量，并生成稳定 hash。对于副作用操作，策略先进入 HITL 审批；排程落库必须先生成预览和 15 分钟确认 token。模型失败时则回退规则路径，Tool 层还能处理超时、重试和人工升级。

### 真实代码依据

- Session 与 TTL：[`src/metaforge/orchestrator/session.py`](../src/metaforge/orchestrator/session.py)
- MemoryManager：[`src/metaforge/memory/manager.py`](../src/metaforge/memory/manager.py)
- Memory 事实边界：[`src/metaforge/memory/boundary.py`](../src/metaforge/memory/boundary.py)
- Pending 续聊路由：[`src/metaforge/memory/pending.py`](../src/metaforge/memory/pending.py)
- Context 压缩：[`src/metaforge/strategy/context_builder.py`](../src/metaforge/strategy/context_builder.py)
- HITL Token：[`src/metaforge/services/persist_store.py`](../src/metaforge/services/persist_store.py)
- 策略审批：[`src/metaforge/strategy/hitl.py`](../src/metaforge/strategy/hitl.py)

---

## 第 6 页：用动态重排场景验证 Agent 到求解器的完整闭环

### 这一页的任务

用一个典型案例落地架构，并给出可信评测数字。

### PPT 标题

**设备故障与紧急插单最终落到 R0/R1/R2 的可量化决策**

### 左侧：场景闭环

```text
用户：3 号机当前故障 4 小时
        ↓
读取 sim_time、baseline_gantt、jobs_snapshot
        ↓
解析 machine_id / start / duration / freeze_time
        ↓
R0：原计划
R1：不重排，仅传播故障造成的延迟
R2：冻结已完成工序 + 故障窗口 + 残段重新求解
        ↓
对比 makespan、拖期、受影响订单和调整工序数
        ↓
人工选择并确认是否覆盖原计划
```

插单场景增加一层多轮补全：如果新订单缺少工序、机台或加工时长，Agent 返回 `need_input`；用户补充后通过 `merge_insert_job` 合并草稿，再执行局部修复或全局重排。

### 右侧：评测结果

| 评测层 | 结果 | 证明什么 |
|---|---:|---|
| L2 Preview | **55/63，87.3%** | 路由、Plan、Parse 整体准确性 |
| L3 核心冒烟 | **14/16，87.5%** | Agent.run、Tool 与 artifacts 契约可跑通 |
| Events L3 全量 | **14/14，100%** | 故障、插单、改交期等异常链路稳定 |
| GLM 验收冒烟 | **17/17** | 指定联调用例全部通过 |

### 评测口径必须主动说明

- L2 用例集共 65 条，其中 2 条 slow 跳过，因此 87.3% 是 55/63，不是 57/65。
- L3 全量首轮为 32/51 = 62.7%，另有 14 条跳过；失败包含测试 Harness、Mongo 环境、路由边界和缺少 plan_id，不能将其包装成 87%。
- 简历建议使用“L2 87.3% + L3 核心冒烟 87.5% + Events 14/14”，证据最完整。

### 口述稿

我用设备故障和紧急插单作为核心验收场景。以设备故障为例，Agent 先读取当前仿真时钟和原计划，再生成三份结果：R0 是原计划，R1 模拟不干预时延迟如何传播，R2 则冻结已完成工序，把故障窗口写入资源约束后只对剩余工序重排。最终系统比较完工时间、拖期和受影响订单，再由用户决定是否落库。评测上，我将 Preview 和真实执行分层：65 条 L2 用例实际执行 63 条，通过 55 条，准确率 87.3%；L3 核心冒烟为 14/16；异常重排 14 条端到端用例全部通过。这样能区分“模型理解正确”和“业务工具真正执行成功”。

### 真实代码依据

- 故障与插单重排：[`src/metaforge/services/event_reschedule.py`](../src/metaforge/services/event_reschedule.py)
- L2 报告：[`reports/agent_e2e_l2_20260601-114642.json`](../reports/agent_e2e_l2_20260601-114642.json)
- L3 核心报告：[`reports/agent_e2e_l3_20260601-125055.json`](../reports/agent_e2e_l3_20260601-125055.json)
- L3 全量报告：[`reports/agent_e2e_l3_20260601-130930.json`](../reports/agent_e2e_l3_20260601-130930.json)

---

## 第 7 页：代码实现与技术难点

### 这一页的任务

作为主讲部分最后一页，用真实代码说明你解决了哪些 Agent 工程难题。

### PPT 标题

**真正的难点不是“调用多个 Agent”，而是保证计划、状态和业务结果一致**

### 屏幕文案

#### 难点 1：如何避免 Agent 越拆越乱

- 外层六岗互斥路由，内层排程才由 Supervisor 拆分。
- `AgentTask / AgentResult / PlanningTaskState` 统一协议，子 Agent 只通过 artifacts 交付结果。
- Order 先执行，Constraint 使用订单分析，Resource 可并行，依赖关系写在代码里。

代码入口：`planning_collab/supervisor.py::run_collab_analyze`

#### 难点 2：如何防止 LLM 调错工具或篡改业务结果

```python
allowed = set(allowed_tools)
if tool not in allowed:
    raise ValueError(f"tool not allowed: {tool}")
```

- LLM 生成的每一步都必须通过 Agent 白名单。
- ToolExecutor 再做风险、输入/输出 Schema、超时与重试控制。
- R0/R1/R2 已产生确定性摘要后，最终回答不再让 LLM 重写关键数字。

代码入口：`orchestrator/llm/parsers.py`、`harness/tool_executor.py`、`agents/base.py`

#### 难点 3：如何保证 Preview、Run 和多轮续聊使用同一上下文

- Context Compiler 生成稳定 `context_hash`。
- Preview 缓存 `cached_plan_steps`，Run 不重复规划。
- pending route 让插单补充和排程澄清继续回到原 Agent。
- Memory Boundary 保证业务事实只有 Mongo/服务一个权威来源。

代码入口：`harness/context.py`、`orchestrator/preview.py`、`memory/pending.py`

### 口述稿

这个项目中最难的不是创建多个 Agent 类，而是控制协作边界。第一，我用两层架构和统一协议避免 Agent 自由群聊，所有依赖都显式写在 Supervisor 中。第二，模型生成的工具必须先通过 allowed_tools，ToolExecutor 再执行风险和 Schema 校验；对于异常重排的关键数字，代码会直接使用确定性摘要，避免模型二次改写。第三，Preview、Run 和多轮续聊必须看到同一个任务状态，因此我增加了 context_hash、Plan 缓存和 pending route，并明确 Memory 不保存甘特等事实权威。这三个问题分别解决了多 Agent 可维护性、工具调用安全性和长链路一致性。

### 现场建议打开的 5 个文件

1. [`src/metaforge/orchestrator/router.py`](../src/metaforge/orchestrator/router.py)：GLM 路由、规则 Guard、pending 续聊。
2. [`src/metaforge/planning_collab/supervisor.py`](../src/metaforge/planning_collab/supervisor.py)：Order → Constraint/Resource → artifacts。
3. [`src/metaforge/harness/tool_executor.py`](../src/metaforge/harness/tool_executor.py)：Tool 风险、Schema、超时、重试与事件。
4. [`src/metaforge/strategy/context_builder.py`](../src/metaforge/strategy/context_builder.py)：上下文裁剪与预算控制。
5. [`src/metaforge/services/event_reschedule.py`](../src/metaforge/services/event_reschedule.py)：设备故障和插单的 R0/R1/R2 实现。

### 收尾句

> 这个项目让我形成了一套 Agent 工程方法：让模型负责理解和决策，让 Harness 负责约束和追踪，让业务 Tool 负责确定性执行，并用分层评测验证每一个边界。

---

# 三、4 页备份素材

## 备份页 1：Supervisor + 6 类业务 Agent 分工

| Agent | 主要职责 | 典型输入 | 核心产物 |
|---|---|---|---|
| Scheduling | 正常排程、策略生成、多算法求解 | 排程目标、工单、机台 | `package`、推荐方案、分析 artifacts |
| Events | 故障、插单、改交期等动态重排 | event、执行态、原计划 | `impact_report`、R0/R1/R2 |
| Kitting | BOM 齐套、缺料与延迟推演 | 工单、BOM、库存 | 齐套报告、缺料影响 |
| Commitment | 交期风险和客户承诺说明 | 当前排程、due date | 交期评估、客户话术 |
| What-if | 多算法、多策略和异常假设对比 | variants、baseline | 方案排序、trade-off |
| Plans | 计划库 CRUD 与计划绑定 | 计划名称、plan_id | 计划列表、active_plan |

### 排程域内三个分析 Agent

| 子 Agent | 职责 | 输出 |
|---|---|---|
| Order | 识别关键订单、临期订单与优先级 | `order_analysis` |
| Constraint | 生成硬约束、软约束候选 | `constraint_analysis` |
| Resource | 分析瓶颈设备、负载和候选资源 | `resource_analysis` |

### 面试表述

> 外层是 6 个业务域 Agent，负责意图和权限隔离；内层是排程专用 Supervisor 和 3 个分析 Agent。Strategy、SolverPolicy、Evaluator 在当前代码里是确定性模块或流水线阶段，不应全部包装成可以自由对话的 Agent。

---

## 备份页 2：30 个 Tool、6 种策略、14 个求解器与 8 类事件

### 项目阶段 30 个 Tool 分类

| 能力域 | 数量 | 代表 Tool |
|---|---:|---|
| 排程 | 4 | `parse_intent`、`run`、`list_catalog`、`ask_clarification` |
| 计划与落库 | 10 | load/list/create/delete/bind/rename/duplicate/update/propose/confirm |
| 异常与执行态 | 6 | get_state、list/parse/check/merge/reschedule |
| 交期 | 4 | assess、compare、explain、customer_script |
| 物料与齐套 | 4 | check_static、compute_delays、predict、build_report |
| 方案对比 | 1 | `compare.variants` |
| 记忆门面 | 1 | `memory.run` |

当前仓库新增：

```text
planning.strategy_generate
planning.strategy_validate
planning.strategy_evaluate
planning.run
```

所以当前静态注册数为 34。面试时可以说：

> 项目交付阶段封装 30 个 Tool，后续为 Planning Harness 演进新增 4 个策略规划 Tool。

### 6 种策略模板

```text
balanced / delivery / cost / balance_load / makespan / throughput
```

本质是多目标权重和业务偏好的 Preset，不是 6 个独立求解算法。

### 14 个求解器

| 类别 | 求解器 |
|---|---|
| 规则启发式 5 个 | SPT、LPT、MWKR、MOPNR、EDD |
| 元启发式 4 个 | TS、GA、SA、ACO |
| RL/实验型 5 个 | Q-Learning、DQN Naive、DQN Replay、Neuroevolution、PPO |

SolverPolicy 根据策略选择 `primary_solvers + fallback_solver + time_budget + max_candidates`。RL 算法不伪装成支持动态多目标权重，Capability Matrix 会限制其使用场景。

### 8 类动态事件

```text
insert_order
machine_breakdown
due_date_change
planned_downtime
material_delay
priority_change
order_cancel
quantity_change
```

---

## 备份页 3：稳定性设计检查表

| 层级 | 风险 | 处理方式 | 关键产物 |
|---|---|---|---|
| Router | 模型误路由 | plans/events/kitting/commitment/whatif 等规则 Guard | `router=rule_override` |
| Plan | LLM 输出非法 Tool | allowed_tools 校验；失败回退规则 Plan | `plan_planner` |
| Tool | 参数或返回结构错误 | 输入/输出 Schema 校验 | `ToolResult` |
| Tool | 高风险副作用 | allow/ask/deny；ask 进入 HITL | `needs_hitl` |
| Tool | 超时/异常 | timeout + retry；运行事件记录 | `tool.retry/tool.end` |
| Agent | 缺参数 | clarify / need_input | `pending_action` |
| Session | 多轮续聊误路由 | pending_route_hint | `router=session_continue` |
| LLM | 服务不可用 | rule_fallback | 规则路由/规则策略 |
| Solver | 主求解器失败 | fallback_solver | 候选排程 |
| Persist | 未确认写库 | 15 分钟一次性 token | `confirm_token` |
| Memory | 状态与事实冲突 | Memory Boundary | warning / strict error |

需要注意：ToolExecutor 已实现通用 timeout/retry 能力，但当前业务 Tool 并非全部显式配置 retry_policy。面试时应说“平台层支持并按风险配置”，不要说“30 个 Tool 全部进行了多次自动重试”。

---

## 备份页 4：评测设计、结果与失败归因

### 分层评测

| 层级 | 测试目标 | 是否执行 Tool |
|---|---|---|
| L1 单元/规则 | Router、Parser、Tool、Memory、HITL 等模块 | 局部执行 |
| L2 Preview | 自然语言 → Agent → Plan → Parse | 否 |
| L3 Exec | 完整 Agent.run → Tool → artifacts | 是 |

### 核心结果

| 数据集 | 通过 | 失败 | 跳过 | 有效率 |
|---|---:|---:|---:|---:|
| L2 Preview 65 条 | 55 | 8 | 2 | 87.3%（55/63） |
| L3 核心冒烟 19 条 | 14 | 2 | 3 | 87.5%（14/16） |
| L3 全量 65 条首轮 | 32 | 19 | 14 | 62.7%（32/51） |

### L2 分项亮点

```text
events：14/14
plans：10/10
adversarial：12/12
```

### L3 全量失败归因

- 测试 Harness：长跑 `TestClient + Motor` 触发 event loop 问题。
- 路由边界：What-if 与 Scheduling、Commitment 与 Scheduling 存在语义重叠。
- 落库依赖：缺少 `plan_id` 或未启用 Mongo 测试环境。
- 用例跳过：slow 和 Mongo 标记未开启。

### 安全表述

推荐：

> 建立 65 条标准业务需求的 L2/L3 分层评测；L2 Preview 有效率 87.3%，L3 核心冒烟 87.5%，异常重排 Agent 14 条端到端用例全部通过。

不推荐：

> 65 条端到端用例准确率 87%，所有 Tool 调用 100% 通过。

后一句会把 Preview、Exec、跳过用例和工具验收混成一个口径，仓库报告无法直接支撑。

---

# 四、面试高频追问与建议回答

## 1. 为什么不用 LangGraph / LangChain？

> 项目核心是制造 Tool 的确定性、可复现和副作用治理，所以我使用轻量自研节点链与 Harness，显式控制 Route、Plan、Execute、Memory 和 HITL。设计思想与图编排类似，但当时没有引入 LangGraph/LangChain 运行时。这样可以直接复用现有 FastAPI、求解器和测试体系，也避免为简单的固定流水线增加框架复杂度。如果团队已有 LangGraph 基础设施，这套 AgentTask、ToolSpec 和状态机也可以映射过去。

## 2. 这算真正的 Multi-Agent 吗？

> 外层有 6 个独立业务 Agent，拥有不同的意图、工具范围和执行流水线；排程域内部还有 Supervisor 与 Order、Constraint、Resource 三个协作 Agent。它们通过统一协议和 artifacts 协作，而不是只在 Prompt 里扮演多个角色。为了稳定性，单请求不会并行启动全部业务 Agent。

## 3. 为什么不让 LLM 直接选算法并输出甘特？

> LLM 可以帮助理解“交付优先、成本优先”等目标，也可以生成策略参数，但甘特图必须满足工序前后关系、机台互斥、停机窗口等约束。让 LLM 直接输出很难验证且不可复现，因此模型只生成结构化策略，真正求解由 14 个确定性或训练后的算法完成，Evaluator 再检查硬约束和综合指标。

## 4. Plan-and-Solve 与 ReAct 怎么选？

> 主路径使用 Plan-and-Solve，便于 Preview、审计和缓存。ReAct/Reflect 作为可选能力，适合 Tool 执行后根据反馈调整下一步；但制造异常重排等关键链路更适合固定阶段流水线，因为执行顺序和副作用边界必须稳定。

## 5. Memory 为什么不直接保存全部甘特和工单？

> 甘特、工单和库存属于会变化的业务事实，如果同时存在 Mongo、Session 和 Memory 三份副本，会产生一致性问题。因此 Memory 只保存会话线索、pending 状态、偏好和任务摘要，真实数据按 plan_id 从业务服务读取。代码中的 Memory Boundary 会检测将事实字段写入 Memory 的行为。

## 6. 你如何证明 Agent 有效，而不是 Prompt Demo？

> 我把评测分成 Preview 和 Exec。Preview 检查路由、Tool Plan 与解析结构；Exec 真正运行求解器和业务 Tool，并验证 artifacts 契约。这样可以区分“模型理解错误”“工具规划错误”和“业务执行环境错误”。此外，异常重排 14 条 L3 用例全部通过，证明核心闭环不是只停留在文本输出。

## 7. 你在项目中最有价值的工作是什么？

> 我最核心的工作不是封装某一个算法，而是把自然语言、Multi-Agent 协作、确定性排程 Tool、Memory、HITL 和分层评测串成完整闭环，同时把每一层的责任边界和失败处理做清楚。

---

# 五、简历原文的口径校正建议

## 建议保留

- “对话—路由—规划—执行—反馈”的工作流。
- 六类业务 Agent、30 个项目阶段 Tool、6 种策略、14 类求解器、8 类异常事件。
- 三层 Memory、追问、上下文裁剪、摘要和缓存。
- L2 87.3%、L3 核心 87.5%、异常重排 14/14。

## 建议修改

### 原表述

> Supervisor + 6 类专家 Agent 协同架构。

### 更准确的表述

> 设计“Router + 6 类业务 Agent”的外层分诊架构，并在复杂排程域内构建 Planning Supervisor + Order/Constraint/Resource 三类分析 Agent，实现分层任务编排。

### 原表述

> 通过 Function Calling 完成结构化参数生成。

### 更准确的表述

> 实现 Function Calling 式结构化 Tool 调用链，通过 JSON Plan、Agent 白名单、Schema 校验与 ToolExecutor 完成参数生成和确定性执行。

### 原表述

> 100% 工具调用验收通过率。

### 更有证据的表述

> L2 Preview 有效率 87.3%，L3 核心端到端 87.5%，异常重排 Agent 14 条 L3 用例全部通过；17 条 GLM 验收冒烟用例全部通过。

## 时间口径提醒

简历写的是 `2025.04—2025.12`，但仓库中的主要 Agent E2E 报告生成于 2026 年 5—6 月。若这些报告属于项目结束后的个人复测或代码演进，面试时建议明确：

> 我的项目参与周期是 2025 年 4—12 月，之后基于同一代码库继续补充了 Harness 和自动化评测。

不要让面试官误以为 2026 年报告是在 2025 年项目周期内生成。

---

# 六、30 秒开场版

> 这个项目是面向离散制造的 Multi-Agent 排程系统。传统 APS 能运行算法，但业务人员很难把订单、设备、交期和异常一次转换成完整参数。我负责构建 Agent 决策编排层：外层 Router 在排程、异常、齐套、交期、对比和计划管理六个 Agent 中单选；复杂排程再由 Supervisor 拆给订单、约束和资源 Agent。模型只负责理解、规划和解释，30 个业务 Tool 与 14 个求解器负责确定性执行，并通过三层 Memory、HITL、规则回退和 L2/L3 评测保证可控性。

# 七、15 秒收尾版

> 这个项目的核心不是“让多个 Agent 聊天”，而是建立 LLM、Agent、Tool、求解器和业务事实之间的工程边界，让自然语言决策最终变成可验证、可回退、可人工确认的制造排程结果。
