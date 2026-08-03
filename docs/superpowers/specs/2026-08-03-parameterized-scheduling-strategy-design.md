# MetaForge 参数化 SchedulingStrategy 设计规范

> 日期：2026-08-03  
> 状态：**实现中 / 主干完成（前端轻量已接）** — 实现计划见 `docs/superpowers/plans/2026-08-03-parameterized-scheduling-strategy.md`  
> 范围：智能排产主线的**第一子项目**——参数化策略 + LLM 生成 + 评价闭环 + 轻量 UI  
> 依据：[`MetaForge_Intelligent_Scheduling_MultiAgent_Implementation.md`](../../../MetaForge_Intelligent_Scheduling_MultiAgent_Implementation.md) + 2026-08-02/03 头脑风暴确认结论  
> 非目标：本文件不实现完整 Supervisor 七 Agent、不全面迁移 LangGraph/MCP、不改 APS Solver 搜索内核

---

## 1. 执行摘要

将现有「6 策略模板 → `weights` 字典 → `compare_solvers`」升级为：

```text
结构化生产数据 + 自然语言目标
  → SchedulingStrategy（结构化说明书）
  → 轻量 SolverPolicy（选少量候选求解器）
  → 确定性 APS Solver（复用现有）
  → Evaluation（硬约束淘汰 + 软约束/目标打分）
  → Production Plan Package
```

**深度约定（评价闭环 B）：** 求解器内核不强制在搜索中消费全部硬/软约束；`adapters` 把策略映射为现有 `weights` / resource hints；`evaluator` 在求解后做硬约束确定性校验与软约束惩罚，非法候选不得成为 recommended。

**落地形态：** 新建独立模块 `metaforge.strategy` + `/api/planning/*`；旧 `/api/agents/scheduling` 并行兼容；替代能力验收通过后**删除**对应旧代码（不搞永久双轨）。

**明确禁止：** LLM 直接修改算法源码；LLM 直接算甘特；LLM 硬约束未经验证即写库；为堆技术栈引入 LangGraph/MCP。

---

## 2. 背景与决策记录

### 2.1 产品主线（实现文档，跨子项目）

```text
先排好计划 → 再执行计划 → 最后处理异常
```

完整愿景含：Multi-Agent 分析 → Strategy → SolverPolicy → Solver → Evaluation → 仿真 → 动态事件 → R0/R1/R2。  
**本规格只锁定第一子项目**；后续子项目另开规格。

### 2.2 已确认决策

| 决策项 | 结论 |
|---|---|
| 本轮子项目 | 参数化 `SchedulingStrategy`（非一次做完 Phase 0–8） |
| 落地深度 | 模型 + 评价闭环（软进分、硬校验淘汰） |
| NL → Strategy | LLM 生成 + 规则回退 |
| 硬约束范围 | 扩展集（含 skill / tooling）；缺数据用模拟并标记 |
| 软约束范围 | 扩展集；与 objectives 去双计 |
| 前端 | 轻量对接（非完整 Mode A/B/C） |
| 架构落法 | 独立 strategy 模块 + Feature Flag；验收后可删旧代码 |
| LLM 改算法 | 不做 |
| P0+P1 增强 | Structured Output repair/retry、Context Builder、策略 HITL、Trace、Guardrail、轻量 SolverPolicy、run 状态机、ToolSpec 可选字段扩展 |

### 2.3 与实现文档的差异（有意收敛）

1. 七 Agent Supervisor → **P2 下一子项目**，本轮用固定流水线替代协作分析输入（可由规则/LLM 直接产 Strategy）。  
2. 「不要一次删除旧 Agent」→ **并行 → 验收 → 删除**。  
3. 补强策略级 HITL（approve / reject / edit_and_approve），不仅落库确认。  
4. 强制 Context Builder，禁止把全量 BOM/甘特塞进 Prompt。  
5. 不上 LangGraph / 全面 MCP。

---

## 3. 架构

```text
用户 / 轻量 UI
        │
        ├─ 旧路径（过渡期保留）
        │    POST /api/agents/scheduling/run
        │
        └─ 新路径（本轮交付）
             POST /api/planning/strategy/generate
             POST /api/planning/strategy/validate
             POST /api/planning/strategy/hitl/*     # approve/reject/edit
             POST /api/planning/run                 # 可 WAITING_APPROVAL
             POST /api/planning/strategy/evaluate
                        │
                        ▼
              metaforge.strategy
              · models / presets / catalog
              · context_builder
              · generator（LLM + repair/retry + rule fallback）
              · guardrails
              · adapters
              · solver_policy（轻量）
              · evaluator
              · hitl / run_state / trace
                        │
          复用：Tool Registry、Session artifacts、SSE、
                compare_solvers、HITL persist、pytest
                        │
                        ▼
              Production Plan Package
```

### 3.1 边界原则

- LLM：理解、生成 Strategy、写推荐理由；**不算甘特、不写库、不改 Solver 源码**。  
- 确定性层：Solver、硬约束校验、KPI、落库。  
- 业务事实（订单/设备/物料/甘特）存领域存储与 Session artifacts；**不**当作 Agent Memory。  
- `PlanningRun` 状态存一次排产运行；Session Memory 仅多轮对话与用户偏好。

### 3.2 薄 Harness 分层（P1，不引入框架）

本轮不新建完整 AgentRuntime 平台，但 strategy 流水线按以下端口解耦，便于下轮 Supervisor 接入：

| 端口 | 职责 |
|---|---|
| Context | `context_builder` |
| Model I/O | generator structured output |
| Tool | `tools/planning/*` |
| State | `PlanningRun` + Session artifacts |
| Policy | guardrails + HITL |
| Evaluation | evaluator |
| Trace | strategy trace → SSE |

---

## 4. 数据模型

### 4.1 SchedulingStrategy

```text
strategy_id: str | None
base_template: str | None          # preset id
objectives: dict[str, float]
hard_constraints: list[Constraint]
soft_constraints: list[Constraint]
critical_orders: list[str]
machine_preferences: dict
machine_limits: dict
overtime_policy: dict | None
freeze_policy: dict | None
solver_preferences: dict | None    # 提示给轻量 SolverPolicy
generated_by: llm | rule_fallback | user | preset
explanation: str
provenance: {
  prompt_version?: str
  simulated_fields: list[str]
  source_refs?: list[str]
}
```

现有 6 模板（balanced / delivery / cost / balance_load / makespan / throughput）降为 **Preset**：只提供默认 `objectives`，可再叠加约束。

### 4.2 Objectives

至少支持现有：

- `makespan`
- `weighted_tardiness_total`
- `energy_cost`
- `machine_busy_cv`

本轮新增（进入 schema；无可靠度量时 evaluator 记录 `metric_unavailable`，不伪造）：

- `setup_changeover`
- `schedule_stability`

综合分仍遵循「越小越好」；软约束 penalty 并入总分前必须查 **去双计表**（见 4.5）。

### 4.3 Hard Constraints（扩展集）

| type | 含义 | 缺数据时 |
|---|---|---|
| `order_on_time` | 指定订单必须按期 | 需 job_id/due |
| `machine_unavailable` | 机台时段禁排 | 可模拟 downtime |
| `frozen_operations` | 冻结工序不可改 | 滚动重排场景 |
| `precedence` | 工序先后（结果校验/报告） | 问题定义已含则报告一致性 |
| `skill_required` | 人员技能 | **允许模拟** `source=simulated` |
| `tooling_exclusive` | 工装唯一占用 | **允许模拟** |

硬约束必须进入确定性 `guardrails` + `evaluator`，不允许只存在于 Prompt。

配置项：`STRATEGY_ALLOW_SIMULATED_CONSTRAINTS`（默认 `true`）。为 `false` 且硬约束数据不足时，`run` **fail-closed**。

### 4.4 Soft Constraints（扩展集）

| type | 含义 | 与 objectives 关系 |
|---|---|---|
| `reduce_changeover` | 少换型 | 可映射 `setup_changeover` 权重，勿双计 |
| `avoid_machine_overload` | 指定机台利用率上限偏好 | 独立 penalty |
| `load_balance` | 负载均衡偏好 | 与 `machine_busy_cv` 折叠 |
| `schedule_stability` | 少改原计划 | 与同名 objective 折叠 |
| `prefer_overtime` / `avoid_overtime` | 加班偏好 | 独立或进 overtime_policy |
| `prefer_outsourcing` / `avoid_outsourcing` | 外包偏好 | 独立 |
| `energy_shift_preference` | 能耗时段偏好 | 与 `energy_cost` 折叠 |

### 4.5 去双计规则

`catalog` 声明每条 soft 的 `folds_into_objective`。若已折叠，evaluator **只**通过 objective 计分，不再加独立 soft penalty。Trace 记录折叠决策。

### 4.6 SolverPolicy（轻量，P1）

```text
primary_solvers: list[str]
fallback_solver: str | None
time_budget_seconds: float
max_candidates: int          # 默认 2–3，不强跑 14
parameters: dict
reason: str
```

由规则 + `solver_preferences` + **Solver Capability Matrix** 生成，不是完整 Solver Agent。

Capability Matrix 至少字段：

- `supports_dynamic_weights`
- `supports_multiobjective_search`
- `supports_complex_hard_constraints`（多数为 false；本轮靠后置评价）
- `family`: rule | metaheuristic | rl

**RL（Q/DQN/PPO/Neuroevo）若 `supports_dynamic_weights=false`，不得被宣传为完全支持参数化策略**；可选为候选时必须在 Package 中记录 limitation。

### 4.7 EvaluationResult / Production Plan Package

```text
recommended_schedule_id
ranking: list[{schedule_id, score, hard_ok, soft_penalties, metrics}]
hard_violations: list
soft_penalties: list
tradeoff_analysis
recommendation_reason
alternatives: up to 2
kpi / critical_order_results / bottleneck_summary
failed_solvers: list
trace_id / run_id
```

全部候选 hard-illegal 时：`recommended_schedule_id = null`，返回违规聚合与放宽建议，**禁止**假装有合法最优。

### 4.8 PlanningRun 状态（P1）

```text
run_id
status: PENDING | RUNNING | WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED
stage: generate | hitl_strategy | solve | evaluate | package
strategy_draft / strategy_approved
candidate_schedules
evaluation
package
error / warnings
created_at / updated_at
```

支持：策略审批后 resume；不实现完整跨进程 durable workflow。不上 LangGraph。

---

## 5. 组件职责

| 组件 | 职责 | 非职责 |
|---|---|---|
| `presets` | 模板 → 默认 objectives | 最终策略 |
| `context_builder` | 按任务选订单/资源/约束摘要；token budget；压缩大 BOM/甘特 | 塞全量原始表 |
| `generator` | NL→Strategy；schema 校验；repair≤2；失败规则回退 | 算甘特 |
| `guardrails` | 校验约束引用的 job/machine 存在；禁止越权写计划字段 | 替代评价 |
| `adapters` | Strategy→weights / resource_config hints | 改 Solver 内核 |
| `solver_policy` | 选 solver 列表/预算/候选数 | 执行求解 |
| `evaluator` | 硬淘汰、软打分、排名、理由素材 | LLM 随意改名次 |
| `hitl` | 策略 approve/reject/edit_and_approve | 静默应用高风险策略 |
| `trace` | 结构化步骤写入 SSE | 另起一套日志系统 |

---

## 6. 数据流与 API

### 6.1 主链路

```text
输入(生产数据 + NL [+ 手动策略覆盖])
  → generate Strategy（Context Builder + LLM/规则）
  → guardrails.validate
  → HITL：WAITING_APPROVAL（可配置跳过：仅开发/评测）
  → approve | edit_and_approve | reject
  → solver_policy → compare_solvers（少量候选）
  → evaluate
  → Production Plan Package
  → （落库仍走现有 HITL confirm_token）
```

### 6.2 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/planning/strategy/generate` | NL → Strategy |
| POST | `/api/planning/strategy/validate` | schema + guardrails |
| POST | `/api/planning/strategy/evaluate` | 候选 + Strategy → EvaluationResult |
| POST | `/api/planning/run` | 一键流水线；可返回 WAITING_APPROVAL |
| POST | `/api/planning/runs/{run_id}/strategy/approve` | 批准草稿策略 |
| POST | `/api/planning/runs/{run_id}/strategy/reject` | 拒绝 |
| POST | `/api/planning/runs/{run_id}/strategy/edit_and_approve` | 编辑后批准 |
| GET | `/api/planning/runs/{run_id}` | 查询状态 |
| GET | `/api/planning/strategy/presets` | 6 Preset |
| GET | `/api/planning/constraints/catalog` | 硬/软类型与去双计声明 |

Feature Flag：`PLANNING_STRATEGY_V1=1`（或等价配置）启用新路由；关闭时行为与现网一致。

旧 API 过渡期保留；删除门槛见 §11。

### 6.3 Tool 挂载（P0 + ToolSpec 扩展 P1）

新 Tool（白名单，供后续 Agent/流水线调用）：

- `planning.strategy_generate`
- `planning.strategy_validate`
- `planning.strategy_evaluate`
- `planning.run`（或拆成 solve_candidates）

`ToolSpec` 扩展**可选**字段（旧 Tool 不强制填齐）：

```text
timeout_seconds, retry_policy, risk_level, idempotency_key_fields, permission
```

约定：`planning.*` 中 generate=`risk_level=ask`（需策略 HITL）；evaluate=`allow`；任何写库仍走现有 `data.propose_persist` / `confirm_persist`。

LLM **不**直接访问 MongoDB，**不**直接算甘特。

---

## 7. Context Engineering

`context_builder.build_for_strategy_generation(...)` 输出固定预算包：

1. 用户目标原文（截断上限）  
2. 订单摘要：id / due / priority / customer（Top-N + 临期）  
3. 资源摘要：机台负荷粗估、已知 downtime  
4. 已有约束/冻结（若有）  
5. Preset 目录短表  
6. 约束 catalog 短表（类型名 + 一句话）  

大甘特、完整 BOM、完整 Tool Result **禁止**原文入模；需要时只提供结构化摘要（条数、缺口、瓶颈机台）。

---

## 8. Structured Output 与失败处理

1. LLM 必须返回 JSON，对照 `SchedulingStrategy` schema 校验。  
2. 失败则 **repair**（带校验错误反馈）最多 2 次。  
3. 仍失败 → **rule_fallback**（关键词/模板 + 可解析的 critical order 规则），`generated_by=rule_fallback`，附 warning。  
4. Schema 失败不得进入求解。  
5. 单候选 Solver 异常：记入 `failed_solvers`，继续其他候选。  
6. 全员 hard-illegal：空推荐 + 违规聚合 + 放宽建议。

Stop conditions（本轮固定流水线，非 ReAct）：

- 阶段成功完成；或  
- 不可恢复错误；或  
- HITL reject；或  
- 超时（generate / solve budget）。

ReAct 仅复用现有能力作**可选**诊断，不作为 `/api/planning/run` 默认控制环。

---

## 9. HITL

### 9.1 策略 HITL（本轮新增）

生成后默认进入 `WAITING_APPROVAL`：

- **approve**：用草稿策略继续 solve→evaluate  
- **reject**：run=`CANCELLED` / `FAILED`（带原因）  
- **edit_and_approve**：客户端提交完整 Strategy（再走 validate/guardrails）后继续  

评测环境可通过 `skip_strategy_hitl=true` 跳过（仅测试）。

### 9.2 计划落库 HITL（复用）

推荐方案写库继续 `propose_persist` / `confirm_persist`；高风险写操作不得绕过。

---

## 10. Guardrail / Security

- Prompt Injection：用户 NL 与系统指令隔离；约束类型必须 ∈ catalog 白名单。  
- Tool 参数 JSON Schema 校验。  
- LLM 产生的 hard constraint：**guardrails** 校验实体存在性与合法时间窗后，才进入 evaluator；**不能**因 Prompt 文案直接修改真实生产计划或库存。  
- `risk_level=ask` 的 Tool 必须 HITL。  
- 模拟数据字段写入 `provenance.simulated_fields`，Package 与 UI 可见。

---

## 11. 旧代码退役门槛

同时满足后方可删除已替代旧路径代码：

1. 新 API 覆盖原 scheduling 主路径能力（模板排程、NL 策略、多候选、落库 HITL）。  
2. §12 黄金场景与回归通过。  
3. 前端默认入口切到新路径。  
4. 文档与 `智能体功能清单` / 进度文档更新。  

删除对象包括但不限于：仅服务于旧 weights 模板路径且无其他引用的适配层；过时 API 别名。共享 Solver / Session / Tool 基础设施**保留**。

---

## 12. 评测与测试

### 12.1 双层指标

**Agent / 流水线层**

- structured output success rate  
- repair count / fallback rate  
- tool success / timeout  
- strategy HITL completion  
- task completion（拿到合法 Package 或明确失败）

**排产业务层**

- hard constraint violation（recommended 必须为 0）  
- 关键订单按期率  
- weighted_tardiness / makespan / setup_changeover / load / energy / stability（可得则报）

### 12.2 黄金场景（本轮至少）

1. **Case 模板兼容**：Preset delivery 与旧 weights 行为可对照。  
2. **Case NL 重点客户**：保证 A 按期；硬约束 `order_on_time`；推荐方案不违法。  
3. **Case 参数化优于裸模板**：同一订单池，带 critical/soft 的策略在业务指标上不劣于仅模板（断言写清可比指标）。  
4. **Case 全员非法**：构造不可行硬约束 → 无 recommended。  
5. **Case 模拟技能/工装**：`simulated_fields` 非空且校验仍执行。  
6. **Case LLM 失败回退**：mock LLM 错误 → rule_fallback 仍可 run。  

实现文档中的 Multi-Agent 并行分析 / 仿真 / R0R1R2 黄金场景 → **归 P2 子项目**，本规格不阻塞。

### 12.3 测试文件（建议）

```text
tests/strategy/test_presets.py
tests/strategy/test_generator_fallback.py
tests/strategy/test_guardrails.py
tests/strategy/test_evaluator_hard_soft.py
tests/strategy/test_planning_api.py
tests/strategy/test_golden_critical_order.py
```

---

## 13. Observability / Trace

每次 `/api/planning/run` 记录：

```text
run_id, stage
model, prompt_version, token_usage, latency
strategy (hash), generated_by, repair/fallback
solver_policy, random_seed, candidate ids
evaluation ranking, hard_violations, recommendation_reason
```

复用并扩展 `orchestrator/execution_trace.py` + SSE；前端展示简化轨迹（阶段卡片），不要求原始 Prompt 全量曝光。

---

## 14. 前端（轻量）

在现有排产相关页增加：

1. 自然语言目标输入  
2. Strategy JSON 预览（含 simulated 标记）  
3. 策略 HITL：批准 / 拒绝 / 编辑后批准  
4. 推荐结果：KPI、硬约束违规、软惩罚、推荐理由、备选  

**不做：** 完整 Mode A/B/C 大改版、全新结果信息架构重构（归后续）。

---

## 15. 文件级修改计划

### 15.1 新建

```text
src/metaforge/strategy/__init__.py
src/metaforge/strategy/models.py
src/metaforge/strategy/presets.py
src/metaforge/strategy/catalog.py
src/metaforge/strategy/context_builder.py
src/metaforge/strategy/generator.py
src/metaforge/strategy/guardrails.py
src/metaforge/strategy/adapters.py
src/metaforge/strategy/solver_policy.py
src/metaforge/strategy/capability_matrix.py
src/metaforge/strategy/evaluator.py
src/metaforge/strategy/hitl.py
src/metaforge/strategy/run_state.py
src/metaforge/strategy/trace.py
src/metaforge/tools/planning/__init__.py
src/metaforge/tools/planning/strategy_generate.py
src/metaforge/tools/planning/strategy_validate.py
src/metaforge/tools/planning/strategy_evaluate.py
src/metaforge/tools/planning/run.py
tests/strategy/...
```

API 路由挂载点：与现有 FastAPI 应用一致的入口文件（保持项目惯例）。

### 15.2 修改

```text
src/metaforge/tools/base.py          # ToolSpec 可选字段
src/metaforge/utils/solver_registry.py
src/metaforge/utils/objectives.py
src/metaforge/utils/multiobjective_eval.py
src/metaforge/orchestrator/execution_trace.py
src/metaforge/orchestrator/stream.py
src/metaforge/orchestrator/session.py
frontend 排产相关视图（轻量）
```

### 15.3 不动

- 各 Solver 搜索内核实现  
- 全面 LangGraph / MCP  
- 七 Agent Supervisor 一次落地  
- 真实 MES/IoT/复杂 RBAC  

---

## 16. 后续子项目（本规格之外）

| 子项目 | 内容 |
|---|---|
| S2 Multi-Agent 协作 | Planning Supervisor + Order/Constraint/Resource → Strategy→Solver→Evaluation；AgentTask/Result；并行分析 |
| S3 前端三模式 | Quick Template / Parameter / AI Strategy + 完整结果页 |
| S4 仿真与动态重排 | 推荐计划 → Production Simulator；自动扰动；R0/R1/R2 强化 |
| S5（条件） | 仅当自研 run 状态机明显不足时，评估 LangGraph **Adapter**；外部系统对接时再评估 MCP Adapter |

---

## 17. 验收标准（本子项目）

1. 可用 Preset 或 NL 生成合法 `SchedulingStrategy`（LLM 或回退）。  
2. 策略 HITL 三种动作可用。  
3. `/api/planning/run` 产出 Package：推荐（或明确无推荐）、KPI、违规、理由。  
4. recommended 方案 hard violation = 0。  
5. 模拟约束可见且可关闭（fail-closed）。  
6. RL 能力限制在 Matrix/Package 中诚实暴露。  
7. SSE 可见策略链路关键阶段。  
8. §12 黄金测试通过。  
9. 旧路径仍可运行，直到 §11 退役。  

面试可回答要点（本设计直接支撑）：

- 为何策略参数化而不是 LLM 改代码 / 直接出甘特  
- Agent/流水线如何与 Tool、State、HITL 协作  
- Structured Output 失败怎么办  
- 为何现在不用 LangGraph、何时才考虑  
- 如何评测「比固定模板更有效」  

---

## 18. 规格自检记录

| 检查项 | 结果 |
|---|---|
| 占位符 / TODO | 无；P2 以「后续子项目」列出而非待定实现 |
| 内部一致性 | 深度 B、可删旧代码、HITL、不上 LangGraph 全文一致 |
| 范围 | 单子项目可覆盖一个实现计划；七 Agent/仿真已外提 |
| 模糊性 | 模拟开关、去双计、RL 能力、HITL 跳过条件已选定默认 |

---

## 19. 参考

- 实现需求原文：`MetaForge_Intelligent_Scheduling_MultiAgent_Implementation.md`  
- 现行排程入口与模板：`src/metaforge/agent/scheduling_agent.py`  
- Tool 基类：`src/metaforge/tools/base.py`  
- 多目标：`src/metaforge/utils/objectives.py`  
