# MetaForge Agent 能力评测方案（GLM 联调 + 端到端执行）

> **文档索引**：[`README.md`](README.md) · 功能对照：[`智能体功能清单.md`](智能体功能清单.md)  
> **版本**：2026-05-31 v1  
> **目标读者**：后续实现自动化测试的开发者  
> **范围**：6 个业务 Agent（`scheduling` / `events` / `kitting` / `commitment` / `whatif` / `plans`）在 **GLM 主路径**下的路由、规划、解析与真执行能力

---

## 1. 评测目标

| 层级 | 代号 | 测什么 | 入口 | 是否调 GLM | 是否跑 Tool |
|------|------|--------|------|------------|-------------|
| **L2** | Preview | 自然语言 → 正确 Agent → 合理 Tool 链 → Parse 结构 | `build_orchestrator_preview` / `/api/orchestrator/preview` | ✅ | ❌ |
| **L3** | Exec | 完整 Agent.run → artifacts 契约 → 状态码 → 会话/HITL | `/api/orchestrator/run` 或 `/api/agents/{id}/run` | ✅（路由+Plan+Parse） | ✅ |

**不在本方案内**（已有离线层，CI 必跑）：

- 规则路由 20 条话术（`tests/test_router_phrases.py`）
- 纯规则 Plan 链（`agent_benchmark.yaml` 中 `router_mode: explicit`）
- 270+ pytest 单元/集成回归

---

## 2. 环境与前置条件

### 2.1 必需

```powershell
# 项目根目录
copy .env.example .env
# 填入 ZHIPU_API_KEY

$env:LLM_ENABLED = "1"
$env:LLM_ROUTER = "glm"
$env:LLM_FALLBACK = "rule"
$env:LLM_PLAN_ENABLED = "1"
$env:LLM_PLAN_AGENTS = "scheduling,events,kitting,commitment,whatif"
$env:LLM_SUMMARIZE_ENABLED = "1"
$env:SESSION_STORE = "memory"   # L3 默认；落库/HITL 用例可切 mongo
```

### 2.2 可选模式（分档跑）

| 环境变量 | 含义 |
|----------|------|
| `RUN_GLM_PREVIEW=1` | 跑 L2 全量 |
| `RUN_GLM_EXEC=1` | 跑 L3 全量 |
| `RUN_GLM_REACT=1` | L2/L3 附加 ReAct 模式（scheduling/events） |
| `RUN_GLM_REFLECT=1` | ReAct + Reflect |
| `AGENT_E2E_MONGO=1` | plans 落库、HITL confirm 用真实 Mongo |
| `AGENT_E2E_SLOW=1` | 含全量算法对比、大算例 ft10 等慢用例 |

### 2.3 依赖服务

| 用例类型 | MongoDB | 说明 |
|----------|---------|------|
| L2 Preview | 否 | 纯内存工单 |
| L3 排程/重排/齐套/交期/whatif | 否 | `custom_data` 注入 |
| L3 plans CRUD | 推荐 | `AGENT_E2E_MONGO=1` 或 mock collection |
| L3 HITL 落库 | 推荐 | `propose_persist` → `confirm_persist` |

### 2.4 记录基线信息（报告必含）

每次跑完写入 JSON 报告：

- `router_build_id`（来自 `/api/llm/status`）
- `ZHIPU_MODEL`
- `LLM_PLAN_AGENTS` / `LLM_REACT_ENABLED`
- `generated_at` UTC
- 每条用例：`elapsed_ms`、`router`、`plan_planner`、`tools[]`、`status`、`ok`

---

## 3. 评测维度与指标

### 3.1 L2 Preview 维度

| 维度 ID | 检查项 | 通过条件 |
|---------|--------|----------|
| **R1 路由** | `agent_id` | 等于 `expect_agent` |
| **R2 意图** | `route.intent` | 等于 `expect_intent`（若指定） |
| **R3 路由来源** | `route.router` | 主路径为 `llm`（guard 覆盖时为 `rule_override`，需 `expect_router` 显式声明） |
| **P1 Tool 链** | plan steps | `expect_tools` 全部出现（顺序可选 `expect_tools_ordered: true`） |
| **P2 白名单** | tools ⊆ allowed_tools | 对照 `registry_meta.AGENT_REGISTRY` |
| **P3 规划来源** | `plan_planner` | 期望 `llm`（events 规则链可为 `rule`，需显式声明） |
| **X1 解析** | parse phase | `expect_parse_fields` 子集匹配（如 `solvers`、`event_type`） |
| **X2 澄清** | 模糊话术 | `expect_status: pending_clarification` 或 plan 含 `scheduling.ask_clarification` |
| **T1 时延** | `elapsed_ms` | ≤ `max_ms`（默认 Preview 单条 90s） |

### 3.2 L3 Exec 维度

| 维度 ID | 检查项 | 通过条件 |
|---------|--------|----------|
| **E1 状态** | `status` | ∈ `expect_status`（默认 `success`） |
| **E2 Agent** | `agent_id` | 等于 `expect_agent` |
| **E3 步骤** | `plan[].status` | 无 `failed`（除非 `expect_failed_step`） |
| **E4 Artifacts** | 键存在 | 见各 Agent 契约表（§6） |
| **E5 数值** | 指标范围 | 如 `makespan > 0`、`impact_report.scenarios` 含 R0/R1/R2 |
| **E6 摘要** | `summary_zh` | 非空（`LLM_SUMMARIZE_ENABLED=1` 时） |
| **E7 会话** | `session_id` | 多轮用例能 `requires_session_from` 续跑 |
| **E8 HITL** | `pending_confirm` | 落库提议含 `confirm_token` |
| **T2 时延** | `elapsed_ms` | ≤ `max_ms`（默认 Exec 单条 180s；慢用例 300s） |

### 3.3 汇总指标（报告顶部）

```
路由命中率     = R1 通过数 / R1 总数
Plan 命中率    = P1 通过数 / P1 总数
Exec 成功率     = E1 通过数 / E1 总数
按 Agent 通过率  = 分 scheduling/events/… 统计
按 Tag 通过率    = route_guard / multi_turn / hitl / adversarial
P95 延迟        = elapsed_ms 分位数
```

### 3.4 发版验收门槛（建议）

| 档位 | 条件 |
|------|------|
| **Preview 发版** | 路由命中率 ≥ 95%；Plan 命中率 ≥ 90%；0 条 P2 白名单违规 |
| **Exec 发版** | Exec 成功率 ≥ 90%；核心 Agent（scheduling/events）≥ 95%；HITL 链路 100% |
| **ReAct 试用** | 在 Preview 门槛上，ReAct 模式路由不降于 90% |

---

## 4. 测试数据 Fixture

统一放在 `tests/data/agent_e2e/`（自动化实现时创建）。

### 4.1 `fixtures/min_jobs.json`（默认 3 工单）

与现有 `glm_smoke.DEFAULT_JOBS` 一致：工单A / 订单106 / 工单B，含 `due_date`、`priority`、2 工序。

### 4.2 `fixtures/mes_baseline.json`（events 重排）

```json
{
  "sim_time": 5.0,
  "baseline_gantt": [ "...4 segments..." ],
  "schedule_results": { "spt": { "gantt_data": [], "metrics": { "makespan": 14.0 } } }
}
```

用于：故障/插单/改交期 L3；通过 `context.production_execution` 或先调 `/api/execution/start` 注入。

### 4.3 `fixtures/bom_jobs.json`（kitting）

含 `materials` / BOM 字段的 2～3 工单，覆盖缺料与齐套两种路径。

### 4.4 `fixtures/plans_seed.json`（plans L3）

预置计划名 `E2E-试产01`、空 jobs 计划、含排程结果计划（HITL 覆盖场景）。

### 4.5 算例

| 文件 | 用途 | 档位 |
|------|------|------|
| `data/benchmarks/ft06.txt` | scheduling 标准算例 | 默认 |
| `data/benchmarks/ft10.txt` | 大算例 | `AGENT_E2E_SLOW=1` |

---

## 5. L2：GLM Preview 用例矩阵

> **合计：约 58 条**（含 12 条路由对抗）。现有 `glm_smoke.py` 覆盖 21 条，本方案为超集。

### 5.1 scheduling（12 条）

| ID | 话术 | expect_agent | expect_tools（包含） | 备注 |
|----|------|--------------|----------------------|------|
| L2-SCH-01 | 用禁忌搜索，交付优先排程 | scheduling | parse_intent, run | 算法+策略 |
| L2-SCH-02 | 对比一下遗传算法和模拟退火 | scheduling | parse_intent, run | 多算法 |
| L2-SCH-03 | 跑一下 ft06 算例，吞吐优先 | scheduling | parse_intent, run | expect_parse: benchmark_file |
| L2-SCH-04 | 快速先出个结果 | scheduling | parse_intent, run | fast 模式 |
| L2-SCH-05 | 帮我排一下 | scheduling | ask_clarification **或** parse_intent | 模糊；允许澄清 |
| L2-SCH-06 | 按交期优先，全量对比所有算法 | scheduling | parse_intent, run | slow tag |
| L2-SCH-07 | 用 SPT 排程，不考虑物料 | scheduling | parse_intent, run | material=false |
| L2-SCH-08 | 有哪些算法可以用？ | scheduling | list_catalog | 目录查询 |
| L2-SCH-09 | 把这个计划排程并保存落库 | scheduling | load_plan?, run, assess?, propose_persist | 落库预览链 |
| L2-SCH-10 | 给当前工单做交付优先排程 | scheduling | parse_intent, run | 策略驱动 |
| L2-SCH-11 | 用禁忌搜索和 SPT 对比一下 | scheduling | parse_intent, run | 与 plans 易混 |
| L2-SCH-12 | 排程 | scheduling | parse_intent, run | intent=schedule 显式对照 |

### 5.2 events（14 条）

| ID | 话术 | expect_agent | expect_parse.event_type | expect_tools（包含） |
|----|------|--------------|-------------------------|----------------------|
| L2-EVT-01 | 3号机坏了4小时 | events | machine_breakdown | parse_event, reschedule |
| L2-EVT-02 | 紧急插单 | events | insert_order | parse_event, check_insert_job?, reschedule |
| L2-EVT-03 | 订单106交期改为20 | events | due_date_change | parse_event, reschedule |
| L2-EVT-04 | 1号机停机大修8小时 | events | planned_downtime | parse_event, reschedule |
| L2-EVT-05 | 工单A加急 | events | priority_change | parse_event, reschedule |
| L2-EVT-06 | 支持哪些异常 | events | — | list_event_types |
| L2-EVT-07 | 物料延迟24小时 | events | material_delay | parse_event, reschedule |
| L2-EVT-08 | 撤单工单B | events | order_cancel | parse_event, reschedule |
| L2-EVT-09 | 工单A数量改成500件 | events | quantity_change | parse_event, reschedule |
| L2-EVT-10 | 客户插单 J005 交期后天 | events | insert_order | 插单+交期 |
| L2-EVT-11 | 2号产线计划停机2小时 | events | planned_downtime | 产线语义 |
| L2-EVT-12 | 3号机坏了需要重排 | events | machine_breakdown | guard：非 commitment |
| L2-EVT-13 | 改交期并重排 订单106 到25 | events | due_date_change | guard：非 commitment |
| L2-EVT-14 | 物料延迟3天到货重排 | events | material_delay | 与 kitting 区分 |

### 5.3 plans（10 条）

| ID | 话术 | expect_agent | expect_tools（包含） |
|----|------|--------------|----------------------|
| L2-PLN-01 | 新建计划试产01 | plans | create_plan |
| L2-PLN-02 | 列出所有计划 | plans | list_plans |
| L2-PLN-03 | 查看计划 E2E-试产01 | plans | bind_plan |
| L2-PLN-04 | 加载计划 演示-A | plans | bind_plan |
| L2-PLN-05 | 把计划 A 改名为计划 B | plans | rename_plan |
| L2-PLN-06 | 复制计划试产01 为试产02 | plans | duplicate_plan |
| L2-PLN-07 | 标记计划 A 为已完成 | plans | update_status |
| L2-PLN-08 | 删除计划旧版 | plans | delete_plan |
| L2-PLN-09 | 创建一个名为春季批次的计划 | plans | create_plan |
| L2-PLN-10 | 打开计划 sss | plans | bind_plan |

### 5.4 kitting（6 条）

| ID | 话术 | expect_agent | expect_tools（包含） | 备注 |
|----|------|--------------|----------------------|------|
| L2-KIT-01 | 检查一下齐套能否开工 | kitting | check_static, build_report | |
| L2-KIT-02 | 当前工单物料齐套吗 | kitting | check_static, build_report | |
| L2-KIT-03 | 缺料会导致哪些工单延期 | kitting | check_static, compute_delays? | kitting guard |
| L2-KIT-04 | 先排程再预测物料消耗 | kitting | run?, predict? | 先排后料 |
| L2-KIT-05 | 这批订单能否按时开工 | kitting | check_static, build_report | 非 commitment |
| L2-KIT-06 | 检查一下 BOM 缺料情况 | kitting | check_static, build_report | |

### 5.5 commitment（6 条）

| ID | 话术 | expect_agent | expect_tools（包含） | 备注 |
|----|------|--------------|----------------------|------|
| L2-CMT-01 | 交期能不能满足客户 | commitment | assess | |
| L2-CMT-02 | 哪些工单可能延期 | commitment | assess | 非 kitting「缺料导致」 |
| L2-CMT-03 | 评估一下当前排程的交付情况 | commitment | assess | |
| L2-CMT-04 | 生成一段给客户的交期说明话术 | commitment | assess, customer_script? | |
| L2-CMT-05 | 客户问能不能5月15日交货 | commitment | assess | |
| L2-CMT-06 | 这批订单交期有没有风险 | commitment | assess | |

### 5.6 whatif（5 条）

| ID | 话术 | expect_agent | expect_tools（包含） |
|----|------|--------------|----------------------|
| L2-WIF-01 | 对比一下交付优先和吞吐优先两种策略 | whatif | compare.variants |
| L2-WIF-02 | 如果按交期优先和按产能优先排，哪个更好 | whatif | compare.variants |
| L2-WIF-03 | 假设用 SPT 和禁忌搜索各跑一遍，对比一下 | whatif | compare.variants |
| L2-WIF-04 | 比较不同排程方案的风险差异 | whatif | compare.variants |
| L2-WIF-05 | 对比交付优先和产能优先 | whatif | compare.variants |

### 5.7 路由对抗 / Guard（12 条，tag: `adversarial`）

| ID | 话术 | expect_agent | 不应进入 |
|----|------|--------------|----------|
| L2-ADV-01 | 新建计划 benchmark_a | plans | scheduling |
| L2-ADV-02 | 用禁忌搜索排程 | scheduling | plans |
| L2-ADV-03 | 3号机坏了4小时，帮我重排 | events | commitment |
| L2-ADV-04 | 订单106交期改为20 | events | commitment |
| L2-ADV-05 | 缺料会导致哪些工单延期 | kitting | commitment |
| L2-ADV-06 | 交期能不能满足客户 | commitment | events |
| L2-ADV-07 | 把这个计划排程并保存落库 | scheduling | plans |
| L2-ADV-08 | 列出所有计划 | plans | scheduling |
| L2-ADV-09 | 对比一下交付优先和吞吐优先 | whatif | scheduling |
| L2-ADV-10 | 检查一下齐套能否开工 | kitting | scheduling |
| L2-ADV-11 | 紧急插单工单 J005 | events | scheduling |
| L2-ADV-12 | 做一个生产计划并排程落库 | scheduling | plans |

---

## 6. L3：端到端执行用例矩阵

> **合计：约 42 条**（含 6 条多轮/HITL）。入口统一 `POST /api/orchestrator/run`，`params.use_llm: true`。

### 6.1 各 Agent Artifacts 契约（E4 检查基准）

| Agent | 成功时必含 artifacts 键 |
|-------|-------------------------|
| scheduling | `schedule_results`（≥1 solver）、任一结果含 `gantt_data`、`metrics.makespan` |
| events | `impact_report` 或 `impact_gantt`；重排含 `reschedule_results` |
| kitting | `kitting_report` 或 `material_check` |
| commitment | `delivery_assessment` |
| whatif | `comparison` 或 `variant_results` |
| plans | `plan_id`（create/bind）或 `plans_list`（list） |

### 6.2 scheduling Exec（8 条）

| ID | 触发方式 | expect_status | E4 要点 | 备注 |
|----|----------|---------------|---------|------|
| L3-SCH-01 | 话术：「用 SPT 排程」+ min_jobs | success | schedule_results.spt | 基线 |
| L3-SCH-02 | 话术：「禁忌搜索交付优先」 | success | schedule_results 含 ts 或解析到的算法 | |
| L3-SCH-03 | intent=schedule, skip_parse, solvers=[spt,ts] | success | 2 个 solver 键 | 确定性对照 |
| L3-SCH-04 | 话术：「对比遗传算法和模拟退火」 | success | schedule_results ≥2 | slow |
| L3-SCH-05 | 话术：「跑 ft06 吞吐优先」 | success | makespan > 0 | slow |
| L3-SCH-06 | 话术：「有哪些算法」 | success | event_type_catalog 或 catalog | list_catalog 路径 |
| L3-SCH-07 | 话术：「排程并保存落库」+ plan_id | pending_confirm **或** success | confirm_token 或 propose | HITL |
| L3-SCH-08 | 覆盖已有排程的 plan | pending_confirm | has_existing_schedule=true | 需 plans_seed |

### 6.3 events Exec（12 条）

| ID | 话术 / params | expect_status | E4 要点 |
|----|---------------|---------------|---------|
| L3-EVT-01 | 3号机坏了4小时 + mes_baseline | success | impact_report.scenarios 含 r0/r1/r2 |
| L3-EVT-02 | 紧急插单（完整 envelope skip_parse） | success | dual gantt / insert 语义 |
| L3-EVT-03 | 订单106交期改为20 | success | due_date 变更 reflected |
| L3-EVT-04 | 工单A加急 | success | priority_change reschedule |
| L3-EVT-05 | 支持哪些异常 | success | event_type_catalog |
| L3-EVT-06 | 物料延迟24小时 | success | material_delay |
| L3-EVT-07 | 撤单工单B | success | order_cancel |
| L3-EVT-08 | 1号机停机8小时 | success | planned_downtime |
| L3-EVT-09 | 插单话术不完整（仅「紧急插单」） | need_input **或** success | 多轮 insert_job_intake |
| L3-EVT-10 | 数量变更 | success | quantity_change |
| L3-EVT-11 | GLM 自然语言：3号机坏了4小时 | success | 全链路 parse+reschedule |
| L3-EVT-12 | REST 对照：POST machine_breakdown_reschedule | success | 与 Agent 结果结构一致 |

### 6.4 kitting Exec（4 条）

| ID | 话术 / params | expect_status | E4 |
|----|---------------|---------------|-----|
| L3-KIT-01 | 检查齐套 + min_jobs | success | material_check / kitting_report |
| L3-KIT-02 | mode=check_only 显式 | success | 同上 |
| L3-KIT-03 | bom_jobs 缺料场景 | success | 含 delay 或 shortage 信息 |
| L3-KIT-04 | 先排程再预测物料（GLM 话术） | success | schedule_results + material |

### 6.5 commitment Exec（4 条）

| ID | 依赖 | 话术 | E4 |
|----|------|------|-----|
| L3-CMT-01 | 先 L3-SCH-01 session | 「交期能不能满足」 | delivery_assessment |
| L3-CMT-02 | schedule_results 在 context | intent=commitment | delivery_assessment.overall |
| L3-CMT-03 | 同上 | 「生成客户交期说明」 | customer_script 字段 |
| L3-CMT-04 | 无排程 | 「评估交付情况」 | success 或 need_input（需声明） |

### 6.6 whatif Exec（3 条）

| ID | 话术 | E4 |
|----|------|-----|
| L3-WIF-01 | 对比交付优先和吞吐优先 | comparison / ≥2 variants |
| L3-WIF-02 | SPT 和禁忌搜索对比 | 多 solver 对比表 |
| L3-WIF-03 | intent=whatif + strategy_ids | variant_results |

### 6.7 plans Exec（6 条，需 Mongo 或 mock）

| ID | 话术 | E4 | 清理 |
|----|------|-----|------|
| L3-PLN-01 | 新建计划 E2E-Temp | plan_id | teardown delete |
| L3-PLN-02 | 列出所有计划 | plans_list | — |
| L3-PLN-03 | 查看计划 {seed_name} | active_plan.plan_id | — |
| L3-PLN-04 | 重命名 | updated plan_name | teardown |
| L3-PLN-05 | 复制计划 | 新 plan_id | teardown |
| L3-PLN-06 | 删除计划 E2E-Temp | success | — |

### 6.8 多轮会话（5 条，tag: `multi_turn`）

| ID | 步骤 | 验证 |
|----|------|------|
| L3-MT-01 | ① SPT 排程 ② 「交期风险呢」 | 同 session；② agent=commitment；有 delivery_assessment |
| L3-MT-02 | ① 排程 ② 「3号机坏了4小时」 | ② agent=events；impact_report |
| L3-MT-03 | ① 「紧急插单」→ need_input ② 补全工艺 | ② success；insert 完成 |
| L3-MT-04 | ① 新建计划 ② 「给这个计划排程」 | ② 使用 plan_id |
| L3-MT-05 | ① whatif 对比 ② 「就按交付优先落库」 | ② scheduling + HITL |

### 6.9 HITL 落库（3 条，tag: `hitl`）

| ID | 流程 | 验证 |
|----|------|------|
| L3-HITL-01 | propose_schedule → confirm_save | DB 含 schedule_results |
| L3-HITL-02 | 覆盖排程 → pending_confirm → 用户确认 | confirm_token 一次性 |
| L3-HITL-03 | 拒绝/过期 token | error=invalid_or_expired_token |

---

## 7. 跨切面专项

### 7.1 ReAct 模式（可选套件）

对 L2-SCH-01/02、L2-EVT-01/02 在 `LLM_REACT_ENABLED=1` 下重跑：

- Tool 步数 ≤ `LLM_REACT_MAX_STEPS`
- 最终 agent 仍正确
- 无无限循环（超时算失败）

### 7.2 Summarize

L3 随机抽 10 条：`summary_zh` 长度 ≥ 20 且含中文关键词（排程/交期/重排/计划）。

### 7.3 降级探测（非 GLM 主路径，可选）

同话术在 `LLM_ENABLED=0` 下路由仍命中（规则 fallback），保证离线可用。

### 7.4 稳定性

同一 L2 用例连跑 3 次：路由 agent 一致率 = 100%（Plan 工具链允许 parse 细节差异）。

---

## 8. 自动化实现规格

### 8.1 文件布局（建议）

```
tests/data/agent_e2e/
  fixtures/           # §4 JSON
  l2_preview.yaml     # §5 全量 L2 用例
  l3_exec.yaml        # §6 全量 L3 用例
src/metaforge/eval/
  agent_e2e.py        # 加载 YAML、跑 preview/exec、断言、报告
tests/
  test_agent_e2e_l2.py
  test_agent_e2e_l3.py
scripts/
  run_agent_e2e.ps1   # 一键 L2 + 可选 L3
reports/
  agent_e2e_l2_{timestamp}.json
  agent_e2e_l3_{timestamp}.json
```

### 8.2 YAML 用例 Schema（扩展 `agent_benchmark.yaml`）

```yaml
- id: L2-SCH-01
  tier: preview                    # preview | exec
  message: "用禁忌搜索，交付优先排程"
  intent: null                     # 可选；null 表示纯 NL
  router_mode: llm                 # llm | explicit | rule
  expect_agent: scheduling
  expect_intent: schedule          # 可选
  expect_router: llm               # 可选；rule_override 时声明
  expect_tools:                    # 子集匹配
    - scheduling.parse_intent
    - scheduling.run
  expect_tools_ordered: false
  expect_plan_planner: llm          # llm | rule | any
  expect_parse_fields:             # 可选
    solvers: ["ts"]
  expect_status: success           # preview 固定 preview；exec 用 success/need_input/...
  context:
    fixture: min_jobs              # 引用 fixtures/*.json
  tags: [scheduling, l2]
  max_ms: 90000
  skip_unless: RUN_GLM_PREVIEW       # 环境门控
  notes: "算法+策略"

- id: L3-MT-01-step2
  tier: exec
  message: "交期风险呢"
  requires_session_from: L3-SCH-01
  expect_agent: commitment
  expect_status: success
  expect_artifacts_keys: [delivery_assessment]
  tags: [multi_turn, commitment]
```

### 8.3 执行器接口

```python
# agent_e2e.py 核心 API（实现参考）
def run_l2_case(case: dict) -> CaseResult: ...
def run_l3_case(case: dict, session_ids: dict) -> CaseResult: ...
def run_suite(tier: str, tags: list | None = None) -> BenchmarkReport: ...
def format_report_md(report) -> str: ...
def main(): ...  # CLI: --tier preview|exec --tags scheduling --json out.json
```

### 8.4 pytest 集成

```python
# test_agent_e2e_l2.py
@pytest.mark.parametrize("case", load_cases("l2_preview.yaml"), ids=lambda c: c["id"])
@pytest.mark.skipif(not os.getenv("RUN_GLM_PREVIEW"), reason="需 RUN_GLM_PREVIEW=1")
def test_l2_preview(case):
    result = run_l2_case(case)
    assert result.ok, result.detail

# test_agent_e2e_l3.py — 按 tag 分模块或 slow 标记
@pytest.mark.slow
@pytest.mark.skipif(not os.getenv("RUN_GLM_EXEC"), reason="需 RUN_GLM_EXEC=1")
def test_l3_exec_suite():
    report = run_suite("exec")
    assert report.rate("exec") >= 0.90
```

### 8.5 与现有脚本关系

| 现有 | 本方案 |
|------|--------|
| `glm_smoke.py`（21 条） | L2 子集；实现后由 `l2_preview.yaml`  supersede 并保留 smoke 作快速抽检 |
| `agent_benchmark.yaml` | 继续服务离线 rule/explicit；GLM 用例迁移到 `l2_preview.yaml` |
| `run_glm_smoke.ps1` | 升级为 `run_agent_e2e.ps1 --preview-only` |

---

## 9. 执行命令（实现后）

```powershell
# === L2 全量 Preview（65 条，需 API Key，约 30–60 min）===
.\scripts\run_agent_e2e.ps1 -Preview

# 或
$env:RUN_GLM_PREVIEW = "1"
$env:SESSION_STORE = "memory"
python -m metaforge.eval.agent_e2e --tier preview --json reports/agent_e2e_l2.json

# === L2 按域快扫 ===
python -m metaforge.eval.agent_e2e --tier preview --tags scheduling --limit 5

# === L3 全量 Exec（约 42 条，约 60–120 min）===
$env:RUN_GLM_EXEC = "1"
$env:AGENT_E2E_MONGO = "1"   # plans/HITL 用例
python -m metaforge.eval.agent_e2e --tier exec --json reports/agent_e2e_l3.json

# === L3 仅核心 Agent ===
python -m metaforge.eval.agent_e2e --tier exec --tags scheduling,events

# === 发版前完整套件 ===
$env:RUN_GLM_PREVIEW = "1"
$env:RUN_GLM_EXEC = "1"
$env:AGENT_E2E_MONGO = "1"
.\scripts\run_agent_e2e.ps1 -Full

# === ReAct 附加层 ===
$env:RUN_GLM_REACT = "1"
python -m metaforge.eval.agent_e2e --tier preview --tags react
```

**实现前临时可用**（现有能力）：

```powershell
.\scripts\run_glm_smoke.ps1                                    # L2 子集 21 条
$env:RUN_GLM_SMOKE_EXEC = "1"; .\scripts\run_glm_smoke.ps1     # L3 子集
$env:RUN_LLM_BENCHMARK = "1"; python -m metaforge.eval.agent_benchmark
$env:RUN_AGENT_BENCHMARK_EXEC = "1"
python -m pytest tests/test_agent_benchmark.py::test_agent_benchmark_run_tier -v
```

---

## 10. 实施路线图

| 阶段 | 交付 | 用例数 |
|------|------|--------|
| **P0** | `l2_preview.yaml` + `agent_e2e.py` preview  runner + `run_agent_e2e.ps1` | 58 L2 |
| **P1** | `l3_exec.yaml` + exec runner + artifacts 断言 | 30 L3（不含 Mongo） |
| **P2** | fixtures + 多轮/HITL + plans Mongo 用例 | +12 L3 |
| **P3** | ReAct/Reflect 分档 + CI nightly 任务 | 可选 |
| **P4** | 报告对比基线（fail only on regression） | 运维 |

---

## 11. 附录：现有覆盖 ↔ 缺口

| 区域 | 现有 | 本方案新增 |
|------|------|------------|
| L2 scheduling | 8（glm_smoke） | +4（list_catalog、落库预览等） |
| L2 events | 8 | +6（quantity_change、对抗等） |
| L2 plans | 1 | +9 CRUD |
| L2 kitting/commitment/whatif | 各 1–2 | 各扩至 5–6 |
| L2 路由对抗 | 1 | +11 |
| L3 scheduling | glm_smoke --exec 部分 | +HITL、多算法、ft06 |
| L3 events | test_agents_events_e2e 部分 | +GLM 自然语言全链路 |
| L3 plans | 无 GLM E2E | 6 条 |
| L3 多轮/HITL | 单测分散 | 8 条整合 |

---

## 12. 相关代码索引

| 模块 | 路径 |
|------|------|
| GLM 冒烟（现） | `src/metaforge/eval/glm_smoke.py` |
| Agent Benchmark（现） | `src/metaforge/eval/agent_benchmark.py` |
| Preview 入口 | `src/metaforge/orchestrator/preview.py` |
| 编排执行 | `src/metaforge/orchestrator/stream.py` |
| Agent 注册 | `src/metaforge/agents/registry_meta.py` |
| 路由 Guard | `src/metaforge/orchestrator/router.py` |
| 现有 E2E | `tests/test_orchestrator_e2e.py`、`tests/test_agents_events_e2e.py` |
