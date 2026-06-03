# MES 执行看板 + 异常重排（恢复对比）Implementation Plan

> **已归档（2026-05-31）**：P1–P4 已实现（R0/R1/R2、影响评估）。现行说明见 [`../../智能体功能清单.md`](../../智能体功能清单.md) §2。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在生产看板选定「当前执行计划」并推进仿真时钟（1 墙钟分 = 1 排程 h）；异常重排基于执行态甘特做 R1 时间推演 + R2 原算法残段重排，展示 R0/R1/R2 对比与甘特图层。

**Architecture:** `production_execution` 单文档存基准甘特/算法/sim_time；`digital_twin/snapshot` 与 events Agent 读同一状态；`run_machine_breakdown` 以 R0 为 baseline（不再重跑 ts 造 baseline），R1 由纯推演模块生成，R2 仅 `baseline_solver`；impact 扩展三场景指标与 `gantt_layers`。

**Tech Stack:** Python 3.10+、FastAPI、`tests/main.py`、MongoDB Motor/PyMongo、pytest、Vue3 + Element Plus、`src/metaforge/*`

**Spec:** [`docs/superpowers/specs/2026-05-30-mes-execution-reschedule-design.md`](../specs/2026-05-30-mes-execution-reschedule-design.md)

---

## 文件结构总览

| 路径 | 职责 |
|------|------|
| `src/metaforge/services/production_execution.py` | 执行态 CRUD、sim_time 计算、从 order 提取 gantt/solver |
| `src/metaforge/utils/gantt_propagate.py` | R1：序不变 + 故障窗阻塞右移 |
| `src/metaforge/utils/machine_labels.py` | `machine_id` ↔ 「N 号机」展示 |
| `src/metaforge/services/event_reschedule.py` | 改 `run_machine_breakdown`：R0/R1/R2 + impact |
| `src/metaforge/tools/execution/get_state.py` | `execution.get_state` Tool |
| `src/metaforge/tools/execution/__init__.py` | 注册 execution tools |
| `src/metaforge/tools/events/parse_event.py` | 合并 `production_execution` 默认时间 |
| `src/metaforge/tools/events/reschedule.py` | 传入 execution、处理 `need_execution` |
| `src/metaforge/tools/delivery/explain_impact.py` | R0/R1/R2 摘要模板 |
| `src/metaforge/agents/events.py` | 计划加 `execution.get_state` |
| `src/metaforge/events/resolve_event.py` | NL 解析后 overlay execution |
| `src/metaforge/orchestrator/llm/prompts.py` | 机台号示例、execution 时间说明 |
| `tests/main.py` | `/api/execution/*`、`snapshot`、orchestrator enrich |
| `frontend/src/views/DashboardView.vue` | 选计划/算法、启停、sim 展示（h） |
| `frontend/src/api/client.js` | execution API 封装（若需） |
| `frontend/src/views/AnalysisView.vue` | 三场景表、impact 图层、甘特叠加 |
| `tests/test_production_execution.py` | sim_time、start/pause |
| `tests/test_gantt_propagate_r1.py` | R1 推演 |
| `tests/test_machine_breakdown_recovery.py` | R2 solver、impact、execution 默认时间 |
| `docs/智能体功能清单.md` | 更新 events / 看板说明 |

**存储策略（本期）：** 执行态文档内嵌 `baseline_gantt` + `jobs_snapshot`（与 spec 一致，实现简单）；不在本期做 plan_id 引用-only 优化。

**暂停实现：** 使用 `paused_at_wall: Optional[str]` + 运行中累加时扣除暂停时长：

```python
effective_elapsed_sec = (now - started).total_seconds() - paused_accum_sec
sim_time = min(makespan, effective_elapsed_sec / 3600.0 * sim_speed)
```

---

## Phase P1：执行态服务 + API + 看板

### Task P1.1: `production_execution` 服务

**Files:**
- Create: `src/metaforge/services/production_execution.py`
- Test: `tests/test_production_execution.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_production_execution.py
from datetime import datetime, timezone, timedelta

from metaforge.services.production_execution import (
    compute_sim_time,
    extract_solver_result,
)


def test_compute_sim_time_one_minute_equals_one_hour():
    started = datetime.now(timezone.utc) - timedelta(seconds=60)
    t = compute_sim_time(
        started_at_wall=started.isoformat(),
        sim_speed=60.0,
        makespan=100.0,
        status="running",
        paused_accum_sec=0.0,
    )
    assert 0.9 <= t <= 1.1


def test_compute_sim_time_caps_at_makespan():
    started = datetime.now(timezone.utc) - timedelta(hours=2)
    t = compute_sim_time(
        started_at_wall=started.isoformat(),
        sim_speed=60.0,
        makespan=10.0,
        status="running",
        paused_accum_sec=0.0,
    )
    assert t == 10.0


def test_extract_solver_result_flat():
    sr = {"ts": {"gantt_data": [{"job_id": 0}], "best_score": 44, "metrics": {}}}
    entry = extract_solver_result(sr, "ts")
    assert entry["gantt_data"][0]["job_id"] == 0
```

- [ ] **Step 2: 运行确认 FAIL**

```powershell
Set-Location "D:\Users\Administrator\Desktop\软著\metaforge"
python -m pytest tests/test_production_execution.py -v
```

- [ ] **Step 3: 实现 `production_execution.py`**

核心函数：

```python
DEFAULT_SIM_SPEED = 60.0  # 1 墙钟分 = 1 排程 h

def compute_sim_time(*, started_at_wall, sim_speed, makespan, status, paused_accum_sec) -> float: ...

def extract_solver_result(schedule_result: dict, solver_id: str) -> dict:
    """兼容 schedule_result.results[sid] 与扁平 schedule_result[sid]。"""

def build_execution_doc(order_doc: dict, solver_id: str) -> dict:
    """组装 active 文档含 baseline_gantt, jobs_snapshot, makespan, weights。"""

async def get_active(db) -> Optional[dict]: ...
async def start_execution(db, orders_coll, *, plan_id: str, solver_id: str, sim_speed: float = 60.0) -> dict: ...
async def pause_execution(db) -> dict: ...
async def resume_execution(db) -> dict: ...
async def reset_execution(db) -> None: ...
async def tick_sim_time(db) -> Optional[dict]:
    """GET 时调用：running 则重算 sim_time 并 $set。"""
```

`makespan` 从 gantt `max(end)` 或 `best_score` 取。

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit（用户要求时）**  
  `feat(execution): add production_execution service and sim_time`

---

### Task P1.2: FastAPI 端点 + Mongo 集合

**Files:**
- Modify: `tests/main.py`（`db.production_execution` 集合、5 个路由）
- Test: `tests/test_api_smoke.py` 或新建 `tests/test_execution_api.py`

- [ ] **Step 1: 写 API 测试（可用 TestClient + mock mongo 或集成）**

```python
def test_execution_state_idle(client):
    r = client.get("/api/execution/state")
    assert r.status_code == 200
    assert r.json().get("status") == "idle"
```

若项目无 TestClient 夹具，在 `test_production_execution.py` 用 mock `get_active` 测路由处理器逻辑。

- [ ] **Step 2: 在 `tests/main.py` 添加**

```python
execution_coll = db.production_execution

class ExecutionStartRequest(BaseModel):
    plan_id: str
    solver_id: str
    sim_speed: float = 60.0

@app.get("/api/execution/state")
async def execution_state():
    doc = await tick_and_return_execution()

@app.post("/api/execution/start")
async def execution_start(req: ExecutionStartRequest): ...

@app.post("/api/execution/pause")
@app.post("/api/execution/resume")
@app.post("/api/execution/reset")
```

`start`：校验 `orders_collection` 存在 `schedule_result` 且含 `solver_id`；`replace_one({"_id":"active"}, build_execution_doc(...), upsert=True)`。

- [ ] **Step 3: 手动验证**

```powershell
# 后端运行后
curl http://127.0.0.1:8008/api/execution/state
```

- [ ] **Step 4: Commit**  
  `feat(api): add production execution endpoints`

---

### Task P1.3: `digital_twin/snapshot` 读执行态

**Files:**
- Modify: `tests/main.py` — `get_digital_twin_snapshot`

- [ ] **Step 1: 改 snapshot 逻辑**

```python
active = await execution_coll.find_one({"_id": "active"})
if active and active.get("status") in ("running", "paused"):
    gantt = active["baseline_gantt"]
    makespan = active.get("makespan") or max(...)
    current_sim_time = active.get("sim_time", 0)  # 先 await tick_sim_time
    meta_info = {
        "status": "execution",
        "plan_name": active.get("plan_name"),
        "current_time": round(current_sim_time, 2),
        "total_time": round(makespan, 2),
        "sim_speed": active.get("sim_speed", 60),
        "time_unit": "h",
    }
    # 机台 running：task.start <= sim_time <= task.end
else:
    # 保留现有 latest_order 回放 / 随机模拟
```

- [ ] **Step 2: 看板手动：选计划→开始→current_time 递增**

- [ ] **Step 3: Commit**  
  `feat(twin): snapshot driven by production_execution`

---

### Task P1.4: 看板 UI

**Files:**
- Modify: `frontend/src/views/DashboardView.vue`

- [ ] **Step 1: 加载计划列表**

`GET /api/db/list`，过滤含 `schedule_result` 的项；第二下拉从 `schedule_result` 解析 solver keys。

- [ ] **Step 2: 控件**

- `sim_speed` 下拉：60 / 1 / 300（标签见 spec）
- 按钮：开始 / 暂停 / 恢复 / 重置 → 对应 POST
- 展示：`plan_name`、`sim_time` **h** / `makespan` **h**（去掉误导性 `s` 后缀）
- 轮询：`GET /api/execution/state` + `/api/digital_twin/snapshot` 每 2–3s

- [ ] **Step 3: 浏览器验证 1 分钟 ≈ 1h 推进**

- [ ] **Step 4: Commit**  
  `feat(ui): dashboard MES execution controls`

---

## Phase P2：R1 推演 + R2 原算法重排

### Task P2.1: R1 `gantt_propagate`

**Files:**
- Create: `src/metaforge/utils/gantt_propagate.py`
- Create: `src/metaforge/utils/machine_labels.py`
- Test: `tests/test_gantt_propagate_r1.py`

- [ ] **Step 1: 失败测试**

```python
from metaforge.utils.gantt_propagate import propagate_breakdown_on_gantt

def test_r1_shifts_op_crossing_breakdown_window():
    gantt = [
        {"job_id": 0, "machine_id": 2, "operation_id": 0, "start": 10.0, "end": 14.0},
    ]
    out = propagate_breakdown_on_gantt(
        gantt,
        machine_id=2,
        breakdown_start=12.0,
        breakdown_duration=4.0,
    )
    assert out[0]["start"] >= 16.0  # 推到 breakdown_end
    assert out[0]["end"] > out[0]["start"]
```

再加多工序、多机台：故障机工序右移，其他机序不变。

- [ ] **Step 2: 实现**

按 spec §5.1：按 `(job_id, operation_id)` 排序；维护 `machine_available` / `job_ready`；相交故障窗则 `start = breakdown_end` 再链式更新。

返回新 gantt 列表（深拷贝）。

- [ ] **Step 3: `machine_labels.py`**

```python
def machine_label_zh(machine_id: int) -> str:
    return f"{machine_id + 1}号机"
```

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit**  
  `feat(reschedule): R1 gantt propagate without solver`

---

### Task P2.2: 重构 `run_machine_breakdown`

**Files:**
- Modify: `src/metaforge/services/event_reschedule.py`
- Test: `tests/test_machine_breakdown_recovery.py`

- [ ] **Step 1: 失败测试**

```python
from unittest.mock import patch
from metaforge.services.event_reschedule import run_machine_breakdown

def test_r2_uses_only_baseline_solver():
    seen = []
    def fake_compare(solvers, *a, **k):
        seen.extend(solvers)
        return {"ga": {"gantt_data": [], "metrics": {"makespan": 1}}}
    # ... minimal jobs + baseline_gantt fixture ...
    with patch("metaforge.services.event_reschedule.compare_solvers", side_effect=fake_compare):
        run_machine_breakdown(..., solvers=["ts", "spt"], baseline_gantt=..., baseline_solver="ga")
    assert seen == ["ga"]
```

```python
def test_baseline_gantt_used_not_recomputed():
    """传入 baseline_gantt 时不得 compare_solvers(solvers[:1]) 造新 baseline。"""
```

- [ ] **Step 2: 改 `run_machine_breakdown` 签名与逻辑**

新增参数：

```python
def run_machine_breakdown(
    base_jobs,
    machine_id: int,
    breakdown_start: float,
    breakdown_duration: float,
    *,
    freeze_time: Optional[float] = None,
    baseline_gantt: Optional[List[dict]] = None,
    baseline_solver: Optional[str] = None,
    **kwargs,
):
```

流程：

1. `r0_gantt = baseline_gantt`；若无则回退现逻辑（兼容报表 API 直调）。
2. `r0_completion = job_completion_map(r0_gantt)`；metrics R0 用 `compute_schedule_metrics`。
3. `r1_gantt = propagate_breakdown_on_gantt(...)`；R1 metrics。
4. `freeze_time = freeze_time if freeze_time is not None else breakdown_start`。
5. `frozen_ops` 从 **r0_gantt**（非重算 baseline）筛选 `start < freeze_time`。
6. `solver = baseline_solver or (kwargs.get("solvers") or ["ts"])[0]`；**仅** `compare_solvers([solver], residual_problem, ...)`。
7. merge → `r2_gantt`；R2 metrics。
8. `impact = build_recovery_impact_report(r0, r1, r2, ...)`（Task P3 可先 stub）。

删除/绕过：`baseline = compare_solvers(solvers[:1], base_problem, ...)` 当 `baseline_gantt` 提供时。

- [ ] **Step 3: `dispatch_event_reschedule` 传入 envelope extras**

从 `envelope["production_execution"]` 或 `reschedule_options` 取 `baseline_gantt`, `baseline_solver`, `jobs_snapshot`。

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit**  
  `feat(events): machine breakdown uses R0 gantt and single solver`

---

### Task P2.3: 报表 API 对齐

**Files:**
- Modify: `tests/main.py` — `machine_breakdown_reschedule` 请求体

- [ ] **Step 1:** 若 body 含 `baseline_gantt` + `baseline_solver`，直传 `run_machine_breakdown`（AnalysisView 已有 `store.results`）。

- [ ] **Step 2:** 默认 `solvers` 改为 `[store.lastSolver]` 单元素，不再 `Object.keys(results)` 多算法。

- [ ] **Step 3: Commit**  
  `fix(api): breakdown reschedule single baseline solver from report`

---

## Phase P3：Impact 对比 + 前端展示

### Task P3.1: `build_recovery_impact_report`

**Files:**
- Modify: `src/metaforge/utils/event_helpers.py` 或新建 `src/metaforge/utils/recovery_impact.py`
- Modify: `src/metaforge/services/event_reschedule.py`

- [ ] **Step 1: 实现报告结构（spec §6.1）**

```python
def build_recovery_impact_report(
    *,
    r0_gantt, r1_gantt, r2_gantt,
    r0_metrics, r1_metrics, r2_metrics,
    baseline_solver: str,
    machine_id: int,
    breakdown_start: float,
    breakdown_end: float,
    freeze_time: float,
    job_name_map: dict,
) -> dict:
```

- `scenarios.r0/r1/r2`：makespan、weighted_tardiness_total、label
- `improvement_vs_r1`：makespan_delta = r2 - r1（负为改善）
- `delay_details`：**相对 R1**（`old_completion` from R1, `new` from R2）
- `gantt_layers`：`frozen_ops` keys、`breakdown_window`、`rescheduled_op_keys`（对比 r0 vs r2）
- `warning` if r2 makespan > r1 makespan + 1e-6

- [ ] **Step 2: 单元测试 assertions on improvement**

- [ ] **Step 3: Commit**  
  `feat(impact): R0/R1/R2 recovery report`

---

### Task P3.2: `delivery.explain_impact`

**Files:**
- Modify: `src/metaforge/tools/delivery/explain_impact.py`
- Test: `tests/test_tools_events.py` 或新文件

- [ ] **Step 1: 扩展摘要**

```python
sc = impact.get("scenarios") or {}
lines = [
    f"事件：{machine_label_zh(impact['machine_id'])}故障 "
    f"{impact['breakdown_start']:.1f}–{impact['breakdown_end']:.1f}h（仿真时刻）。",
    f"原计划(R0) makespan={sc['r0']['makespan']:.1f}；"
    f"不重排(R1)={sc['r1']['makespan']:.1f}；"
    f"重排(R2,{impact['baseline_solver']})={sc['r2']['makespan']:.1f}。",
]
imp = impact.get("improvement_vs_r1") or {}
if imp.get("makespan_delta", 0) < 0:
    lines.append(f"相对不重排，完工缩短 {abs(imp['makespan_delta']):.1f}h。")
elif impact.get("warning"):
    lines.append("注意：重排方案未优于故障下沿用原计划，请检查参数。")
```

- [ ] **Step 2: pytest**

- [ ] **Step 3: Commit**

---

### Task P3.3: 报表分析 UI

**Files:**
- Modify: `frontend/src/views/AnalysisView.vue`
- Modify: `frontend/src/stores/useResultsStore.js`（若需存 `recovery_scenarios`）

- [ ] **Step 1: impact 对话框增加三列 scenarios 表**（R0/R1/R2 makespan、拖期）

- [ ] **Step 2: 甘特 `renderGantt` 叠加**

- `markArea` 或 `itemStyle`：故障窗红色透明带
- 冻结工序灰色
- 变更工序高亮（来自 `gantt_layers.rescheduled_op_keys`）

- [ ] **Step 3: 故障表单默认 `breakdown_start` = `store.executionSimTime`**（若 execution state API 已接）

- [ ] **Step 4: 手动验证重排后可读对比**

- [ ] **Step 5: Commit**  
  `feat(ui): recovery comparison and gantt layers`

---

## Phase P4：Events Agent + NL 集成

### Task P4.1: `execution.get_state` Tool

**Files:**
- Create: `src/metaforge/tools/execution/get_state.py`
- Create: `src/metaforge/tools/execution/__init__.py`
- Modify: `src/metaforge/tools/load_all.py`
- Modify: `src/metaforge/agents/events.py`

- [ ] **Step 1: Tool 读 `ctx.extras["production_execution"]` 或调服务**

无执行态：`ToolResult(ok=False, error="请先在生产看板启动当前计划")`

- [ ] **Step 2: `EventsAgentRunner.build_rule_plan`**

```python
steps = [PlanStep("s0", "execution.get_state", {})]
# 然后 parse_event, reschedule, explain_impact
```

`list_event_types` 查询时不加 s0。

- [ ] **Step 3: 注册 + pytest `test_tools_registry` 含 execution.get_state**

- [ ] **Step 4: Commit**

---

### Task P4.2: `parse_event` + execution 默认时间

**Files:**
- Modify: `src/metaforge/tools/events/parse_event.py`
- Modify: `src/metaforge/events/resolve_event.py`
- Modify: `src/metaforge/orchestrator/llm/parsers.py`
- Modify: `src/metaforge/orchestrator/llm/prompts.py`

- [ ] **Step 1: `parse_event_message` / LLM 后处理**

```python
def apply_execution_defaults(params: dict, execution: Optional[dict]) -> dict:
    if not execution:
        return params
    if execution.get("status") in ("running", "paused"):
        sim = float(execution.get("sim_time") or 0)
        params.setdefault("breakdown_start", sim)
        params.setdefault("freeze_time", sim)
    return params
```

- [ ] **Step 2: 机台文案** — prompts 示例改为「3号机」对应 `machine_id=2`；`summary_zh` 用 `machine_label_zh`

- [ ] **Step 3: `events/reschedule.py` 把 execution 写入 envelope**

```python
env["production_execution"] = ctx.extras.get("production_execution")
env["reschedule_options"]["baseline_solver"] = execution["baseline_solver"]
env["reschedule_options"]["solvers"] = [execution["baseline_solver"]]
```

- [ ] **Step 4: 测试 `test_machine_breakdown_with_execution_defaults`**

- [ ] **Step 5: Commit**

---

### Task P4.3: Orchestrator 注入 execution

**Files:**
- Modify: `tests/main.py` — `_prepare_orchestrator_areq`

- [ ] **Step 1: 对 `agent_id == "events"` 加载 active execution**

```python
doc = await execution_coll.find_one({"_id": "active"})
if doc:
    await tick_sim_time(...)  # 或内联 compute
    areq.context["extras"]["production_execution"] = doc
```

- [ ] **Step 2: E2E** — `tests/test_agents_events.py` mock execution，发「3号机坏了4小时」断言 `breakdown_start` ≈ sim_time

- [ ] **Step 3: Commit**

---

### Task P4.4: 文档

**Files:**
- Modify: `docs/智能体功能清单.md`
- Modify: `docs/superpowers/specs/2026-05-30-mes-execution-reschedule-design.md` — `状态: 已实现`（全部任务完成后）

- [ ] **Step 1:** §2 异常重排补充：需先看板启动执行；R0/R1/R2 说明；sim 1min=1h

- [ ] **Step 2: Commit**  
  `docs: MES execution and recovery reschedule`

---

## 验证清单（Phase 完成后）

```powershell
Set-Location "D:\Users\Administrator\Desktop\软著\metaforge"
python -m pytest tests/test_production_execution.py tests/test_gantt_propagate_r1.py tests/test_machine_breakdown_recovery.py tests/test_tools_events.py tests/test_agents_events.py -q
```

手动：

1. 排程中心跑一版 → 报表有结果  
2. 看板选计划 + 算法 → 开始执行 → sim_time 约 1min +1h  
3. 助手：「3号机坏了4小时，帮我重排」→ 摘要含 R0/R1/R2；甘特有故障带  
4. 报表「设备故障重排」仍可用，且仅用当前选中算法  

---

## Spec 覆盖自检

| Spec § | 任务 |
|--------|------|
| §3 MES 执行态 | P1.1–P1.4 |
| §3.3 sim_speed=60 | P1.1 `DEFAULT_SIM_SPEED` |
| §4 时间/机台 | P4.2 |
| §5.1 R1 | P2.1 |
| §5.2 R2 原算法 | P2.2 |
| §5.3 R2≤R1 warning | P3.1 |
| §6 impact + UI | P3.1–P3.3 |
| §7 Agent 计划 | P4.1–P4.3 |
| §8 错误处理 | P4.1 need_execution |

**待决（本期固定）：** `delay_details` 相对 **R1**（P3.1）。

---

## 执行方式

Plan 已保存至 `docs/superpowers/plans/2026-05-30-mes-execution-reschedule.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每 Task 派生子 agent，任务间你做 review  
2. **Inline Execution** — 本会话按 Phase 连续实现，Phase 末 checkpoint  

你更倾向哪一种？确认后可从 **P1.1** 开始写代码。
