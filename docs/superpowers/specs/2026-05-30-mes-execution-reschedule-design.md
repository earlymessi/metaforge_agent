# MES 执行看板 + 异常重排（恢复对比）设计

> 日期：2026-05-30  
> 状态：已实现（2026-05-30）  
> 关联：`events` Agent、`/api/digital_twin/snapshot`、报表分析故障重排、`event_reschedule.run_machine_breakdown`

---

## 1. 背景与问题

### 1.1 现状

- **生产看板**（`DashboardView`）通过 `GET /api/digital_twin/snapshot` 展示数字孪生；有「计划回放」但取的是**最新** `schedule_result`，墙钟循环播放，**不能**选定「当前在产计划」。
- **异常重排 Agent**（`events.parse_event` → `events.reschedule`）默认 `breakdown_start=0`，`solvers=["ts","spt"]`，**未**读取报表/执行态中的基准甘特与算法。
- **对比**：后端会重跑 baseline 求解器，摘要只有延期数字，缺少「故障下不重排 vs 原算法重排」的清晰对照，也未标注冻结段/故障窗/重排段。

### 1.2 目标

1. 在看板选定**已排程计划**为「当前执行」，仿真时钟推进，机台状态与甘特对齐。
2. 自然语言异常重排（如「3 号机坏了 4 小时」）能读取 **sim_now、基准甘特、基准算法**。
3. **R1** 故障下沿用原计划：序不变，仅阻塞右移（时间推演）。
4. **R2** 重调度：**仅**使用与执行态一致的 **原算法**，对未完工残段重排（冻结前缀 + 更新机台就绪）。
5. 对比展示 **R0 / R1 / R2**，并标注冻结工序、故障窗口、重排段。

### 1.3 非目标（本期不做）

- 真实 MES 1:1 墙钟对齐（默认仿真倍速，见 §3.3）。
- 重排时多算法对比选优（用户明确：只原算法，保持简单）。
- 全局 Job Shop 理论最优证明；文案使用「恢复方案」而非「全局最优」。

---

## 2. 核心概念

| 符号 | 名称 | 说明 |
|------|------|------|
| **R0** | 原计划 | 执行态绑定的 `baseline_gantt`（无故障） |
| **R1** | 故障不重排 | 在 R0 上施加故障窗，**工序顺序不变**，不可加工时段右移/阻塞推演 |
| **R2** | 重排方案 | `freeze_time` 前冻结，残段仅用 `baseline_solver` 重算后与前缀合并 |
| **sim_time** | 仿真时刻 | 排程时间轴上的「现在」（小时，相对 t=0） |

**语义说明（FAQ）**：R2 与 R1 即使用同一求解器族，**输入不同**（残段问题 + 机台就绪），结果一般**不相同**；同算法 ≠ 和不重排一样。

---

## 3. MES 执行态（Shop Execution）

### 3.1 存储

Mongo 集合 `production_execution`，单文档 `_id: "active"`（单产线演示）：

```json
{
  "_id": "active",
  "status": "idle | running | paused",
  "plan_id": "ObjectId string",
  "plan_name": "string",
  "baseline_solver": "ts",
  "baseline_gantt": [ /* gantt_data */ ],
  "strategy_id": "balanced",
  "weights": { "makespan": 1.0, ... },
  "jobs_snapshot": [ /* JobData[]，与排程时一致 */ ],
  "sim_time": 0.0,
  "sim_speed": 60.0,
  "started_at_wall": "ISO8601",
  "updated_at_wall": "ISO8601"
}
```

- `baseline_gantt` / `baseline_solver` 来自用户在看板选择的计划及算法（与报表 `schedule_result` 中对应 solver 条目一致）。
- `jobs_snapshot` 供重排构建 `base_jobs`，避免计划正文变更后不一致。

**存储体量（与时间推进无关）**：

- 时钟只存标量 `sim_time` / `sim_speed` / 墙钟起点，**不按秒落历史**；每次 GET 按公式重算或更新一个 float 即可。
- 体积主要来自 `baseline_gantt` + `jobs_snapshot`（与既有 `schedule_result` 同量级，通常 KB～低 MB）；单文档 `_id: "active"`，仿真倍速再快也不会增加条数。
- 可选优化：执行态仅存 `plan_id` + `solver_id`，甘特从 `orders.schedule_result` 引用读取（少一份拷贝，实现时二选一）。

### 3.2 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/execution/state` | 返回当前执行态；无则 `status: idle` |
| POST | `/api/execution/start` | body: `plan_id`, `solver_id`；校验计划含该 solver 结果 |
| POST | `/api/execution/pause` | 暂停时钟 |
| POST | `/api/execution/resume` | 恢复 |
| POST | `/api/execution/reset` | 停止并清空 active |

服务端定时或每次 GET snapshot 时根据 `started_at_wall` 与 `sim_speed` 更新 `sim_time`（运行中）：

```
sim_time = min(makespan, (now_wall - started_at_wall).seconds / 3600 * sim_speed)
```

暂停时不推进 `sim_time`，记录 `paused_accum` 或 `paused_at_wall`（实现二选一，计划阶段实现时定一种）。

### 3.3 仿真时钟

**时间单位（与甘特一致）**：`baseline_gantt` 的 `start` / `end`、`sim_time`、故障 `breakdown_*` 均为 **排程小时**（相对计划起点 t=0）。看板展示建议标注 **h**，勿用墙钟「秒」后缀误导。

**`sim_speed` 定义**：每经过 **1 真实小时**（墙钟），仿真时间前进的 **排程小时数**。

```
Δsim_time（排程小时） = Δ墙钟秒数 / 3600 × sim_speed

sim_time = min(makespan, sim_time₀ + Δsim_time)   // 运行中；暂停时不累加 Δ
```

**已确认默认倍速**：**1 真实分钟 = 1 甘特小时（排程小时）**

- 代入：60 墙钟秒 → `60/3600 × sim_speed = 1` → **`sim_speed = 60`（默认）**
- 例：makespan = 44 → 约 **44 真实分钟** 播放到计划完工（未暂停、未提前触发重排）
- 例：故障「4 小时」→ 甘特轴上 4 个单位 → 仿真约 **4 真实分钟** 的停机窗长度

**看板可选档位（实现参考）**：

| 档位标签 | sim_speed | 换算 |
|----------|-----------|------|
| 默认（推荐） | 60 | 1 墙钟分 = 1 排程 h |
| 实时 1:1 | 1 | 1 墙钟 h = 1 排程 h |
| 快进 ×5 | 300 | 1 墙钟分 = 5 排程 h |

- 不在本期做真实 MES 墙钟 1:1 产线对接；若需更慢演示，用「实时 1:1」档。

### 3.4 看板 UI（`DashboardView`）

- 下拉：有计划且含 `schedule_result` 的订单列表。
- 下拉：该计划下可选 `solver_id`（来自 `schedule_result.results` 或扁平结构）。
- 按钮：开始执行 / 暂停 / 重置；展示 `plan_name`、`sim_time`、`makespan`、进度条。
- `digital_twin/snapshot` **优先读** `production_execution` 推导机台 running/idle；无执行态时保持现有随机/最新订单回放回退。

### 3.5 Orchestrator / Agent 上下文

`_prepare_orchestrator_areq` 对 `agent_id in ("events", ...)` 增加：

```python
execution = await fetch_production_execution()
if execution and execution.get("status") in ("running", "paused"):
    areq.context["extras"]["production_execution"] = execution
```

`events` 无执行态时：`parse_event` 仍可解析，但 `reschedule` 返回需澄清错误或通过 `events.load_execution` Tool 明确提示「请先在生产看板启动当前计划」。

---

## 4. 异常事件解析（时间 / 机台）

### 4.1 默认时间

| 字段 | 有执行态 | 无执行态 |
|------|----------|----------|
| `breakdown_start` | `sim_time` | 须澄清或默认 0（并提示无执行态） |
| `freeze_time` | `sim_time`（可参数覆盖） | 同左 |
| `breakdown_duration` | 从 NL 解析，默认 4h | 同左 |

口语「现在/马上坏了」→ `breakdown_start = sim_time`。

### 4.2 机台号展示

- 用户说「3 号机」→ `machine_id = 2`（0 起算），**对外文案统一显示「3 号机」**，避免与 machine_id 混淆。

### 4.3 LLM / 规则

- 更新 `orchestrator/llm/prompts.py` 事件示例：禁止把 3 号机写成 2 号机。
- `parse_event` 规则与 GLM 输出需写入 `execution` 可用时的默认时间来源说明。

---

## 5. 重排算法

### 5.1 R1 — 故障下沿用原计划（时间推演）

**输入**：`baseline_gantt`，`machine_id`，`breakdown_start`，`breakdown_duration`。

**规则**：

1. 工序按 R0 的 `(job_id, operation_id)` 顺序处理（序不变）。
2. 每台机维护 `machine_available`；工序开始时间 `start = max(job_ready, machine_available)`。
3. 若 `machine_id` 与故障机相同，且 `[start, start+duration)` 与 `[breakdown_start, breakdown_end)` 相交，则将工序推到 `breakdown_end` 之后（右移）；必要时链式推迟后续工序。
4. 输出 `r1_gantt` 与 `r1_completion` / metrics。

**不**调用求解器。用于对比「不重排有多差」。

### 5.2 R2 — 原算法残段重排

**输入**：`jobs_snapshot`，`baseline_gantt`，`baseline_solver`，`freeze_time`，故障参数，`weights`，`resource_config`。

**流程**（在现有 `run_machine_breakdown` 上改）：

1. 冻结：`start < freeze_time` → `frozen_ops`。
2. 故障机 `machine_ready[m] = max(..., breakdown_end)`。
3. 构建残段 `JobShopProblem`（与现逻辑一致）。
4. **仅** `compare_solvers([baseline_solver], ...)` 或 `run_single_solver(baseline_solver, ...)` — **禁止**默认 `["ts","spt"]`。
5. `merge_repaired_schedule` → `r2_gantt`。

`reschedule_options.solvers` 若传入且与 baseline 不同，以 **execution.baseline_solver** 为准（助手场景），报表 API 可显式传参覆盖（高级）。

### 5.3 选优

- 仅 R2 一版，无多候选 recovery_score。
- 验证：`r2` 的 makespan 或加权拖期应 **≤ R1**（大多数算例）；若不满足，在 `impact_report` 打 `warning` 供测试与 UI 展示，不静默失败。

---

## 6. 对比与 Tool

### 6.1 `impact_report` 扩展

```json
{
  "event_type": "machine_breakdown",
  "machine_id": 2,
  "machine_label_zh": "3号机",
  "breakdown_start": 12.0,
  "breakdown_end": 16.0,
  "freeze_time": 12.0,
  "baseline_solver": "ts",
  "scenarios": {
    "r0": { "makespan": 44, "weighted_tardiness_total": 8, "label": "原计划" },
    "r1": { "makespan": 52, "weighted_tardiness_total": 20, "label": "故障不重排" },
    "r2": { "makespan": 48, "weighted_tardiness_total": 14, "label": "原算法重排" }
  },
  "improvement_vs_r1": {
    "makespan_delta": -4,
    "tardiness_delta": -6
  },
  "delay_details": [ /* 相对 R0 或 R1，实现时固定一种，推荐相对 R1 */ ],
  "gantt_layers": {
    "frozen_ops": [ /* op keys */ ],
    "breakdown_window": { "machine_id": 2, "start": 12, "end": 16 },
    "rescheduled_op_keys": [ /* 相对 R0 时间/机器有变的工序 */ ]
  }
}
```

### 6.2 Tools

| Tool | 职责 |
|------|------|
| `execution.get_state` | 读执行态，供 Agent trace |
| `events.parse_event` | 合并 execution 默认时间 |
| `events.reschedule` | 调 `run_machine_breakdown` + R1 推演 |
| `events.compare_recovery`（或合并进 reschedule 输出） | 生成 scenarios + layers |
| `delivery.explain_impact` | 摘要模板含 R0/R1/R2 与改善量 |

### 6.3 前端

- **报表分析**：故障重排后展示三列指标；甘特叠加故障带（红）、冻结（灰）、重排变更（蓝）。
- **助手**：跳转报表时带 `impact_report` artifact。
- 与看板执行态联动：无执行态时禁用 NL 重排或强提示。

---

## 7. Agent 计划

```
s0  execution.get_state          （可选，无则失败提示）
s1  events.parse_event
s2  events.reschedule          （内含 R1+R2+impact）
s3  delivery.explain_impact
```

`scheduling` / `events` 路由不变；`reschedule` intent → `events`。

---

## 8. 错误处理

| 情况 | 行为 |
|------|------|
| 无 `production_execution` | `status=need_execution`，中文说明先看板启动 |
| 计划无 `schedule_result` | start API 400 |
| 残段为空 | 与现逻辑一致，返回 error |
| R2 劣于 R1 | 成功但 `warning` + 摘要注明 |

---

## 9. 测试要点

- R1 推演：单工序跨故障窗，应右移且序不变。
- R2 仅调用 `baseline_solver`（mock 计数）。
- 有 execution 时 `breakdown_start` 默认 = `sim_time`。
- impact `improvement_vs_r1.makespan_delta <= 0` 在标准 ft06 自定义工单上抽检。
- 机台文案：输入「3号机」摘要含「3号机」。

---

## 10. 实施分期

| 阶段 | 内容 |
|------|------|
| **P1** | `production_execution` API + 看板启停 + snapshot 读执行态 |
| **P2** | R1 时间推演 + R2 仅 baseline_solver + 去掉默认 ts/spt |
| **P3** | impact_report 扩展 + 报表/甘特图层 + explain_impact 模板 |
| **P4** | events Agent 接 execution + NL 默认时间 + 文档更新 `智能体功能清单.md` |

---

## 11. 已确认的产品决策

- 重调度：**仅原算法**（`baseline_solver`）。
- 故障下不重排：**R1 时间推演**（序不变、阻塞右移）。
- 基准甘特：**执行态绑定的当前计划 + 选中算法**（非重新 compare 出来的 TS）。
- 对比：R0 / R1 / R2 三场景 + 图层标注。
- 仿真时钟默认：**sim_speed = 60**（**1 墙钟分钟 = 1 排程小时**）。

---

## 12. 待决（可选，不阻塞 P1–P2）

- `delay_details` 相对 R0 还是 R1 展示（建议 **相对 R1**，突出重排价值）。
