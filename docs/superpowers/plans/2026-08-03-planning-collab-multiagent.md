# S2 Planning Collab Multi-Agent 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用 Planning Supervisor + Order/Constraint/Resource（规则结构 + LLM 摘要可跳过）替换 scheduling 主路径，分析结果喂入 S1 strategy pipeline，产出 Production Plan Package。

**架构：** 新建 `metaforge.planning_collab`；Orchestrator/APS 默认走 collab；`PLANNING_COLLAB_V1` 可短暂回退；验收后删除旧 SchedulingAgentRunner 主责路径。其余五 Agent 仅文档 backlog。

**技术栈：** Python 3.10+、现有 S1 `strategy.*`、FastAPI `tests/main.py`、pytest、可选 ThreadPool 并行

**规格：** [`docs/superpowers/specs/2026-08-03-planning-collab-multiagent-design.md`](../specs/2026-08-03-planning-collab-multiagent-design.md)

**工作目录：** `D:\Desktop\metaforge`（分支 `V1`）。PowerShell 用 `;`；`PYTHONPATH=src`。

---

## 文件结构总览

| 路径 | 职责 |
|------|------|
| `src/metaforge/planning_collab/protocol.py` | AgentTask / AgentResult / PlanningTaskState |
| `src/metaforge/planning_collab/agents/order.py` | 订单规则分析 |
| `src/metaforge/planning_collab/agents/constraint.py` | 硬/软约束候选 |
| `src/metaforge/planning_collab/agents/resource.py` | 资源/瓶颈粗估 |
| `src/metaforge/planning_collab/summarize.py` | LLM 摘要，失败返回 None |
| `src/metaforge/planning_collab/supervisor.py` | 编排 + 调 S1 |
| `src/metaforge/strategy/context_builder.py` | 消费分析 artifacts |
| `src/metaforge/strategy/generator.py` | 合并 critical/hard/soft |
| `tests/main.py` | `/api/planning/collab/*` |
| `src/metaforge/orchestrator/router.py` 或 agents 入口 | scheduling → collab |
| `tests/planning_collab/test_*.py` | 单测与 e2e |
| 文档 README / 进度 | backlog + S2 状态 |

---

### 任务 1：协议类型

**文件：**
- 创建：`src/metaforge/planning_collab/__init__.py`
- 创建：`src/metaforge/planning_collab/protocol.py`
- 测试：`tests/planning_collab/test_protocol.py`

- [ ] **步骤 1：写失败测试**

```python
# tests/planning_collab/test_protocol.py
from metaforge.planning_collab.protocol import AgentTask, AgentResult, PlanningTaskState


def test_task_state_roundtrip():
    state = PlanningTaskState.new(user_goal="保证A按期", jobs=[{"job_id": "A"}])
    d = state.to_dict()
    assert d["user_goal"] == "保证A按期"
    assert "artifacts" in d
    task = AgentTask(task_id="t1", agent_id="order", objective="分析订单", inputs={"jobs": []})
    assert task.agent_id == "order"
    res = AgentResult(agent_id="order", status="success", summary="ok", artifacts={"critical_orders": ["A"]})
    assert res.artifacts["critical_orders"] == ["A"]
```

- [ ] **步骤 2：pytest 确认 FAIL → 实现 dataclass + `to_dict`/`from_dict`/`PlanningTaskState.new`**

`PlanningTaskState` 字段对齐规格 §4.3；`artifacts` 默认空 dict。

- [ ] **步骤 3：Commit**

```powershell
git commit -m "feat(collab): add AgentTask/Result/PlanningTaskState protocol"
```

---

### 任务 2：Order Agent（规则）

**文件：**
- 创建：`src/metaforge/planning_collab/agents/__init__.py`
- 创建：`src/metaforge/planning_collab/agents/order.py`
- 测试：`tests/planning_collab/test_order_agent.py`

- [ ] **步骤 1：写失败测试**

```python
from metaforge.planning_collab.agents.order import run_order_agent
from metaforge.planning_collab.protocol import AgentTask


def test_order_agent_marks_critical_from_goal():
    task = AgentTask(
        task_id="1",
        agent_id="order",
        objective="分析",
        inputs={
            "user_goal": "优先保证客户A按期",
            "jobs": [
                {"job_id": "A", "customer": "A", "due_date": 10, "priority": 5},
                {"job_id": "B", "due_date": 100, "priority": 1},
            ],
        },
    )
    result = run_order_agent(task)
    assert result.status == "success"
    assert "A" in result.artifacts["critical_orders"]
```

- [ ] **步骤 2：实现规则**（due 窗口、priority、goal 关键词「保证X按期」/客户匹配）；`reasoning_summary=None`  
- [ ] **步骤 3：Commit** `feat(collab): add rule-based Order Agent`

---

### 任务 3：Constraint + Resource Agents

**文件：**
- 创建：`agents/constraint.py`、`agents/resource.py`
- 测试：`test_constraint_agent.py`、`test_resource_agent.py`

- [ ] Constraint：从 goal「减少换型」→ soft `reduce_changeover`；critical/order_on_time 来自 order_analysis 或 goal；类型必须在 S1 catalog，否则丢弃+warning  
- [ ] Resource：按 tasks.machine_id 统计负载，标 bottleneck（最高占用）；无 tasks 时 empty + warning  
- [ ] Commit：`feat(collab): add Constraint and Resource analysis agents`

---

### 任务 4：LLM 摘要（可跳过）

**文件：**
- 创建：`summarize.py`
- 测试：`test_summarize.py`

```python
def test_summarize_returns_none_on_failure():
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("down")
    assert summarize_agent_result({"critical_orders": ["A"]}, llm_client=Boom()) is None


def test_summarize_ok():
    class Ok:
        def complete(self, *a, **k):
            return "重点保证A"
    assert "A" in (summarize_agent_result({"critical_orders": ["A"]}, llm_client=Ok()) or "")
```

- [ ] 实现：无 client 或异常 → `None`；有 client 则短中文摘要（截断）  
- [ ] Commit：`feat(collab): optional LLM reasoning summary with skip-on-failure`

---

### 任务 5：Supervisor + 接入 S1

**文件：**
- 创建：`supervisor.py`
- 修改：`strategy/context_builder.py`、`strategy/generator.py`（接受并合并分析 artifacts）
- 测试：`test_supervisor.py`

- [ ] **步骤 1：测试**

```python
def test_supervisor_analyze_fills_artifacts(monkeypatch):
    from metaforge.planning_collab.supervisor import run_collab_analyze
    out = run_collab_analyze(
        user_goal="保证A按期，减少换型",
        jobs=[{"job_id": "A", "due_date": 10, "priority": 8, "tasks": [{"machine_id": 0, "duration": 2}]}],
        machines=["0"],
        llm_client=None,
    )
    arts = out["artifacts"]
    assert "order_analysis" in arts and "constraint_analysis" in arts and "resource_analysis" in arts


def test_supervisor_run_skip_hitl(monkeypatch):
    from metaforge.strategy.models import SolverPolicy
    def fast_policy(strategy, n_jobs=0):
        return SolverPolicy(["edd"], "spt", 2.0, 2, {}, "t")
    monkeypatch.setattr("metaforge.strategy.pipeline.build_solver_policy", fast_policy)
    from metaforge.planning_collab.supervisor import run_collab
    out = run_collab(
        user_goal="综合平衡",
        jobs=[{
            "job_id": "A", "name": "A", "priority": 10, "due_date": 50,
            "tasks": [{"machine_id": 0, "duration": 2}, {"machine_id": 1, "duration": 2}],
        }],
        machines=["0", "1"],
        skip_strategy_hitl=True,
        llm_client=None,
    )
    assert out["status"] == "COMPLETED"
    assert out.get("package", {}).get("recommended_schedule_id") is not None
```

- [ ] **步骤 2：实现 `run_collab_analyze` / `run_collab`**
  - 建 State；跑三 Agent（可用 `concurrent.futures.ThreadPoolExecutor`，也允许串行）
  - 对各成功 Result 调 summarize（可空）
  - `generate_strategy(..., order_analysis=..., constraint_analysis=..., resource_analysis=...)`
  - `run_planning(..., skip_strategy_hitl=...)`；把分析 artifacts 并入返回
- [ ] Generator 合并：`critical_orders`、hard/soft 从分析并入后再 `validate_strategy`  
- [ ] Commit：`feat(collab): supervisor wires analyses into S1 pipeline`

---

### 任务 6：API

**文件：** 修改 `tests/main.py`；测试 `tests/planning_collab/test_collab_api.py`

```text
POST /api/planning/collab/analyze
POST /api/planning/collab/run
GET  /api/planning/collab/runs/{id}
```

Flag：`PLANNING_COLLAB_V1` 默认 `"1"`；关闭时 404 或明确 disabled。

- [ ] Commit：`feat(api): add /api/planning/collab endpoints`

---

### 任务 7：替换 scheduling 路由

**文件：**
- 修改：`orchestrator/router.py` 的 `get_agent` **或** `tests/main.py` 中 `POST /api/agents/scheduling/run` / orchestrator run 分发处
- 修改：`agents/registry_meta.py`（scheduling 标注 `replaced_by=planning_collab` 或实现转发）
- 测试：扩展路由/agent 测试，scheduling 意图最终走到 collab

推荐实现：新增薄包装 `SchedulingCollabBridge` 作为 `get_agent("scheduling")` 返回值，内部调 `run_collab`；Flag=0 时返回旧 `SchedulingAgentRunner`。

- [ ] Commit：`feat(orchestrator): route scheduling intent to planning collab`

---

### 任务 8：APS UI 切到 collab

**文件：** `frontend/src/views/APSView.vue`

- 「智能排产运行」改为 `POST /api/planning/collab/run`（保留 HITL 字段兼容：若 collab 返回 WAITING_APPROVAL，HITL 仍走 S1 `/api/planning/runs/...`）
- 展示三分析摘要（可选折叠：order/constraint/resource）

- [ ] `npm run build`  
- [ ] Commit：`feat(ui): point APS smart planning to collab API`

---

### 任务 9：文档 + 废弃旧 scheduling 主路径

**文件：**
- `docs/多智能体开发进度.md`、`README.md`：S2 打勾；五 Agent 迁移 backlog  
- 删除或掏空：`SchedulingAgentRunner` 主流程（Flag=0 回退可先保留一版再删）  
- 更新 `registry_meta`；移除无引用遗留 `/api/agent/schedule`（确认无测试依赖）

删除前必须：`pytest tests/planning_collab/ tests/strategy/ tests/test_api_smoke.py tests/test_orchestrator_router.py -q` 全绿。

- [ ] Commit：`refactor: retire scheduling agent main path in favor of collab`  
- [ ] Commit：`docs: mark S2 collab done and record agent migration backlog`

---

## 自检（对照规格）

| 规格 | 任务 |
|------|------|
| 协议 | 1 |
| 三分析规则 | 2–3 |
| LLM 摘要可跳过 | 4 |
| Supervisor + S1 | 5 |
| API | 6 |
| 替换 scheduling 路由 | 7–8 |
| 删除旧路径 + backlog 文档 | 9 |
| 不上 LangGraph / 不换五 Agent | 遵守 |

---

## 执行注意事项

- 复用 S1：`generate_strategy` / `run_planning` / `problem_resolve` / HITL  
- 三分析失败默认降级；`COLLAB_FAIL_CLOSED=1` 可选  
- 每任务独立 commit；Windows 下 `;` 连接命令  
