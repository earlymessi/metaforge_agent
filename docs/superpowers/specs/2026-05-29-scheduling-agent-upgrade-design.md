# Scheduling Agent 架构升级（Plan-and-Solve + 细粒度意图）

> **版本**：2026-05-29  
> **状态**：设计已定稿（待实施）  
> **父文档**：[`2026-05-29-llm-scheduling-design.md`](2026-05-29-llm-scheduling-design.md)  
> **关联**：[`2026-05-29-mes-multi-agent-design.md`](2026-05-29-mes-multi-agent-design.md)  
> **原则**：渐进式、非破坏性；向后兼容第一

---

## 1. 目标

在保留现有 Plan-and-Solve 两阶段执行、三层解析优先级（显式覆盖 > LLM > 规则回退）的前提下，升级 scheduling Agent：

1. **修复「快速」与指定算法冲突**（第一优先级）
2. **细粒度意图分类 + 上下文管理 + 动态 Plan**（第二优先级）
3. **LLM 上下文感知 + confidence 字段**（第三优先级）

**不做：**

- 修改 `SOLVER_REGISTRY` 与 5 套策略模板定义
- 修改 `scheduling.run` 与 `finalize` 排程结果汇总核心逻辑
- 修改 UI 跳转格式（成功排程仍 `ui_action → /reports`）
- 引入新依赖（Redis 等；ContextManager 先用内存）

---

## 2. 已确认决策

| 问题 | 决策 |
|------|------|
| 架构方案 | **方案 1**：`build_rule_plan` 预解析 + 动态 Plan；`parse_intent` Tool 复用同一解析函数 |
| CLARIFICATION 交互 | **A 阻塞式**：本次不跑排程，返回澄清问题；下一条消息在同 session 续答后执行 |
| 「快速 + 指定算法」 | 保留用户指定 solvers，设 `is_fast_mode=True`，提高 `weights.makespan` |
| 「快速 + 未指定算法」 | 对比所有非 RL 算法（`family ∈ {rule, metaheuristic}`），上限 **6 个**，给出推荐 |
| 快速无指定算法对比上限 | **6 个** solver（按 registry 顺序：rule 优先，再 metaheuristic） |
| Context 持久化 | 内存 `dict[session_id]`；Orchestrator `session_id` 为主键，无 session 用 `"default"` |

---

## 3. 现状与路径映射

用户描述路径与实际代码对照：

| 描述 | 实际路径 |
|------|----------|
| Agent 入口 `build_plan/finalize` | `src/metaforge/agents/scheduling.py` |
| 意图解析入口 | `src/metaforge/scheduling/resolve_intent.py` |
| 规则解析核心 | `src/metaforge/agent/scheduling_agent.py` |
| LLM 提示词 | `src/metaforge/orchestrator/llm/prompts.py` |
| LLM 解析校验 | `src/metaforge/orchestrator/llm/parsers.py` |

**已知缺陷**（`scheduling_agent.py:160-162`）：

```python
if any(h in text for h in _FAST_HINTS):
    matched_solvers = ["spt"]  # 无条件覆盖，与「遗传算法快速排」冲突
```

现有测试 `test_agent_parse_fast_spt` 固化了旧行为，实施时需更新。

---

## 4. 架构总览

```text
用户消息 + session_id + params（显式覆盖）
        │
        ▼
ContextManager.get(session_id)  ──► 若有 pending_clarification → 合并续答
        │
        ▼
resolve_schedule_intent()  【五步流程，见 §5】
        │
        ├── intent_type = CLARIFICATION ──► 写 pending，不跑 run
        ├── intent_type = LIST_* / HELP ──► 只读/写 context
        └── intent_type = RUN_* / COMPARE_* ──► 正常排程链
        │
        ▼
SchedulingAgentRunner.build_rule_plan()
        │  预解析结果缓存至 params["_pre_resolved"]
        ▼
动态 PlanStep 列表（见 §7）
        │
        ▼
Tool 执行（parse_intent / run / list_catalog / ask_clarification）
        │
        ▼
finalize()  【仅开头增加 CLARIFICATION 分支，§8】
        │
        ▼
ContextManager.save(session_id, updated_context)
```

**向后兼容：**

- 旧 API 只传 `message/solvers/weights` → interpretation 旧字段不变
- `skip_parse=true` → 仍跳过 parse，直接 `run`
- LLM 失败 → 仍 `planner: "rule_fallback"`

---

## 5. 五步解析流程

`resolve_schedule_intent(params, extras, benchmark_file, session_id=None)`：

### Step 0：澄清续答

若 `ContextManager.get_pending(session_id)` 存在：

- 将 `pending.original_message` + 用户新消息合并为完整意图
- 重新走 Step 1–4
- 成功后 `clear_pending(session_id)`

### Step 1：高置信规则拦截（≥ 0.95）

| 模式 | intent_type | 说明 |
|------|-------------|------|
| `有哪些算法/策略/求解器` | `LIST_SOLVERS` | 替代 `build_plan` 硬编码关键词 |
| `\b(ft\|la)\d{2}\b` + 跑算例 | `RUN_BENCHMARK` | 保留现有 benchmark 逻辑 |
| `is_plans_management_message` | 短路 | 返回提示，不调用 GLM |
| 显式 `params.intent_type` | 直接使用 | API 兼容 |

### Step 2：LLM 深度解析

条件：`llm_enabled()` 且 `use_llm != false` 且 message 非空。

注入 Context：

```json
{
  "last_solvers": ["ga", "ts"],
  "last_strategy_id": "delivery",
  "default_strategy_id": "balanced",
  "enforce_material": true
}
```

要求 LLM 输出 `confidence`（0–1）、`intent_type`、`is_fast_mode`。

### Step 3：规则校验与修正

- 过滤无效 solver / strategy_id（现有 `parse_scheduling` 逻辑）
- **快速修正**：若 `is_fast_mode` 且 solvers 非空 → 禁止替换 solvers
- 若 LLM 违反快速规则 → 回退规则层 `_match_solvers` 结果

### Step 4：置信度评估

| 区间 | 行为 |
|------|------|
| ≥ 0.7 | 返回完整 interpretation |
| 0.4 – 0.7 | `intent_type=CLARIFICATION`；生成 `clarification_question`；`set_pending`；**不跑排程** |
| < 0.4 | 增强规则 `SchedulingAgent.parse()` + 重新评估 |

**置信度来源：**

- 规则多关键词命中：0.95+
- LLM `confidence` 字段：采用，校验后 ±0.1
- 纯规则单算法明确：0.75
- 纯规则模糊：0.55

### Step 5：显式参数覆盖 + 上下文回写

`_apply_explicit_overrides(data, params)`（现有逻辑，最后执行）。

`ContextManager.update(session_id, last_solvers, last_strategy_id, ...)`。

---

## 6. 数据模型

### 6.1 ScheduleIntentType（`scheduling/intent_types.py`）

```python
class ScheduleIntentType(str, Enum):
    RUN_SCHEDULE = "RUN_SCHEDULE"
    COMPARE_SOLVERS = "COMPARE_SOLVERS"
    RUN_BENCHMARK = "RUN_BENCHMARK"
    LIST_SOLVERS = "LIST_SOLVERS"
    LIST_STRATEGIES = "LIST_STRATEGIES"
    GET_LAST_RESULT = "GET_LAST_RESULT"
    SET_DEFAULT_STRATEGY = "SET_DEFAULT_STRATEGY"
    SET_DEFAULT_SOLVER = "SET_DEFAULT_SOLVER"
    TOGGLE_MATERIAL = "TOGGLE_MATERIAL"
    CLARIFICATION = "CLARIFICATION"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"
```

常量：

```python
CONFIDENCE_HIGH = 0.95
CONFIDENCE_EXECUTE = 0.7
CONFIDENCE_CLARIFY = 0.4
FAST_MAKESPAN_BOOST = 1.5
FAST_COMPARE_MAX_SOLVERS = 6
RL_EXCLUDED_FAMILIES = frozenset({"rl"})
```

### 6.2 interpretation 扩展字段（只增不改）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `intent_type` | str | `RUN_SCHEDULE` | ScheduleIntentType 值 |
| `confidence` | float | 0.7 | 0–1 |
| `is_fast_mode` | bool | False | 快速模式标记 |
| `clarification_question` | str \| null | null | CLARIFICATION 时的问题 |
| `clarification_context` | dict \| null | null | 待合并的部分意图 |
| `planner` | str | — | 现有：`rule` / `llm` / `rule_fallback` |

`ScheduleIntent` dataclass 同步增加上述字段（`scheduling_agent.py`）。

### 6.3 ScheduleContext（`scheduling/context.py`）

```python
@dataclass
class ScheduleContext:
    last_solvers: List[str] = field(default_factory=list)
    last_strategy_id: str = "balanced"
    default_solvers: List[str] = field(default_factory=list)
    default_strategy_id: str = "balanced"
    enforce_material: bool = True
    last_run_summary: str = ""
    pending_clarification: Optional[Dict[str, Any]] = None
```

```python
class ContextManager:
    _store: Dict[str, ScheduleContext]

    def get(session_id: str) -> ScheduleContext
    def save(session_id: str, ctx: ScheduleContext) -> None
    def set_pending(session_id, original_message, partial_intent, question) -> None
    def clear_pending(session_id) -> None
    def merge_clarification_reply(session_id, reply: str) -> str  # 合并消息
```

---

## 7. 「快速」逻辑（第一优先级）

### 7.1 用户明确指定算法

```
输入: "用遗传算法快速排一下"
输出:
  solvers = ["ga"]
  is_fast_mode = True
  strategy_id = "balanced"  # 无策略关键词时默认
  weights.makespan *= FAST_MAKESPAN_BOOST (1.5)
```

**绝不**将 solvers 替换为 `["spt"]`。

### 7.2 仅「快速」、未指定算法

```
输入: "快速先出个结果"
输出:
  solvers = 非 RL 算法，最多 6 个（rule 优先，再 metaheuristic）
  is_fast_mode = True
  weights.makespan *= 1.5
  summary 注明「快速对比模式，已排除 RL 实验算法」
```

### 7.3 澄清追问（CLARIFICATION 时可问）

当 `is_fast_mode=True` 且策略不明确，澄清问题可包含：

- 「除完工时间外，是否需要考虑能耗成本？」
- 「是否启用物料约束？」

---

## 8. 动态 Plan 映射

`SchedulingAgentRunner.build_rule_plan()` 流程：

1. 从 `request.context.get("session_id")` 取 session_id
2. 调用 `resolve_schedule_intent(..., session_id=session_id)`
3. 缓存至 `request.params["_pre_resolved"]`
4. 按 `intent_type` 返回 PlanStep 列表

| intent_type | PlanStep 链 |
|-------------|-------------|
| `LIST_SOLVERS` / `LIST_STRATEGIES` | `[list_catalog]` |
| `CLARIFICATION` / `HELP` / `UNKNOWN`（低置信） | `[ask_clarification]` |
| `RUN_SCHEDULE` / `COMPARE_SOLVERS` / `RUN_BENCHMARK` | `[parse_intent, run]` |
| `RUN_SCHEDULE` + `skip_parse` | `[run]` |
| `GET_LAST_RESULT` | `[ask_clarification]`（只读 context 摘要，不跑 run） |
| `SET_DEFAULT_STRATEGY` / `SET_DEFAULT_SOLVER` / `TOGGLE_MATERIAL` | `[ask_clarification]`（写 context + 确认文案） |

`parse_intent` Tool：若 params 含 `_pre_resolved`，直接写入 artifacts，**跳过重复 LLM 调用**。

### 8.1 新增 Tool：`scheduling.ask_clarification`

```python
# 输入: question, clarification_context, intent_type
# 输出: artifacts["clarification"] = { question, options?, context }
# 不修改 schedule_results
```

注册至 `allowed_tools` 与 `tools/scheduling/__init__.py`。

---

## 9. CLARIFICATION 阻塞流程（A）

```text
Turn 1:
  用户: "帮我排一下"
  resolve → confidence=0.45, intent_type=CLARIFICATION
  question: "请问更关注交期、产能还是成本？是否启用物料约束？"
  ContextManager.set_pending(session_id, ...)
  build_plan → [ask_clarification]
  finalize → status="pending_clarification", summary_zh=question, 无 ui_action

Turn 2:
  用户: "交付优先，不考虑物料"
  resolve → merge pending → confidence=0.85, intent_type=RUN_SCHEDULE
  build_plan → [parse_intent, run]
  finalize → 原有排程汇总 + ui_action /reports
  ContextManager.clear_pending(session_id)
```

### finalize 改动（最小）

在 `SchedulingAgentRunner.finalize()` **开头**增加：

```python
clar = ctx.artifacts.get("clarification")
if clar and clar.get("question"):
    return AgentResponse(
        status="pending_clarification",
        summary_zh=clar["question"],
        ...
        # 无 ui_action
    )
```

其后逻辑不变。

---

## 10. LLM 增强（第三优先级）

### 10.1 `scheduling_system()` 增补

- 注入用户 Context（last_solvers、default_strategy）
- 算法 family 说明：rule / metaheuristic / rl（rl 默认不参与快速对比）
- **快速模式规则**（与 §7 一致）
- 输出字段增加：`intent_type`、`confidence`、`is_fast_mode`、`clarification_question`
- 示例：「用遗传算法快速排一下」→ `solvers=["ga"], is_fast_mode=true`

### 10.2 `parse_scheduling()` 增补

- 校验 `confidence` clamp 到 [0, 1]
- 校验 `intent_type` 枚举，非法 → `RUN_SCHEDULE`
- 传递 `is_fast_mode`；若 true 且 weights 存在 → makespan boost
- 保留现有 solver/strategy 白名单校验

---

## 11. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scheduling/intent_types.py` | **新增** | 枚举 + 常量 |
| `scheduling/context.py` | **新增** | ScheduleContext + ContextManager |
| `scheduling/resolve_intent.py` | **修改** | 五步流程 + session_id |
| `agent/scheduling_agent.py` | **修改** | 快速逻辑、ScheduleIntent 扩展、规则置信度 |
| `agents/scheduling.py` | **修改** | 动态 build_plan、finalize CLARIFICATION 分支 |
| `tools/scheduling/parse_intent.py` | **修改** | 扩展 schema、`_pre_resolved` 短路 |
| `tools/scheduling/ask_clarification.py` | **新增** | 澄清 Tool |
| `tools/scheduling/__init__.py` | **修改** | 注册新 Tool |
| `orchestrator/llm/prompts.py` | **修改** | scheduling_system/user |
| `orchestrator/llm/parsers.py` | **修改** | parse_scheduling 新字段 |
| `scheduling/llm_intent.py` | **修改** | 透传 session context |
| `tests/test_scheduling_agent.py` | **修改** | 更新 fast 用例 + 新增 ga+fast |
| `tests/test_scheduling_resolve_v2.py` | **新增** | 澄清、动态 plan、confidence |

**不修改：**

- `tools/scheduling/run.py`
- `agents/scheduling.py` finalize 排程结果汇总段（§9 除外）
- `utils/solver_registry.py` 策略模板

---

## 12. 测试计划

| 用例 | 期望 |
|------|------|
| `用遗传算法快速排一下` | `solvers=["ga"]`, `is_fast_mode=True`, `strategy_id="balanced"` |
| `快速先出个结果` | 非 RL solvers ≤6, `is_fast_mode=True`, 不含 rl |
| `用禁忌搜索，交付优先` | `solvers` 含 ts, `strategy_id=delivery`, `is_fast_mode=False` |
| `帮我排一下`（无历史） | `CLARIFICATION`, 不执行 run, `status=pending_clarification` |
| pending + `交付优先，不考虑物料` | `RUN_SCHEDULE`, `delivery`, `enforce_material=False` |
| `有哪些算法` | `LIST_SOLVERS`, 只 list_catalog |
| `params.skip_parse=true` + solvers | 直接 run，行为与现有一致 |
| LLM 失败 | `planner=rule_fallback`, 仍可排程 |
| 旧 interpretation 消费者 | 只读 solvers/weights 不受影响 |

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 快速对比 6 算法耗时长 | 上限 6；summary 提示「快速对比模式」 |
| 预解析 + parse_intent 重复 | `_pre_resolved` 缓存短路 |
| pending 跨 session 丢失 | 与 Orchestrator session 绑定；memory store 1h TTL 一致 |
| 旧测试失败 | 更新 `test_agent_parse_fast_spt` 预期 |

---

## 14. 实施顺序

1. `intent_types.py` + `context.py`（无行为变化）
2. `scheduling_agent.py` 快速逻辑修复 + 新字段
3. `resolve_intent.py` 五步流程
4. `prompts.py` + `parsers.py` LLM 增强
5. `ask_clarification` Tool + `parse_intent` 扩展
6. `agents/scheduling.py` 动态 plan + finalize 分支
7. 测试更新与新增

---

## 15. Spec 自检

- [x] 无 TBD / TODO 占位
- [x] CLARIFICATION=A 与动态 Plan、ContextManager 一致
- [x] 快速逻辑与测试用例一致
- [x] 不改 run/finalize 核心 / registry / 策略模板
- [x] 范围可单份 implementation plan 覆盖
