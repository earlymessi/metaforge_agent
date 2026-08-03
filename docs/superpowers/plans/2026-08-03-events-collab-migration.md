# Events Collab 同构迁移 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用薄 `EventsCollabBridge` + `events_collab` 固定编排替换 `EventsAgentRunner` 主路径，保留看板 `/api/events/*` 与 Tool/重排内核不变。

**架构：** Bridge 实现 `BaseAgent.run` → 调用 `events_collab.pipeline.run_events`；pipeline 按固定阶段调用现有 Tools；产出 `events_trace`；Flag `EVENTS_COLLAB_V1` 默认开。验收后删除旧 Runner。

**技术栈：** Python 3.10+、现有 Tool 注册表、pytest、FastAPI

**规格：** [`docs/superpowers/specs/2026-08-03-events-collab-migration-design.md`](../specs/2026-08-03-events-collab-migration-design.md)

**工作目录：** `D:\Desktop\metaforge`。建议分支 `feat/events-collab-migration`。PowerShell：`;`；`PYTHONPATH=src;tests`。

## 实现锁定（规格二选一处）

| 项 | 锁定 |
|----|------|
| Flag | `EVENTS_COLLAB_V1` 默认 `1`；`0/false` 回退旧 Runner |
| 主路径 LLM plan | **不做**；纯固定编排 |
| `events_trace` 挂载 | `artifacts["events_trace"]`；Bridge/API `to_dict` 时同时写顶层 `events_trace` |
| Tool 调用 | 通过现有 Tool 注册（对齐 `BaseAgent`），禁止复制重排算法 |

---

## 文件结构

| 路径 | 职责 |
|------|------|
| `src/metaforge/events_collab/pipeline.py` | `run_events(...)` 固定阶段 |
| `src/metaforge/events_collab/trace.py` | `build_events_trace(...)` |
| `src/metaforge/events_collab/__init__.py` | 导出 |
| `src/metaforge/agents/events_collab_bridge.py` | 薄 Bridge |
| `src/metaforge/orchestrator/router.py` | `get_agent("events")` 按 Flag 选类 |
| `tests/main.py` | `/api/agents/events/run` 用 Bridge |
| `tests/events_collab/test_*.py` | 编排与 trace 单测 |
| 既有 events Agent 测试 | 改指向新路径 |
| 文档 | README / 进度 / 规格链到本 plan |

---

### 任务 1：`build_events_trace` + 包骨架

**文件：**
- 创建：`src/metaforge/events_collab/trace.py`
- 创建：`src/metaforge/events_collab/__init__.py`
- 测试：`tests/events_collab/test_events_trace.py`

- [ ] **步骤 1：失败测试**

```python
from metaforge.events_collab.trace import build_events_trace


def test_build_events_trace_minimal():
    tr = build_events_trace(
        status="success",
        stages=["parse", "reschedule", "explain"],
        event_type="machine_breakdown",
        tool_log=[{"tool": "events.reschedule", "ok": True}],
        warnings=[],
    )
    assert tr["status"] == "success"
    assert tr["event_type"] == "machine_breakdown"
    assert "events.reschedule" in [x["tool"] for x in tr["tool_log"]]
```

- [ ] **步骤 2：** 实现 → PASS
- [ ] **步骤 3：Commit** `feat(events-collab): add events_trace builder`

---

### 任务 2：`run_events` 固定编排（TDD，可注入 invoke_tool）

**文件：**
- 创建/修改：`src/metaforge/events_collab/pipeline.py`
- 测试：`tests/events_collab/test_pipeline.py`

```python
def run_events(
    *,
    message: str = "",
    context: dict | None = None,
    params: dict | None = None,
    invoke_tool=None,
) -> dict:
    """Return status/summary_zh/artifacts/pending_action/plan; artifacts include events_trace."""
```

阶段与规格 §4 一致。默认 `invoke_tool` 走真实 Tool（读 `agents/base.py`）。

- [ ] catalog 短路径：只调 `events.list_event_types`
- [ ] envelope + skip_parse：调用 reschedule，trace 含该步
- [ ] need_input：不调 reschedule

先读：`agents/events.py`、`agents/base.py`、`router.has_pending_insert_job_intake`

- [ ] Commit `feat(events-collab): add fixed-stage run_events pipeline`

---

### 任务 3：`EventsCollabBridge`

**文件：**
- 创建：`src/metaforge/agents/events_collab_bridge.py`
- 测试：`tests/events_collab/test_bridge.py`

对齐 `SchedulingCollabBridge`：`run()` → `run_events` → `AgentResponse`；保证 dict 含顶层或 artifacts 内 `events_trace`。

- [ ] Commit `feat(events-collab): add EventsCollabBridge`

---

### 任务 4：接入 router + API

**文件：**
- `orchestrator/router.py`：`_events_collab_enabled` + events 注册 Bridge
- `tests/main.py`：`agents_events_run` 经 `get_agent("events")`（保留 resource_config / production_execution 注入与 sync）

- [ ] Flag=1 → Bridge；API 响应含 `events_trace`
- [ ] Commit `feat(api): route events agent to collab bridge`

---

### 任务 5：更新既有 events Agent 测试

```powershell
Select-String -Path tests\*.py -Pattern "EventsAgentRunner"
```

主路径改 collab；可选保留 1 条 Flag=0 回退测。

- [ ] Commit `test(events-collab): point agent tests at collab path`

---

### 任务 6：删除旧 Runner 主路径

门槛：任务 2–5 绿 + events 相关回归绿。

- 删除 `EventsAgentRunner`（catalog regex 迁入 `events_collab`）
- 去掉 Flag 回退（与「禁止永久双跑」一致；若需缓冲，进度文档写明下一 PR）
- [ ] Commit `refactor(events): remove EventsAgentRunner main path`

---

### 任务 7：文档

- 规格链到本 plan；README / 进度：events 同构 ✅；backlog 余四领域
- plans/specs README 更新

```powershell
$env:PYTHONPATH="src;tests"
pytest tests/events_collab/ -q
# 外加 Select-String 找到的 events agent / extended 测试
```

- [ ] Commit `docs: mark events collab migration closed-loop`

---

## 执行注意

- 搬迁 intake/catalog 行为，避免回归
- Tool 失败 → `failed` + tool_log `ok=False`
- Windows：`git commit -m "..."`；每任务独立 commit
