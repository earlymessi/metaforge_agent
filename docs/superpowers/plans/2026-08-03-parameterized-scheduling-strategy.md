# 参数化 SchedulingStrategy 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 落地独立 `metaforge.strategy` 模块与 `/api/planning/*`：NL/Preset → `SchedulingStrategy` → 轻量 SolverPolicy → 复用 `compare_solvers` → 硬/软评价 → Production Plan Package；含策略 HITL、Context Builder、Trace 与黄金测试；旧 scheduling 路径过渡期并行。

**架构：** 新建策略域模块，不经七 Agent Supervisor；固定流水线 `generate → HITL → solve → evaluate`。LLM 只产结构化策略（repair/retry/规则回退）；求解与硬约束校验保持确定性。Feature Flag `PLANNING_STRATEGY_V1` 控制新 API。

**技术栈：** Python 3.10+、Pydantic v2（若项目已有则用；否则 dataclass + 手写校验）、FastAPI（`tests/main.py`）、现有 Tool Registry / Session / SSE / `compare_solvers`、pytest、Vue `APSView.vue`

**规格：** [`docs/superpowers/specs/2026-08-03-parameterized-scheduling-strategy-design.md`](../specs/2026-08-03-parameterized-scheduling-strategy-design.md)

---

## 文件结构总览

| 路径 | 职责 |
|------|------|
| `src/metaforge/strategy/models.py` | `SchedulingStrategy`、`Constraint`、`SolverPolicy`、`EvaluationResult`、`PlanningRun` |
| `src/metaforge/strategy/presets.py` | 6 模板 → Preset（从 `STRATEGY_TEMPLATES` 适配，避免双份真相过久） |
| `src/metaforge/strategy/catalog.py` | 硬/软约束类型目录 + 去双计声明 |
| `src/metaforge/strategy/context_builder.py` | 策略生成用压缩上下文 |
| `src/metaforge/strategy/generator.py` | LLM + repair + rule_fallback |
| `src/metaforge/strategy/guardrails.py` | 实体存在性 / catalog 白名单 / 模拟注入 |
| `src/metaforge/strategy/adapters.py` | Strategy → weights / resource hints |
| `src/metaforge/strategy/capability_matrix.py` | Solver 能力视图（含 RL 限制） |
| `src/metaforge/strategy/solver_policy.py` | 轻量选 solver / budget / candidates |
| `src/metaforge/strategy/evaluator.py` | 硬淘汰 + 软惩罚 + 排名 |
| `src/metaforge/strategy/hitl.py` | 策略 approve/reject/edit |
| `src/metaforge/strategy/run_state.py` | `PlanningRun` 存取（内存，可后换 Mongo） |
| `src/metaforge/strategy/pipeline.py` | `/api/planning/run` 编排 |
| `src/metaforge/strategy/trace.py` | 策略链路 trace 块 |
| `src/metaforge/tools/planning/*.py` | 白名单 Tool |
| `tests/main.py` | `/api/planning/*` 路由 |
| `tests/strategy/test_*.py` | 单测与黄金场景 |
| `frontend/src/views/APSView.vue` | 轻量策略 UI |

---

### 任务 1：SchedulingStrategy 模型与 Preset

**文件：**
- 创建：`src/metaforge/strategy/__init__.py`
- 创建：`src/metaforge/strategy/models.py`
- 创建：`src/metaforge/strategy/presets.py`
- 测试：`tests/strategy/test_presets.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_presets.py
from metaforge.strategy.presets import list_presets, strategy_from_preset


def test_list_presets_has_six():
    ids = {p["id"] for p in list_presets()}
    assert ids >= {"balanced", "delivery", "cost", "balance_load", "makespan", "throughput"}


def test_strategy_from_preset_delivery_has_tardiness_weight():
    s = strategy_from_preset("delivery")
    assert s.base_template == "delivery"
    assert s.objectives["weighted_tardiness_total"] >= s.objectives["makespan"]
    assert s.generated_by == "preset"
```

- [ ] **步骤 2：运行测试验证失败**

```powershell
Set-Location D:\Desktop\metaforge
$env:PYTHONPATH="D:\Desktop\metaforge\src"
python -m pytest tests/strategy/test_presets.py -v
```

预期：`ModuleNotFoundError: No module named 'metaforge.strategy'`

- [ ] **步骤 3：编写最少实现代码**

`models.py` 使用 dataclass（与现有 Tool 风格一致）：

```python
# src/metaforge/strategy/models.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

@dataclass
class Constraint:
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    penalty: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": self.type, **self.params}
        if self.penalty is not None:
            d["penalty"] = self.penalty
        return d

@dataclass
class SchedulingStrategy:
    strategy_id: Optional[str] = None
    base_template: Optional[str] = None
    objectives: Dict[str, float] = field(default_factory=dict)
    hard_constraints: List[Constraint] = field(default_factory=list)
    soft_constraints: List[Constraint] = field(default_factory=list)
    critical_orders: List[str] = field(default_factory=list)
    machine_preferences: Dict[str, Any] = field(default_factory=dict)
    machine_limits: Dict[str, Any] = field(default_factory=dict)
    overtime_policy: Optional[Dict[str, Any]] = None
    freeze_policy: Optional[Dict[str, Any]] = None
    solver_preferences: Optional[Dict[str, Any]] = None
    generated_by: str = "user"
    explanation: str = ""
    provenance: Dict[str, Any] = field(default_factory=lambda: {"simulated_fields": []})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "base_template": self.base_template,
            "objectives": dict(self.objectives),
            "hard_constraints": [c.to_dict() for c in self.hard_constraints],
            "soft_constraints": [c.to_dict() for c in self.soft_constraints],
            "critical_orders": list(self.critical_orders),
            "machine_preferences": dict(self.machine_preferences),
            "machine_limits": dict(self.machine_limits),
            "overtime_policy": self.overtime_policy,
            "freeze_policy": self.freeze_policy,
            "solver_preferences": self.solver_preferences,
            "generated_by": self.generated_by,
            "explanation": self.explanation,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SchedulingStrategy":
        def _parse_constraints(items: Any) -> List[Constraint]:
            out: List[Constraint] = []
            for raw in items or []:
                if not isinstance(raw, dict):
                    continue
                t = str(raw.get("type") or "")
                penalty = raw.get("penalty")
                params = {k: v for k, v in raw.items() if k not in ("type", "penalty")}
                out.append(Constraint(type=t, params=params, penalty=penalty))
            return out
        return cls(
            strategy_id=data.get("strategy_id"),
            base_template=data.get("base_template"),
            objectives={k: float(v) for k, v in (data.get("objectives") or {}).items()},
            hard_constraints=_parse_constraints(data.get("hard_constraints")),
            soft_constraints=_parse_constraints(data.get("soft_constraints")),
            critical_orders=list(data.get("critical_orders") or []),
            machine_preferences=dict(data.get("machine_preferences") or {}),
            machine_limits=dict(data.get("machine_limits") or {}),
            overtime_policy=data.get("overtime_policy"),
            freeze_policy=data.get("freeze_policy"),
            solver_preferences=data.get("solver_preferences"),
            generated_by=str(data.get("generated_by") or "user"),
            explanation=str(data.get("explanation") or ""),
            provenance=dict(data.get("provenance") or {"simulated_fields": []}),
        )
```

`presets.py`：从 `metaforge.agent.scheduling_agent.STRATEGY_TEMPLATES` 读取 weights，组装 `SchedulingStrategy(generated_by="preset")`。

- [ ] **步骤 4：运行测试验证通过**

```powershell
python -m pytest tests/strategy/test_presets.py -v
```

预期：PASS

- [ ] **步骤 5：Commit**

```powershell
git add src/metaforge/strategy tests/strategy/test_presets.py
git commit -m "feat(strategy): add SchedulingStrategy model and presets"
```

---

### 任务 2：约束 Catalog 与 Guardrails

**文件：**
- 创建：`src/metaforge/strategy/catalog.py`
- 创建：`src/metaforge/strategy/guardrails.py`
- 测试：`tests/strategy/test_guardrails.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_guardrails.py
from metaforge.strategy.models import Constraint, SchedulingStrategy
from metaforge.strategy.guardrails import validate_strategy


def test_unknown_hard_type_rejected():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="not_a_real_type", params={"job_id": "A"})]
    )
    ok, errors, _ = validate_strategy(s, jobs=[{"job_id": "A"}], machines=["M01"], allow_simulated=True)
    assert ok is False
    assert any("not_a_real_type" in e for e in errors)


def test_order_on_time_missing_job_rejected():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="order_on_time", params={"job_id": "Z99"})]
    )
    ok, errors, _ = validate_strategy(s, jobs=[{"job_id": "A12"}], machines=["M01"], allow_simulated=True)
    assert ok is False


def test_skill_required_injects_simulated_when_allowed():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="skill_required", params={"job_id": "A12", "skill": "weld"})]
    )
    ok, errors, fixed = validate_strategy(
        s, jobs=[{"job_id": "A12"}], machines=["M01"], workers=[], allow_simulated=True
    )
    assert ok is True
    assert "skill_required" in (fixed.provenance.get("simulated_fields") or [])
```

- [ ] **步骤 2：运行确认 FAIL**

```powershell
python -m pytest tests/strategy/test_guardrails.py -v
```

- [ ] **步骤 3：实现 catalog + guardrails**

`catalog.py` 导出：

```python
HARD_CONSTRAINT_TYPES = {
    "order_on_time", "machine_unavailable", "frozen_operations",
    "precedence", "skill_required", "tooling_exclusive",
}
SOFT_CONSTRAINT_TYPES = {
    "reduce_changeover", "avoid_machine_overload", "load_balance",
    "schedule_stability", "prefer_overtime", "avoid_overtime",
    "prefer_outsourcing", "avoid_outsourcing", "energy_shift_preference",
}
# soft_type -> folds_into_objective or None
SOFT_FOLDS_INTO = {
    "reduce_changeover": "setup_changeover",
    "load_balance": "machine_busy_cv",
    "schedule_stability": "schedule_stability",
    "energy_shift_preference": "energy_cost",
}
```

`validate_strategy(...)` 返回 `(ok, errors, strategy_out)`：未知 type 失败；`order_on_time` / `machine_unavailable` 校验实体；`skill_required`/`tooling_exclusive` 在无 workers/tools 且 `allow_simulated` 时注入模拟并写 `simulated_fields`；`allow_simulated=False` 时缺数据则 `ok=False`。

- [ ] **步骤 4：pytest 通过后 Commit**

```powershell
git add src/metaforge/strategy/catalog.py src/metaforge/strategy/guardrails.py tests/strategy/test_guardrails.py
git commit -m "feat(strategy): add constraint catalog and guardrails"
```

---

### 任务 3：Context Builder + 规则 Generator

**文件：**
- 创建：`src/metaforge/strategy/context_builder.py`
- 创建：`src/metaforge/strategy/generator.py`
- 测试：`tests/strategy/test_generator_fallback.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_generator_fallback.py
from metaforge.strategy.context_builder import build_for_strategy_generation
from metaforge.strategy.generator import generate_strategy


def test_context_builder_omits_full_gantt():
    ctx = build_for_strategy_generation(
        user_goal="保证A按期",
        jobs=[{"job_id": "A", "due_date": 10, "priority": 5}],
        machines=["M01", "M02"],
        gantt_data=[{"job": "A", "op": 0}] * 500,
        bom={"items": list(range(200))},
    )
    blob = str(ctx)
    assert "保证A按期" in blob
    assert blob.count("job") < 50  # 摘要而非全量翻倍
    assert "items" not in blob or "bom_item_count" in blob


def test_rule_fallback_delivery_keywords():
    s, meta = generate_strategy(
        user_goal="优先交付，保证客户A按期，减少换型",
        jobs=[{"job_id": "A", "customer": "A", "due_date": 20}],
        machines=["M01"],
        llm_client=None,  # 强制规则
    )
    assert s.generated_by in ("rule_fallback", "preset", "llm")
    assert s.base_template in ("delivery", "balanced") or s.objectives.get("weighted_tardiness_total", 0) > 0
    assert meta.get("fallback") is True or s.generated_by == "rule_fallback"
```

- [ ] **步骤 2：运行确认 FAIL → 实现**

`context_builder`：返回 dict，含 `user_goal`（截断 500 字）、`orders_summary`（最多 30 条关键字段）、`machines_summary`、`constraint_catalog_short`、`preset_ids`、`bom_item_count`、`gantt_op_count`——**永不**内嵌完整 gantt/bom 数组。

`generator.generate_strategy`：
1. 若提供 `llm_client`，调用 JSON completion（system 要求只输出 SchedulingStrategy 字段）；
2. `SchedulingStrategy.from_dict` + `validate_strategy`；失败则 repair prompt 最多 2 次；
3. 仍失败或无 client → 规则：复用 `STRATEGY_NL` / delivery 关键词选 preset，解析「保证X按期」为 `order_on_time` + `critical_orders`，解析「减少换型」为 soft `reduce_changeover`。

- [ ] **步骤 3：pytest 通过后 Commit**

```powershell
git commit -m "feat(strategy): context builder and rule/LLM strategy generator"
```

---

### 任务 4：Adapters + Capability Matrix + SolverPolicy

**文件：**
- 创建：`src/metaforge/strategy/adapters.py`
- 创建：`src/metaforge/strategy/capability_matrix.py`
- 创建：`src/metaforge/strategy/solver_policy.py`
- 修改：`src/metaforge/utils/solver_registry.py`（`to_catalog_dict` 增加能力别名字段，或仅在 matrix 层映射）
- 测试：`tests/strategy/test_solver_policy.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_solver_policy.py
from metaforge.strategy.models import SchedulingStrategy
from metaforge.strategy.adapters import strategy_to_solver_inputs
from metaforge.strategy.solver_policy import build_solver_policy
from metaforge.strategy.capability_matrix import get_capability


def test_adapter_maps_objectives_to_weights():
    s = SchedulingStrategy(objectives={"makespan": 1.0, "weighted_tardiness_total": 2.5})
    weights, hints = strategy_to_solver_inputs(s)
    assert weights["weighted_tardiness_total"] == 2.5
    assert "resource_config_patch" in hints or isinstance(hints, dict)


def test_rl_marked_no_dynamic_weights():
    cap = get_capability("ppo")
    assert cap["supports_dynamic_weights"] is False
    assert cap["family"] == "rl"


def test_policy_prefers_metaheuristic_for_delivery():
    s = SchedulingStrategy(base_template="delivery", objectives={"weighted_tardiness_total": 2.0, "makespan": 0.8})
    policy = build_solver_policy(s, n_jobs=10)
    assert policy.max_candidates <= 3
    assert "ppo" not in policy.primary_solvers or get_capability("ppo")["supports_dynamic_weights"]
    assert policy.fallback_solver is not None
```

- [ ] **步骤 2：实现**

`SolverPolicy` dataclass 放入 `models.py`：

```python
@dataclass
class SolverPolicy:
    primary_solvers: List[str]
    fallback_solver: Optional[str]
    time_budget_seconds: float
    max_candidates: int
    parameters: Dict[str, Any]
    reason: str
```

`get_capability(solver_id)`：rule/metaheuristic → `supports_dynamic_weights` 跟随 `supports_weights_in_search`；rl → **强制 False**（诚实限制）。

`build_solver_policy`：默认 `["ts", "ga"]` + fallback `"edd"`；`max_candidates=3`；尊重 `solver_preferences`；排除宣称不支持动态权重却又被当成多目标主选的 RL。

`strategy_to_solver_inputs`：objectives → weights（只保留 compare_solvers 认识的键；未知键留在 strategy 供 evaluator）；`machine_unavailable` → `resource_config` downtime_blocks 提示。

- [ ] **步骤 3：Commit**

```powershell
git commit -m "feat(strategy): adapters, capability matrix, and solver policy"
```

---

### 任务 5：Evaluator（硬淘汰 + 软惩罚）

**文件：**
- 创建：`src/metaforge/strategy/evaluator.py`
- 测试：`tests/strategy/test_evaluator_hard_soft.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_evaluator_hard_soft.py
from metaforge.strategy.models import Constraint, SchedulingStrategy
from metaforge.strategy.evaluator import evaluate_candidates


def _cand(sid, completion_by_job, metrics, gantt=None):
    return {
        "schedule_id": sid,
        "solver": sid,
        "metrics": metrics,
        "completion_by_job": completion_by_job,
        "gantt_data": gantt or [],
    }


def test_hard_illegal_cannot_be_recommended():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="order_on_time", params={"job_id": "A", "due_date": 10})],
        objectives={"makespan": 1.0, "weighted_tardiness_total": 1.0},
    )
    cands = [
        _cand("bad", {"A": 20}, {"makespan": 20, "weighted_tardiness_total": 10, "energy_cost": 0, "machine_busy_cv": 0}),
        _cand("good", {"A": 8}, {"makespan": 30, "weighted_tardiness_total": 0, "energy_cost": 0, "machine_busy_cv": 0}),
    ]
    result = evaluate_candidates(s, cands, jobs=[{"job_id": "A", "due_date": 10}])
    assert result["recommended_schedule_id"] == "good"
    assert result["ranking"][0]["schedule_id"] == "good" or result["recommended_schedule_id"] == "good"


def test_all_illegal_returns_null_recommendation():
    s = SchedulingStrategy(
        hard_constraints=[Constraint(type="order_on_time", params={"job_id": "A", "due_date": 1})],
        objectives={"makespan": 1.0},
    )
    cands = [_cand("x", {"A": 99}, {"makespan": 99, "weighted_tardiness_total": 98, "energy_cost": 0, "machine_busy_cv": 0})]
    result = evaluate_candidates(s, cands, jobs=[{"job_id": "A", "due_date": 1}])
    assert result["recommended_schedule_id"] is None
    assert result["hard_violations"]
```

- [ ] **步骤 2：实现 evaluator**

对每个候选：
1. 检查 hard：`order_on_time` 用 `completion_by_job` vs due；`machine_unavailable` 扫 gantt 时段重叠；`frozen_operations` 对比冻结快照（无快照则 skip+warning）；skill/tooling 在本轮可用简化：若 provenance 含模拟则检查 gantt 未违反注入的互斥表，否则 warning。
2. `hard_ok=False` 的候选不得成为 recommended。
3. score = `compute_composite_score(metrics, weights=objectives_filtered)` + soft penalties（查 `SOFT_FOLDS_INTO`，已折叠的 soft 不再加 penalty）。
4. 输出 EvaluationResult dict：`recommended_schedule_id`, `ranking`, `hard_violations`, `soft_penalties`, `recommendation_reason`（模板字符串即可，LLM 理由留给 pipeline 可选）。

若 metrics 缺 `completion_by_job`，从 `gantt_data` 推导每 job 最大 end。

- [ ] **步骤 3：Commit**

```powershell
git commit -m "feat(strategy): candidate evaluator with hard/soft scoring"
```

---

### 任务 6：PlanningRun 状态机 + 策略 HITL

**文件：**
- 创建：`src/metaforge/strategy/run_state.py`
- 创建：`src/metaforge/strategy/hitl.py`
- 测试：`tests/strategy/test_strategy_hitl.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_strategy_hitl.py
from metaforge.strategy.run_state import create_run, get_run
from metaforge.strategy.hitl import approve_strategy, reject_strategy, edit_and_approve
from metaforge.strategy.models import SchedulingStrategy


def test_approve_moves_to_running_or_ready():
    run = create_run(user_goal="test")
    run["strategy_draft"] = SchedulingStrategy(base_template="balanced", objectives={"makespan": 1.0}).to_dict()
    run["status"] = "WAITING_APPROVAL"
    out = approve_strategy(run["run_id"])
    assert out["status"] in ("RUNNING", "APPROVED", "SOLVING")
    assert get_run(run["run_id"])["strategy_approved"] is not None


def test_reject_cancels():
    run = create_run(user_goal="test")
    run["status"] = "WAITING_APPROVAL"
    run["strategy_draft"] = {"objectives": {"makespan": 1.0}}
    out = reject_strategy(run["run_id"], reason="nope")
    assert out["status"] in ("CANCELLED", "FAILED")


def test_edit_and_approve_replaces_draft():
    run = create_run(user_goal="test")
    run["status"] = "WAITING_APPROVAL"
    run["strategy_draft"] = {"objectives": {"makespan": 1.0}}
    edited = SchedulingStrategy(base_template="delivery", objectives={"makespan": 0.8, "weighted_tardiness_total": 2.0})
    out = edit_and_approve(run["run_id"], edited.to_dict(), jobs=[], machines=[])
    assert out["strategy_approved"]["base_template"] == "delivery"
```

- [ ] **步骤 2：实现内存 store**

```python
# run_state.py 核心 API
def create_run(**fields) -> dict: ...
def get_run(run_id: str) -> dict: ...
def update_run(run_id: str, **patch) -> dict: ...
```

状态枚举字符串与规格一致：`PENDING|RUNNING|WAITING_APPROVAL|COMPLETED|FAILED|CANCELLED`。

`edit_and_approve` 必须调用 `validate_strategy`；失败保持 `WAITING_APPROVAL` 并返回 errors。

- [ ] **步骤 3：Commit**

```powershell
git commit -m "feat(strategy): planning run state and strategy HITL"
```

---

### 任务 7：Pipeline 编排 + Trace

**文件：**
- 创建：`src/metaforge/strategy/pipeline.py`
- 创建：`src/metaforge/strategy/trace.py`
- 修改：`src/metaforge/orchestrator/execution_trace.py`（增加 `build_strategy_trace_block` 或由 trace.py 产出可 merge 的 block）
- 测试：`tests/strategy/test_pipeline.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_pipeline.py
from metaforge.strategy.pipeline import run_planning


def test_pipeline_skip_hitl_returns_package(monkeypatch):
    # monkeypatch compare / solvers 为假候选，避免长时间求解
    def fake_solve(strategy, problem, policy):
        return [{
            "schedule_id": "ts",
            "solver": "ts",
            "metrics": {"makespan": 10, "weighted_tardiness_total": 0, "energy_cost": 0, "machine_busy_cv": 0.1},
            "completion_by_job": {"A": 5},
            "gantt_data": [],
        }]
    monkeypatch.setattr("metaforge.strategy.pipeline.solve_candidates", fake_solve)
    pkg = run_planning(
        user_goal="综合平衡",
        jobs=[{"job_id": "A", "due_date": 20, "operations": []}],
        machines=["M01"],
        skip_strategy_hitl=True,
        llm_client=None,
    )
    assert pkg["status"] == "COMPLETED"
    assert pkg.get("package", {}).get("recommended_schedule_id") is not None or pkg.get("evaluation")
```

- [ ] **步骤 2：实现 `run_planning`**

顺序：
1. `create_run` → stage=generate  
2. `generate_strategy` → guardrails  
3. 若非 `skip_strategy_hitl`：status=`WAITING_APPROVAL`，返回 run（含 draft）；调用方后续 approve 再 `resume_planning(run_id)`  
4. `build_solver_policy` → `solve_candidates`（内部：`strategy_to_solver_inputs` + 对 primary_solvers 调 `run_single_solver` / 精简版 compare；捕获单求解失败）  
5. `evaluate_candidates`  
6. 组装 Package + `build_strategy_trace`  
7. status=`COMPLETED`

`solve_candidates` 放在 `pipeline.py` 或 `adapters` 旁；**不要**改 Solver 内核。

- [ ] **步骤 3：Commit**

```powershell
git commit -m "feat(strategy): planning pipeline and strategy trace"
```

---

### 任务 8：ToolSpec 可选字段 + planning Tools

**文件：**
- 修改：`src/metaforge/tools/base.py`
- 创建：`src/metaforge/tools/planning/__init__.py`（注册全部）
- 创建：`src/metaforge/tools/planning/strategy_generate.py`
- 创建：`src/metaforge/tools/planning/strategy_validate.py`
- 创建：`src/metaforge/tools/planning/strategy_evaluate.py`
- 创建：`src/metaforge/tools/planning/run.py`
- 修改：`src/metaforge/tools/load_all.py`
- 修改：`src/metaforge/tools/registry.py`（list_tools 带出可选字段）
- 测试：`tests/strategy/test_planning_tools.py`

- [ ] **步骤 1：扩展 ToolSpec**

```python
@dataclass
class ToolSpec:
    name: str
    description_zh: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    handler: ToolHandler
    timeout_seconds: Optional[float] = None
    retry_policy: Optional[Dict[str, Any]] = None
    risk_level: str = "allow"  # allow | ask | deny
    idempotency_key_fields: Optional[List[str]] = None
    permission: Optional[str] = None
```

旧 Tool 不传新字段，默认兼容。

- [ ] **步骤 2：实现 planning tools**

| Tool | risk_level | 行为 |
|------|------------|------|
| `planning.strategy_generate` | ask | 调 generator |
| `planning.strategy_validate` | allow | 调 guardrails |
| `planning.strategy_evaluate` | allow | 调 evaluator |
| `planning.run` | ask | 调 pipeline（默认需要 HITL，除非 params.skip_strategy_hitl） |

- [ ] **步骤 3：测试 registry 含新 tool + Commit**

```powershell
python -m pytest tests/strategy/test_planning_tools.py tests/test_tools_registry.py -v
git commit -m "feat(planning): register planning tools with risk_level"
```

---

### 任务 9：FastAPI `/api/planning/*` + Feature Flag

**文件：**
- 修改：`tests/main.py`（在 agents 路由附近新增 planning 路由）
- 测试：`tests/strategy/test_planning_api.py`、更新 `tests/test_api_smoke.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/strategy/test_planning_api.py
import os
from fastapi.testclient import TestClient


def test_planning_routes_behind_flag(monkeypatch):
    monkeypatch.setenv("PLANNING_STRATEGY_V1", "1")
    from main import app  # tests/main.py
    client = TestClient(app)
    r = client.get("/api/planning/strategy/presets")
    assert r.status_code == 200
    assert len(r.json()["presets"]) >= 6


def test_generate_and_run_skip_hitl(monkeypatch):
    monkeypatch.setenv("PLANNING_STRATEGY_V1", "1")
    from main import app
    client = TestClient(app)
    # 使用最小 jobs；若求解过慢可再 monkeypatch pipeline
    payload = {
        "user_goal": "综合平衡排程",
        "jobs": [{"job_id": "J1", "name": "J1", "priority": 1, "operations": [{"machine": 0, "time": 2}]}],
        "skip_strategy_hitl": True,
        "benchmark_file": None,
    }
    r = client.post("/api/planning/run", json=payload)
    assert r.status_code in (200, 202)
    body = r.json()
    assert body.get("run_id") or body.get("package")
```

- [ ] **步骤 2：实现路由**

```python
def _planning_enabled() -> bool:
    return os.getenv("PLANNING_STRATEGY_V1", "1").strip() not in ("0", "false", "False")

@app.get("/api/planning/strategy/presets")
def planning_presets():
    if not _planning_enabled():
        raise HTTPException(404, "planning strategy v1 disabled")
    ...

@app.post("/api/planning/strategy/generate")
@app.post("/api/planning/strategy/validate")
@app.post("/api/planning/strategy/evaluate")
@app.post("/api/planning/run")
@app.get("/api/planning/runs/{run_id}")
@app.post("/api/planning/runs/{run_id}/strategy/approve")
@app.post("/api/planning/runs/{run_id}/strategy/reject")
@app.post("/api/planning/runs/{run_id}/strategy/edit_and_approve")
@app.get("/api/planning/constraints/catalog")
```

Flag 关闭时上述路由 404（或统一 disabled JSON）。默认 `"1"` 便于开发；若需保守默认改为 `"0"` 并在 `.env.example` 写明。

- [ ] **步骤 3：smoke 测试增加路径断言；Commit**

```powershell
git commit -m "feat(api): add /api/planning strategy endpoints"
```

---

### 任务 10：黄金场景测试

**文件：**
- 创建：`tests/strategy/test_golden_critical_order.py`
- 创建：`tests/strategy/test_golden_all_illegal.py`
- 创建：`tests/strategy/test_golden_template_compat.py`

- [ ] **步骤 1：实现三组黄金测试（可 fake solve）**

1. **模板兼容：** `strategy_from_preset("delivery").objectives` 与 `STRATEGY_TEMPLATES` delivery weights 一致。  
2. **关键订单：** 构造两候选，仅合法者含按期 A → recommended 为合法者。  
3. **全员非法：** recommended is None。  
4. （可选同文件）**LLM 失败回退：** monkeypatch llm 抛错 → `generated_by=rule_fallback`。

```powershell
python -m pytest tests/strategy/ -v
```

预期：全部 PASS

- [ ] **步骤 2：Commit**

```powershell
git commit -m "test(strategy): add golden scenarios for parameterized strategy"
```

---

### 任务 11：轻量前端（APSView）

**文件：**
- 修改：`frontend/src/views/APSView.vue`
- 可选：`frontend/src/api/planning.ts`（若项目有 api 模块习惯则新建）

- [ ] **步骤 1：在「策略与运行」卡片增加区块**

- 自然语言目标 `el-input` textarea  
- 按钮「AI 生成策略」→ `POST /api/planning/strategy/generate`  
- Strategy JSON `<el-input type="textarea" readonly>` 或折叠面板  
- HITL：`批准` / `拒绝` / `编辑后批准`（编辑可用 JSON textarea）  
- 「智能排产运行」→ `POST /api/planning/run`（`skip_strategy_hitl` 在已批准后为 true，或先 run 再轮询 `WAITING_APPROVAL`）  
- 结果区展示：`recommended_schedule_id`、hard_violations、recommendation_reason、simulated_fields  

保留原有模板下拉与 `/api/run` 路径，不删除。

- [ ] **步骤 2：本地验证**

```powershell
cd D:\Desktop\metaforge\frontend
npm run build
```

预期：构建成功

- [ ] **步骤 3：Commit**

```powershell
git commit -m "feat(ui): light planning strategy panel on APS view"
```

---

### 任务 12：SSE Trace 挂接 + 文档收尾

**文件：**
- 修改：`src/metaforge/orchestrator/execution_trace.py` 或 stream 合并点  
- 修改：`docs/多智能体开发进度.md`（简短增加 Planning Strategy V1 条目）  
- 修改：规格文首状态 → `已批准 / 实现中`

- [ ] **步骤 1：** `pipeline` 产出的 strategy trace block 能被现有 SSE merge（若 `/api/planning/run` 暂无 SSE，则 Package 内嵌 `execution_trace`；可选后续加 stream 端点）。  
- [ ] **步骤 2：** 全量策略测试

```powershell
python -m pytest tests/strategy/ tests/test_api_smoke.py -v --tb=short
```

- [ ] **步骤 3：Commit**

```powershell
git commit -m "docs: note planning strategy v1 progress and wire strategy trace"
```

---

## 自检（对照规格）

| 规格章节 | 对应任务 |
|----------|----------|
| SchedulingStrategy / Preset | 任务 1 |
| Catalog / 硬软扩展集 / 模拟 | 任务 2 |
| Context Builder / Generator | 任务 3 |
| Adapter / SolverPolicy / Capability | 任务 4 |
| Evaluator 深度 B | 任务 5 |
| HITL + PlanningRun | 任务 6 |
| Pipeline + Trace | 任务 7、12 |
| Tools + ToolSpec | 任务 8 |
| API + Flag | 任务 9 |
| 黄金测试 | 任务 10 |
| 轻量 UI | 任务 11 |
| 不上 LangGraph/MCP/七 Agent/改 Solver 内核 | 全任务遵守 |
| 旧路径可删门槛 | 本计划不执行删除；仅并行（符合规格 §11） |

占位符扫描：无 TODO/待定实现步骤。  
类型名统一：`SchedulingStrategy`、`SolverPolicy`、`Constraint`、`PlanningRun` 状态字符串与规格一致。

---

## 执行注意事项

- 工作目录：`D:\Desktop\metaforge`；测试时设 `PYTHONPATH=src`（或按 `pyproject.toml` / 现有 conftest）。  
- Windows PowerShell：用 `;` 连接命令，不用 `&&`。  
- 求解黄金测试优先 monkeypatch，避免 CI 长时间跑 GA/TS。  
- 每任务一次 commit；失败不要 amend 已推送提交。  
