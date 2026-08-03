# S4 仿真对接 + 扰动剧本 + R0/R1/R2 对比 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 薄适配打通 Package→MES 执行仿真、可配置扰动剧本、独立 R0/R1/R2 三甘特对比页与导出；按 P0→P1→P2 分期可验收交付。

**架构：** `package_to_execution` 桥接写入 plan.`schedule_result` 后调现有 `start_execution`；`metaforge.scenario` 提供剧本 CRUD + runner（逐步调 `dispatch_event_reschedule`）；前端 APS 按钮 + 看板 ScenarioPanel + `CompareView` 三甘特/导出。不新建仿真引擎。

**技术栈：** Python 3.10+、FastAPI、MongoDB、Vue 3、现有 jspdf、pytest

**规格：** [`docs/superpowers/specs/2026-08-03-sim-scenario-compare-design.md`](../specs/2026-08-03-sim-scenario-compare-design.md)

**工作目录：** `D:\Desktop\metaforge`。建议分支 `feat/s4-sim-scenario-compare`。PowerShell：`;`；`PYTHONPATH=src`。

**分期门禁：** P0 验收通过后再合 P1；P1 通过后再合 P2（同一分支可连续，但测试门禁按阶段）。

---

## 文件结构总览

| 路径 | 阶段 | 职责 |
|------|------|------|
| `src/metaforge/services/package_to_execution.py` | P0 | 从 package/run 提取甘特并落 plan、start |
| `tests/main.py` | P0–P2 | API 路由 |
| `tests/test_package_to_execution.py` | P0 | 桥接单测 |
| `frontend/.../PackageResultPanel.vue` | P0 | 「送入执行仿真」 |
| `frontend/.../PlanningWorkbench.vue` / `APSView` | P0 | 跳转看板 |
| `frontend/.../DashboardView.vue` | P0–P1 | auto_start；挂 ScenarioPanel |
| `src/metaforge/scenario/*` | P1 | 模型、预设、store、runner |
| `frontend/src/components/ScenarioPanel.vue` | P1 | 剧本 UI |
| `frontend/src/views/CompareView.vue` | P2 | 对比页 |
| `frontend/src/components/ImpactTripleGantt.vue` | P2 | 三甘特 |
| `frontend/src/router/index.js` | P2 | `/compare` |
| `README.md` / 进度文档 | P2 末 | S4 打勾 |

---

# ========== P0：Package → 执行 ==========

### 任务 1：提取推荐甘特纯函数

**文件：**
- 创建：`src/metaforge/services/package_to_execution.py`
- 测试：`tests/test_package_to_execution.py`

- [ ] **步骤 1：失败测试**

```python
from metaforge.services.package_to_execution import extract_recommended_gantt


def test_extract_recommended_gantt_from_package():
    package = {
        "recommended_schedule_id": "edd",
        "evaluation": {
            "recommended_schedule_id": "edd",
            "candidates": [
                {"schedule_id": "edd", "solver": "edd", "gantt_data": [{"Job": "A", "Start": 0, "Finish": 2}]},
            ],
        },
    }
    solver_id, gantt = extract_recommended_gantt(package=package, candidates=None)
    assert solver_id == "edd"
    assert len(gantt) == 1


def test_extract_fails_without_recommendation():
    import pytest
    with pytest.raises(ValueError, match="recommended"):
        extract_recommended_gantt(package={"recommended_schedule_id": None}, candidates=[])
```

也支持：`candidates` 在 run 顶层 `candidate_schedules`；`gantt_data` 在 candidate 上。

- [ ] **步骤 2：** pytest FAIL → 实现 `extract_recommended_gantt` → PASS
- [ ] **步骤 3：Commit** `feat(s4): extract recommended gantt from package`

---

### 任务 2：`start_from_package` 服务 + API

**文件：**
- 修改：`package_to_execution.py` 增加 `async def start_from_package(...)`
- 修改：`tests/main.py`
- 测试：扩展 `tests/test_package_to_execution.py`（可用 mongomock 或 monkeypatch coll）

**行为锁定：**

```python
async def start_from_package(
    execution_coll,
    orders_coll,
    *,
    package: dict | None = None,
    run_id: str | None = None,
    plan_id: str | None = None,
    persist_plan: bool = True,
    sim_speed: float = 60.0,
    jobs: list | None = None,
    plan_name: str = "Package 推荐计划",
) -> dict:
    # 1. 若 run_id：从 strategy.run_state.get_run 取 package/candidates
    # 2. extract_recommended_gantt
    # 3. 若 plan_id：更新该 order 的 schedule_result / schedule_results[solver]
    #    否则若 persist_plan：insert 新 order（jobs + schedule_result）
    #    否则 raise ValueError("plan_id required when persist_plan=false")
    # 4. return await start_execution(..., plan_id=..., solver_id=...)
```

`schedule_result` 形状与现网一致：`{ solver_id: { "gantt_data": [...], "metrics": {} } }` 或项目现用单快照格式——**先读** `resolve_plan_schedule_map` / 现有落库代码对齐。

API：

```python
@app.post("/api/execution/start_from_package")
async def execution_start_from_package(body: Dict = Body(...)):
    try:
        return await start_from_package(
            execution_collection,
            orders_collection,
            package=body.get("package"),
            run_id=body.get("run_id"),
            plan_id=body.get("plan_id"),
            persist_plan=bool(body.get("persist_plan", True)),
            sim_speed=float(body.get("sim_speed") or 60),
            jobs=body.get("jobs"),
            plan_name=body.get("plan_name") or "Package 推荐计划",
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
```

- [ ] 测试：无推荐 → 400；有 package+jobs+persist → 返回 execution 含 `baseline_gantt`（mock start_execution 亦可）
- [ ] Commit `feat(s4): start execution from planning package`

---

### 任务 3：APS「送入执行仿真」+ 看板 auto_start

**文件：**
- 修改：`PackageResultPanel.vue` — 按钮，emit `send-to-sim` 或内调需 props（`runId`/`package`/`jobs`）
- 修改：`PlanningWorkbench.vue` — 处理：`POST /api/execution/start_from_package`，成功后 `router.push({ path: '/dashboard', query: { from_package: '1' } })`
- 修改：`DashboardView.vue` — `onMounted`/watch query：若 `from_package=1` 则 `GET /api/execution/state` 刷新；已有选计划 start 保留

- [ ] `npm run build`
- [ ] Commit `feat(ui): send package to MES simulation from APS`

**P0 门禁：** `pytest tests/test_package_to_execution.py tests/test_production_execution.py -q` + build 通过。

---

# ========== P1：扰动剧本 ==========

### 任务 4：Scenario 模型与内存/Mongo store

**文件：**
- 创建：`src/metaforge/scenario/models.py` — dataclass Scenario, ScenarioStep
- 创建：`src/metaforge/scenario/presets.py` — 3 个预设（machine_breakdown / insert_order / due_date_change），`event_type` 与现网一致
- 创建：`src/metaforge/scenario/store.py` — 进程内 dict store（可后续换 Mongo；接口：`list/get/create/update/delete`）
- 测试：`tests/scenario/test_scenario_store.py`

```python
def test_scenario_crud_roundtrip():
    from metaforge.scenario.store import ScenarioStore
    from metaforge.scenario.presets import list_preset_scenarios
    store = ScenarioStore()
    for p in list_preset_scenarios():
        store.create(p)
    assert len(store.list()) >= 3
    s = store.list()[0]
    s2 = store.get(s["id"])
    assert s2["name"] == s["name"]
```

- [ ] Commit `feat(s4): add scenario model presets and store`

---

### 任务 5：Scenario runner

**文件：**
- 创建：`src/metaforge/scenario/runner.py`
- 测试：`tests/scenario/test_scenario_runner.py`

```python
def test_runner_stops_on_step_failure(monkeypatch):
    calls = []
    def fake_dispatch(envelope, event_type, params, **kw):
        calls.append(event_type)
        if event_type == "machine_breakdown":
            raise RuntimeError("boom")
        return {"ok": True, "impact_report": {}}

    monkeypatch.setattr("metaforge.scenario.runner.dispatch_event_reschedule", fake_dispatch)
    # 或 patch 实际 import 路径
    out = run_scenario(scenario_with_two_steps, envelope={})
    assert out["status"] == "failed"
    assert len(out["timeline"]) == 1
    assert out["timeline"][0]["status"] == "failed"
```

`run_scenario`：逐步调用；成功记 timeline；失败 break；返回最后 impact。

**注意：** 查清 `dispatch_event_reschedule` 真实签名（`event_reschedule.py`），按现网 envelope（含 `production_execution`）组装。

- [ ] Commit `feat(s4): scenario runner with fail-stop timeline`

---

### 任务 6：Scenarios API

**文件：** `tests/main.py`

```text
GET    /api/scenarios
POST   /api/scenarios
GET    /api/scenarios/{id}
PUT    /api/scenarios/{id}
DELETE /api/scenarios/{id}
POST   /api/scenarios/{id}/run
GET    /api/scenarios/presets   # 可选：只读预设模板
```

- [ ] 测试：`tests/scenario/test_scenario_api.py` CRUD + run mock
- [ ] Commit `feat(api): add /api/scenarios endpoints`

---

### 任务 7：ScenarioPanel UI

**文件：** `frontend/src/components/ScenarioPanel.vue`；挂到 `DashboardView.vue`

- 下拉预设 / 列表已存剧本
- JSON textarea 编辑 steps
- 保存、运行、timeline 展示
- 运行成功后按钮「打开对比」→ `/compare`（P2 路由可先占位或 query 暂存 impact 于 sessionStorage）

- [ ] `npm run build`
- [ ] Commit `feat(ui): add ScenarioPanel on dashboard`

**P1 门禁：** `pytest tests/scenario/ -q` + build。

---

# ========== P2：对比页 ==========

### 任务 8：ImpactTripleGantt + CompareView

**文件：**
- 创建：`frontend/src/components/ImpactTripleGantt.vue` — 三列，复用 Dual 的图层 props 模式
- 创建：`frontend/src/views/CompareView.vue` — 指标条 + Triple + 导出
- 修改：`frontend/src/router/index.js` — `{ path: 'compare', component: CompareView }`
- 工具：`frontend/src/utils/compareExport.js` — `buildCompareJson(impact)`；PDF 用已有 jspdf 写标题+指标表

数据：`sessionStorage['metaforge_last_impact']` 或 `route.query`；从 `impactReport.js` 已有 `effectiveR1Gantt` 等扩展 R0（baseline）提取。

- [ ] 纯函数测：`compareExport.test.mjs` 断言 JSON 含 R0/R1/R2 或 scenarios 键
- [ ] Commit `feat(ui): add CompareView with triple gantt and export`

---

### 任务 9：串起来入口

- ScenarioPanel / MesReschedulePanel 完成后写入 `sessionStorage` 并提供「打开对比页」
- Compare 空态文案

- [ ] Commit `feat(ui): link reschedule and scenarios to CompareView`

---

### 任务 10：文档 + 总回归

- README / `docs/多智能体开发进度.md`：S4 ✅，写明 P0/P1/P2
- 规格头「实现计划」链到本文件

```powershell
$env:PYTHONPATH="src"
pytest tests/test_package_to_execution.py tests/scenario/ tests/test_production_execution.py tests/planning_collab/ tests/strategy/ -q
cd frontend; npm run build
```

- [ ] Commit `docs: mark S4 sim scenario compare as closed-loop`

---

## 自检（对照规格）

| 规格 | 任务 |
|------|------|
| P0 bridge + 双入口 | 1–3 |
| P1 scenario CRUD/run/UI | 4–7 |
| P2 三甘特+导出+路由 | 8–9 |
| 文档与回归 | 10 |
| 无新仿真引擎 / 无定时后台 | 遵守 |

---

## 执行注意事项

- 先读 `production_execution.build_execution_doc` 与计划 `schedule_result` 真实形状再写写入逻辑
- `dispatch_event_reschedule` 签名以源码为准，勿臆造
- 每任务独立 commit；P0/P1/P2 各自门禁测试全绿再往下
- Windows：`git commit -m "..."`；`;` 连接命令
