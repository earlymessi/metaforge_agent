# MetaForge MES 多智能体 Implementation Plan

> **已归档（2026-05-31）**：Phase 0–4 已完成；`pipeline` Agent 已合并入 `scheduling`。现行说明见 [`../../智能体功能清单.md`](../../智能体功能清单.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按设计 spec 实现 **6 个业务 Agent（场景 1:1）+ 共享 Tool 层 + Intent Router**，先规则 Plan、不接 LLM；为后期 NL/LLM 预留 schema 与注册表 API。

**Architecture:** Router 将 `intent` 映射到唯一主责 Agent；Agent 内部 Plan-and-Solve 调用白名单 Tool；Tool 封装现有 `compare_solvers`、events API、material、delivery、db。`scheduling` Agent 复用现有 `SchedulingAgent`。

**Tech Stack:** Python 3.10+、FastAPI、`tests/main.py`、MongoDB motor、pytest、现有 `src/metaforge/*`

**Spec:** [`docs/superpowers/specs/2026-05-29-mes-multi-agent-design.md`](../../superpowers/specs/2026-05-29-mes-multi-agent-design.md)

---

## 文件结构总览

| 路径 | 职责 |
|------|------|
| `src/metaforge/tools/base.py` | `ToolResult`, `ToolSpec`, 注册装饰器 |
| `src/metaforge/tools/registry.py` | 全局 `TOOL_REGISTRY`, `run_tool(name, ctx)` |
| `src/metaforge/tools/scheduling/` | `parse_intent`, `run`, `run_async` |
| `src/metaforge/tools/material/` | `check_static`, `compute_delays`, `predict` |
| `src/metaforge/tools/delivery/` | `assess`, `customer_script`, `explain_impact` |
| `src/metaforge/tools/events/` | `parse_event`, `reschedule`, `EVENT_REGISTRY` |
| `src/metaforge/tools/data/` | `load_plan`, `propose_persist`, `confirm_persist` |
| `src/metaforge/tools/compare/` | `variants` |
| `src/metaforge/tools/kitting/` | `build_report` |
| `src/metaforge/agents/base.py` | `BaseAgent`, `AgentRequest`, `AgentResponse` |
| `src/metaforge/agents/{scheduling,events,kitting,commitment,whatif,pipeline}.py` | 6 Agent |
| `src/metaforge/orchestrator/router.py` | `resolve_intent`, `route` |
| `src/metaforge/orchestrator/session.py` | 内存 session（Phase 4 可换 Mongo） |
| `tests/test_tools_*.py` | Tool 单测 |
| `tests/test_agents_*.py` | Agent + Router E2E |
| `tests/main.py` | 新 API 端点 |

---

## Phase 0：Tool 基础

### Task 0.1: Tool 基类与注册表

**Files:**
- Create: `src/metaforge/tools/__init__.py`
- Create: `src/metaforge/tools/base.py`
- Create: `src/metaforge/tools/registry.py`
- Test: `tests/test_tools_registry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tools_registry.py
from metaforge.tools.registry import run_tool, list_tools


def test_list_tools_includes_scheduling_run():
    names = {t["name"] for t in list_tools()}
    assert "scheduling.run" in names


def test_run_tool_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        run_tool("nonexistent.tool", {})
```

- [ ] **Step 2: 运行确认 FAIL**

```powershell
Set-Location D:\Users\Administrator\Desktop\软著\metaforge\tests
$env:PYTHONIOENCODING="utf-8"
python -m pytest test_tools_registry.py -v
```

Expected: `ModuleNotFoundError` 或 `KeyError` 行为未实现

- [ ] **Step 3: 实现 base + registry**

`src/metaforge/tools/base.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

@dataclass
class ToolContext:
    """执行 Tool 时的共享上下文（由 Agent 填充）。"""
    custom_data: Optional[List[Any]] = None
    benchmark_file: Optional[str] = None
    plan_id: Optional[str] = None
    weights: Optional[Dict[str, float]] = None
    enforce_material: bool = False
    random_seed: Optional[int] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolResult:
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    artifacts_key: Optional[str] = None

@dataclass
class ToolSpec:
    name: str
    description_zh: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any], ToolContext], ToolResult]
```

`src/metaforge/tools/registry.py` 实现 `register_tool(spec)`, `list_tools()`, `run_tool(name, params, ctx)`.

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit**（用户要求时）：`feat(tools): add ToolResult registry skeleton`

---

### Task 0.2: `scheduling.parse_intent` Tool

**Files:**
- Create: `src/metaforge/tools/scheduling/__init__.py`
- Create: `src/metaforge/tools/scheduling/parse_intent.py`
- Modify: `src/metaforge/tools/registry.py`（import 注册）
- Test: `tests/test_tools_scheduling.py`

- [ ] **Step 1: 测试封装现有 SchedulingAgent**

```python
from metaforge.tools.registry import run_tool
from metaforge.tools.base import ToolContext

def test_scheduling_parse_intent_tabu_delivery():
    ctx = ToolContext()
    r = run_tool(
        "scheduling.parse_intent",
        {"message": "禁忌搜索，交付优先"},
        ctx,
    )
    assert r.ok
    assert "ts" in r.data["solvers"]
    assert r.data["strategy_id"] == "delivery"
```

- [ ] **Step 2: FAIL 后实现**

`parse_intent.py` 内调用 `SchedulingAgent().parse(message, **overrides)`，返回 `ToolResult(data=intent 字段 dict)`。

- [ ] **Step 3: PASS**

---

### Task 0.3: `scheduling.run` Tool

**Files:**
- Create: `src/metaforge/tools/scheduling/run.py`
- Test: `tests/test_tools_scheduling.py`（追加）

- [ ] **Step 1: 测试最小 JobShop 排程**

```python
from metaforge.problems.jobshop import Job, JobShopProblem, Task
from metaforge.tools.base import ToolContext
from metaforge.tools.registry import run_tool

def test_scheduling_run_spt():
    jobs = [Job(tasks=[Task(machine_id=0, duration=3, id=0)], id=0)]
    problem = JobShopProblem(jobs, instance_name="t")
    ctx = ToolContext(extras={"problem": problem})
    r = run_tool(
        "scheduling.run",
        {"solvers": ["spt"], "weights": {"makespan": 1.0, "weighted_tardiness_total": 0.5, "energy_cost": 0.0, "machine_busy_cv": 5.0}},
        ctx,
    )
    assert r.ok
    assert "spt" in r.data["results"]
    assert r.data["results"]["spt"]["gantt_data"]
```

- [ ] **Step 2: 实现**

直接调 `compare_solvers(solvers, problem, weights=..., random_seed=...)`；若 `ctx.custom_data` 存在，需在 Tool 内调与 `main._build_problem_from_custom_jobs` 相同逻辑——**抽取**到 `src/metaforge/utils/problem_builder.py`（避免 Tool 依赖 `tests/main.py`）。

- [ ] **Step 3: 抽取 problem_builder（若 Step 2 需要）**

- Create: `src/metaforge/utils/problem_builder.py`  
- 从 `tests/main.py` 迁移 `_build_problem_from_custom_jobs`、`_resolve_task_duration` 为公开函数 `build_problem_from_job_data_list(jobs, instance_name=...)`
- `tests/main.py` 改为 import 调用（保持 API 行为不变）

- [ ] **Step 4: pytest PASS + 回归 `test_api_smoke.py`**

```powershell
python -m pytest test_tools_scheduling.py test_api_smoke.py -q
```

---

### Task 0.4: `material.check_static` / `material.predict`

**Files:**
- Create: `src/metaforge/tools/material/check_static.py`
- Create: `src/metaforge/tools/material/predict.py`
- Test: `tests/test_tools_material.py`

- [ ] **Step 1: 测试 check_static**

对 `JobData` pydantic 列表 mock inventory dict，断言 `feasible` 字段；调用 `check_jobs_material_static`。

- [ ] **Step 2: 实现并注册**

- [ ] **Step 3: predict** 封装 `build_material_report_for_schedule` 或现有 `/api/materials/predict` 逻辑

- [ ] **Step 4: PASS**

---

### Task 0.5: `delivery.assess` / `delivery.explain_impact`

**Files:**
- Create: `src/metaforge/tools/delivery/assess.py`
- Create: `src/metaforge/tools/delivery/explain_impact.py`
- Create: `src/metaforge/tools/delivery/customer_script.py`
- Test: `tests/test_tools_delivery.py`

- [ ] **Step 1: assess** 输入 `gantt_data` + `problem`，输出 `delivery_assessment`（含 `overall`, `jobs[]`, `summary_zh`）

使用 `compute_delivery_predictions`，再规则生成 `verdict_zh`（映射 spec §6.1 risk_level）。

- [ ] **Step 2: explain_impact** 输入 `impact_report`，输出 `summary_zh`

- [ ] **Step 3: customer_script** 输入 `delivery_assessment`，模板拼接话术（Phase 0 不用 LLM）

- [ ] **Step 4: pytest PASS**

---

### Task 0.6: `GET /api/tools/registry`

**Files:**
- Modify: `tests/main.py`

- [ ] **Step 1: 添加路由**

```python
from metaforge.tools.registry import list_tools

@app.get("/api/tools/registry")
async def get_tools_registry():
    return {"tools": list_tools()}
```

- [ ] **Step 2: 测试路由注册**

```python
def test_tools_registry_route():
    from main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/tools/registry" in paths
```

---

## Phase 1：Agent 骨架 + scheduling + commitment + Router

### Task 1.1: `BaseAgent` 与请求/响应模型

**Files:**
- Create: `src/metaforge/agents/__init__.py`
- Create: `src/metaforge/agents/base.py`
- Test: `tests/test_agents_base.py`

- [ ] **Step 1: 定义模型**

```python
@dataclass
class AgentRequest:
    message: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentResponse:
    status: str  # success | need_input | pending_confirm | failed
    agent_id: str
    summary_zh: str = ""
    plan: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    pending_action: Optional[Dict[str, Any]] = None
```

`BaseAgent`:
- `agent_id: str`
- `allowed_tools: List[str]`
- `build_plan(request) -> List[PlanStep]`
- `run(request) -> AgentResponse` 循环执行 plan，写 `artifacts`

- [ ] **Step 2: 单测 mock plan 执行一步 tool**

---

### Task 1.2: `scheduling` Agent

**Files:**
- Create: `src/metaforge/agents/scheduling.py`
- Modify: `src/metaforge/agent/scheduling_agent.py`（保留 parse，Agent 调用 Tool）
- Test: `tests/test_agents_scheduling.py`

- [ ] **Step 1: Plan 模板**

```python
def build_plan(self, request):
    if request.params.get("skip_parse"):
        return [PlanStep("s1", "scheduling.run", {...})]
    return [
        PlanStep("s1", "scheduling.parse_intent", {"message": request.message}),
        PlanStep("s2", "scheduling.run", {"use_artifacts": "interpretation"}),
    ]
```

- [ ] **Step 2: E2E 测试** `params` 传 `custom_data` 结构（最小 1 工单）

- [ ] **Step 3: API** `POST /api/agents/scheduling/run`；`/api/agent/schedule` 内部转调 `SchedulingAgentRunner.run`

---

### Task 1.3: `commitment` Agent

**Files:**
- Create: `src/metaforge/agents/commitment.py`
- Test: `tests/test_agents_commitment.py`

- [ ] **Step 1: Plan** `resolve_schedule_ref`（读 `context.schedule_results` 或调 `scheduling.run`）→ `delivery.assess` → 可选 `delivery.customer_script`

- [ ] **Step 2: 测试** 传入已有 `artifacts.schedule_results`

- [ ] **Step 3: API** `POST /api/agents/commitment/run`

---

### Task 1.4: Intent Router

**Files:**
- Create: `src/metaforge/orchestrator/__init__.py`
- Create: `src/metaforge/orchestrator/router.py`
- Test: `tests/test_orchestrator_router.py`

- [ ] **Step 1: 实现 `resolve_agent_id(message, intent=None)`**

按 spec §3.6 优先级规则（保存→whatif→events→kitting→commitment→scheduling）。

```python
def resolve_agent_id(message: str = "", intent: str | None = None) -> str:
    if intent:
        return INTENT_TO_AGENT[intent]
    msg = message or ""
    if any(k in msg for k in ("保存", "落库")) and "plan" in msg.lower():
        return "pipeline"
    ...
    return "scheduling"
```

- [ ] **Step 2: 表驱动测试** 至少 12 条用例

- [ ] **Step 3: `POST /api/orchestrator/run`**

```python
class OrchestratorRequest(BaseModel):
    message: str = ""
    intent: Optional[str] = None
    context: Dict[str, Any] = {}
    params: Dict[str, Any] = {}

@app.post("/api/orchestrator/run")
async def orchestrator_run(req: OrchestratorRequest):
    agent_id = resolve_agent_id(req.message, req.intent)
    agent = get_agent(agent_id)
    return agent.run(AgentRequest(...))
```

---

### Task 1.5: `GET /api/agents/registry`

**Files:**
- Create: `src/metaforge/agents/registry_meta.py`（静态 6 Agent 元数据）
- Modify: `tests/main.py`

- [ ] **返回** `id, name_zh, intent, endpoint, allowed_tools, nl_keywords` 与 spec §10 一致

- [ ] **测试** 长度为 6，`scheduling` 在列

---

## Phase 2：kitting + events（扩展事件 API）

### Task 2.1: `kitting.build_report` + `kitting` Agent

**Files:**
- Create: `src/metaforge/tools/kitting/build_report.py`
- Create: `src/metaforge/agents/kitting.py`
- Test: `tests/test_agents_kitting.py`

- [ ] **三种 Plan 模式**（spec §5.3）用 `params.mode`: `check_only` | `kit_then_schedule` | `schedule_then_predict`

- [ ] **API** `POST /api/agents/kitting/run`

---

### Task 2.2: `events.parse_event` + `events.reschedule` Tool

**Files:**
- Create: `src/metaforge/tools/events/registry.py`（`EVENT_REGISTRY`）
- Create: `src/metaforge/tools/events/parse_event.py`
- Create: `src/metaforge/tools/events/reschedule.py`
- Test: `tests/test_tools_events.py`

- [ ] **parse_event（规则版）**

| event_type | 规则示例 |
|------------|----------|
| `insert_order` | 含「插单」 |
| `machine_breakdown` | 含「坏了/故障」+ 解析 machine_id、时长 |
| `due_date_change` | 含「交期」 |
| `planned_downtime` | 含「停机/大修」 |
| `material_delay` | 含「晚到/延迟」 |
| `priority_change` | 含「加急/优先级」 |
| `order_cancel` | 含「取消/撤单」 |
| `quantity_change` | 含「数量」 |

输出统一 `event_envelope`。

- [ ] **reschedule** 根据 `event_type` 调 `tests/main` 中对应 handler；未实现 API 的返回 `ok=False` + `error=not_implemented`

---

### Task 2.3: 扩展事件 REST API（待实现 5 类）

**Files:**
- Modify: `tests/main.py`
- Create: `src/metaforge/utils/event_mutations.py`（纯函数：改 jobs 列表）
- Test: `tests/test_events_extended.py`

对每个事件实现 **最小可用** 路径：

| API | 行为 |
|-----|------|
| `POST /api/events/planned_downtime` | 合并 `downtime_blocks` 到 resource_config → 调 compare |
| `POST /api/events/material_delay` | 设置 `material_arrival` → 重排 |
| `POST /api/events/priority_change` | 改 priority → 重排 |
| `POST /api/events/order_cancel` | 过滤 jobs → 重排 |
| `POST /api/events/quantity_change` | 改 quantity + 重算 duration → 重排 |

- [ ] 每个端点至少 1 个 pytest（可 mock Mongo）

- [ ] `events/reschedule` Tool 路由到新端点

---

### Task 2.4: `events` Agent

**Files:**
- Create: `src/metaforge/agents/events.py`
- Test: `tests/test_agents_events.py`

- [ ] **Plan:** `parse_event` → `reschedule` → `delivery.explain_impact`

- [ ] **契约测试** `impact_report` 必含 `delay_details`, `commitment_changes`

- [ ] **API** `POST /api/agents/events/run`

---

## Phase 3：whatif + pipeline HITL

### Task 3.1: `compare.variants` Tool

**Files:**
- Create: `src/metaforge/tools/compare/variants.py`
- Test: `tests/test_tools_compare.py`

- [ ] 输入 `variants: [{label, scheduling: {...}, event: null}]`，循环 `scheduling.run`，输出 `what_if` 结构 + 简单推荐（最小 makespan 或最小 max tardiness，可配置）

---

### Task 3.2: `whatif` Agent

**Files:**
- Create: `src/metaforge/agents/whatif.py`
- Test: `tests/test_agents_whatif.py`

- [ ] **Plan:** `build_variants`（来自 `params.variants` 或 2 个 strategy_id）→ 循环 run → `compare.variants` → Reflect（差异 <1% 时 `summary_zh` 提示）

- [ ] **API** `POST /api/agents/whatif/run`

---

### Task 3.3: HITL 落库 API

**Files:**
- Modify: `tests/main.py`
- Create: `src/metaforge/tools/data/load_plan.py`
- Create: `src/metaforge/tools/data/propose_persist.py`
- Create: `src/metaforge/tools/data/confirm_persist.py`
- Test: `tests/test_hitl_persist.py`

- [ ] **`_pending_persist: Dict[str, dict]`** 内存 store（key=token，15min 过期）

- [ ] **`POST /api/db/propose_save`**

Body: `{ plan_id, schedule_result, delivery_assessment? }`  
Return: `{ confirm_token, expires_at, preview }`

- [ ] **`POST /api/db/confirm_save`**

Body: `{ confirm_token }` → `update_one` 写 `schedule_result` → 删 token

- [ ] **测试** 无 token 拒绝；有效 token 成功；过期 token 失败

---

### Task 3.4: `pipeline` Agent

**Files:**
- Create: `src/metaforge/agents/pipeline.py`
- Test: `tests/test_agents_pipeline.py`

- [ ] **Plan:** `data.load_plan` → `scheduling.run` → `delivery.assess` → `data.propose_persist` → 返回 `pending_confirm`

- [ ] **二次请求** `context.confirm_token` → 仅执行 `data.confirm_persist`

- [ ] **API** `POST /api/agents/pipeline/run`

---

### Task 3.5: 前端 HITL 确认卡片（可选同 Phase）

**Files:**
- Create: `frontend/src/components/PersistConfirmDialog.vue`
- Modify: `frontend/src/views/APSView.vue` 或新 `AgentChatView.vue`（最小：仅 pipeline 结果展示）

- [ ] 展示 `preview`：plan_name、makespan、high_risk_jobs

- [ ] 确认按钮调 `POST /api/db/confirm_save`

- [ ] `npm run build` 更新 `tests/templates/dist`

---

## Phase 4：编排收尾与文档

### Task 4.1: SessionStore

**Files:**
- Create: `src/metaforge/orchestrator/session.py`
- Modify: `tests/main.py`

- [ ] `create_session() -> session_id`

- [ ] `get/set artifacts`

- [ ] Orchestrator 响应带 `session_id`；`context.session_id` 可续跑

---

### Task 4.2: E2E 与回归

**Files:**
- Create: `tests/test_orchestrator_e2e.py`

- [ ] 6 条：`intent` 直达各 Agent（mock 重计算用最小 job）

- [ ] Router 无 intent 时关键词命中正确 `agent_id`

- [ ] 全量：`python -m pytest test_tools_*.py test_agents_*.py test_orchestrator_*.py test_api_smoke.py test_material_bom.py -q`

---

### Task 4.3: 文档更新

**Files:**
- Modify: `docs/改进计划.md`（增加多智能体 Phase 条目）
- Modify: `star.md`（`POST /api/orchestrator/run` 说明）
- Modify: `README.md`（Agent API 表）

---

## Phase 5–6（本计划不展开逐步骤，仅列入口）

| Phase | 内容 | 入口文件 |
|-------|------|----------|
| 5 LLM | `orchestrator/llm_planner.py`，按 Agent 启用 | 各 `agents/*.py` 的 `build_plan` 分支 |
| 6 MCP | `orchestrator/mcp_adapter.py` | `MCP_ENABLED` 环境变量 |

---

## Spec 覆盖自检

| Spec 要求 | 任务 |
|-------------|------|
| 6 Agent 1:1 | Task 1.2–1.3, 2.1, 2.4, 3.2, 3.4 |
| Router 不串多 Agent | Task 1.4 |
| Tool 先行 | Phase 0 |
| 扩展事件 A | Task 2.2–2.3 |
| HITL E | Task 3.3–3.5 |
| whatif D | Task 3.1–3.2 |
| tools/agents registry API | Task 0.6, 1.5 |
| 不接 LLM | Phase 5 隔离 |
| problem_builder 抽取 | Task 0.3 Step 3 |

---

## 执行顺序建议

```text
0.1 → 0.2 → 0.3 → 0.4 → 0.5 → 0.6
→ 1.1 → 1.2 → 1.3 → 1.4 → 1.5
→ 2.1 → 2.2 → 2.3 → 2.4
→ 3.1 → 3.2 → 3.3 → 3.4 → (3.5)
→ 4.1 → 4.2 → 4.3
```

**预估：** Phase 0–1 约 1 周；Phase 2 约 1–1.5 周；Phase 3–4 约 1 周（不含 LLM/MCP）。

---

## 执行方式

Plan 已保存至 `docs/superpowers/plans/2026-05-29-mes-multi-agent.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 按 Task 派发子 agent，每 Task 完成后 review  
2. **Inline Execution** — 在本会话用 executing-plans 按 Phase 批量实现并设检查点  

你更希望用哪种方式开始 Phase 0？
