# S3 前端三模式 + Package 结果页 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 `APSView` 内用 Mode A/B/C Tab 工作台替换旧 NL/权重排产入口，复用 S1/S2 API，展示完整 Package 结果。

**架构：** 后端为 `run_planning` / `/api/planning/run` 增加可选 `preset_id`（及可选 `strategy` 覆盖）；前端拆 `frontend/src/components/planning/*`，由 `PlanningWorkbench` 挂到 APSView；隐藏旧 weights/NL 面板。

**技术栈：** Vue 3 + Element Plus、FastAPI、pytest、`npm run build`（前端暂无 vitest：Node 小测 + build）

**规格：** [`docs/superpowers/specs/2026-08-03-planning-frontend-modes-design.md`](../specs/2026-08-03-planning-frontend-modes-design.md)

**工作目录：** `D:\Desktop\metaforge`（分支 `V1`）。PowerShell 用 `;`；`PYTHONPATH=src`。

**Mode A 锁定：** `preset_id` → 服务端 `strategy_from_preset`。

---

## 文件结构总览

| 路径 | 职责 |
|------|------|
| `src/metaforge/strategy/pipeline.py` | `run_planning` 支持 `preset_id` / `strategy` |
| `tests/main.py` | `/api/planning/run` 转发新字段 |
| `tests/strategy/test_preset_run.py` | Mode A 后端契约 |
| `frontend/src/components/planning/packageExtract.js` | Package 字段提取 |
| `frontend/src/components/planning/*.vue` | 结果/HITL/约束/三模式/Workbench |
| `frontend/src/views/APSView.vue` | 挂载 Workbench，移除旧面板 |
| `README.md` / `docs/多智能体开发进度.md` | S3 状态 |

---

### 任务 1：后端 `preset_id` / `strategy` 接入 run_planning

**文件：**
- 修改：`src/metaforge/strategy/pipeline.py`
- 修改：`tests/main.py`
- 测试：`tests/strategy/test_preset_run.py`

- [ ] **步骤 1：写失败测试**

```python
# tests/strategy/test_preset_run.py
from metaforge.strategy.pipeline import run_planning


def test_run_planning_with_preset_id_skips_nl_generate(monkeypatch):
    calls = {"generate": 0}

    def boom(**kwargs):
        calls["generate"] += 1
        raise AssertionError("generate_strategy should not be called when preset_id set")

    monkeypatch.setattr("metaforge.strategy.pipeline.generate_strategy", boom)

    def fake_finish(run_id, *, strategy, jobs, problem):
        return {
            "status": "COMPLETED",
            "run_id": run_id,
            "package": {
                "recommended_schedule_id": "edd",
                "strategy": strategy.to_dict(),
            },
        }

    monkeypatch.setattr("metaforge.strategy.pipeline._finish_planning", fake_finish)

    out = run_planning(
        user_goal="",
        jobs=[{"job_id": "A", "due_date": 20, "tasks": [{"machine_id": 0, "duration": 1}]}],
        machines=["0"],
        skip_strategy_hitl=True,
        preset_id="delivery",
    )
    assert calls["generate"] == 0
    assert out["status"] == "COMPLETED"
    assert out["package"]["strategy"]["base_template"] == "delivery"
    assert out["package"]["strategy"]["generated_by"] == "preset"


def test_run_planning_unknown_preset_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown preset"):
        run_planning(
            user_goal="",
            jobs=[],
            machines=[],
            skip_strategy_hitl=True,
            preset_id="not_a_real_preset",
        )
```

- [ ] **步骤 2：** `$env:PYTHONPATH="src"; pytest tests/strategy/test_preset_run.py -v` → FAIL

- [ ] **步骤 3：实现** — `run_planning` 增加 `preset_id` / `strategy`：有 strategy（dict→from_dict）用之；elif preset_id → strategy_from_preset；else generate_strategy。`tests/main.py` 转发字段，ValueError→HTTP 400。

- [ ] **步骤 4：** pytest 通过；`pytest tests/strategy/test_pipeline.py -q`

- [ ] **步骤 5：Commit** `feat(planning): support preset_id and strategy on run_planning`

---

### 任务 2：API 冒烟 — preset_id

**文件：** `tests/strategy/test_planning_api.py`

```python
def test_planning_run_preset_id(client, monkeypatch):
    def fake_run_planning(**kwargs):
        assert kwargs.get("preset_id") == "delivery"
        return {"status": "COMPLETED", "run_id": "r1", "package": {"recommended_schedule_id": "ts"}}

    monkeypatch.setattr("metaforge.strategy.pipeline.run_planning", fake_run_planning)
    r = client.post(
        "/api/planning/run",
        json={
            "preset_id": "delivery",
            "jobs": [{"job_id": "J1"}],
            "machines": ["M01"],
            "skip_strategy_hitl": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["package"]["recommended_schedule_id"] == "ts"
```

- [ ] Commit `test(api): cover planning run preset_id`

---

### 任务 3：packageExtract 纯函数

**文件：**
- `frontend/src/components/planning/packageExtract.js`
- `frontend/src/components/planning/packageExtract.test.mjs`

```js
import assert from 'node:assert/strict'
import { extractPackageView } from './packageExtract.js'

const view = extractPackageView({
  status: 'COMPLETED',
  package: {
    recommended_schedule_id: 'edd',
    strategy: { provenance: { simulated_fields: ['skill'] } },
    evaluation: {
      recommended_schedule_id: 'edd',
      recommendation_reason: 'ok',
      hard_violations: [],
      candidates: [{ schedule_id: 'edd', solver: 'edd', metrics: { makespan: 10 } }],
    },
  },
})
assert.equal(view.recommended_schedule_id, 'edd')
assert.equal(view.hasRecommendation, true)
console.log('packageExtract ok')
```

实现兼容顶层 `evaluation` / `candidate_schedules`。运行：`node frontend/src/components/planning/packageExtract.test.mjs`

- [ ] Commit `feat(ui): add packageExtract helper for S3 results`

---

### 任务 4：PackageResultPanel + StrategyHitlBar

**文件：** `PackageResultPanel.vue`、`StrategyHitlBar.vue`

- 结果：推荐/无推荐、metrics、违规、理由、候选表、simulated_fields
- HITL：emit approve / reject / edit-approve
- `cd frontend; npm run build`
- Commit `feat(ui): add PackageResultPanel and StrategyHitlBar`

---

### 任务 5：ConstraintEditor

**文件：** `ConstraintEditor.vue`

- v-model `{ hard_constraints, soft_constraints }`；catalog 分组；仅允许 catalog type
- Commit `feat(ui): add ConstraintEditor for Mode B`

---

### 任务 6：ModeTemplatePanel（A）

- GET presets；requireHitl 开关（默认关）；emit run `{ preset_id, skip_strategy_hitl }`
- Commit `feat(ui): add Mode A template panel`

---

### 任务 7：ModeParameterPanel（B）

- 权重 + critical_orders + ConstraintEditor + JSON；emit validate / run（默认需 HITL）
- Commit `feat(ui): add Mode B parameter panel`

---

### 任务 8：ModeAiPanel（C）

- NL + 三分析；emit collab run
- Commit `feat(ui): add Mode C AI panel`

---

### 任务 9：PlanningWorkbench + APSView

- Workbench：Tab；调 run/validate/collab；HITL；extractPackageView
- APSView：替换 planning-panel；删除 weights-panel / NL 入口。主甘特按钮可保留内部默认 weights，不展示旧面板。
- `npm run build`
- Commit `feat(ui): wire PlanningWorkbench into APSView and remove legacy NL panel`

---

### 任务 10：文档

- README / 进度 S3 ✅
- Commit `docs: mark S3 frontend modes as closed-loop`

---

### 任务 11：回归

```powershell
$env:PYTHONPATH="src"; pytest tests/planning_collab/ tests/strategy/ tests/test_api_smoke.py -q
cd frontend; npm run build
```

---

## 自检

| 规格 | 任务 |
|------|------|
| Mode A preset_id | 1–2, 6, 9 |
| Mode B 全量约束 | 5, 7, 9 |
| Mode C collab | 8, 9 |
| Package 结果 | 3–4, 9 |
| 隐藏旧 NL/权重 | 9 |
| 无甘特/trace | 遵守 |

---

## 执行注意事项

- 建议 worktree：`feat/planning-frontend-modes`
- PowerShell：`;`；`git commit -m "..."`
