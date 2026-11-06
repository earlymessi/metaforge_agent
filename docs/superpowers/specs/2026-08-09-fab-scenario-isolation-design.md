# FAB 场景与通用 JSSP 隔离设计

> 日期：2026-08-09  
> 状态：**待实现**（本文件定边界与契约；物理语义见 `2026-08-09-fab-mini-scenario-physics-design.md`）  
> 原则：**内容与约束隔离；代码可复用；默认路径零行为变化**

---

## 0. 目标与非目标

### 目标

1. APS 增加第三数据源 **「FAB 场景」**，与 `算例库` / `自定义/数据库` 并列。  
2. FAB 的场景包、约束类型、评价逻辑与通用 JSSP **内容隔离**。  
3. 求解器搜索壳、JobShop 基础模型、策略工作台 UI 壳 **允许复用**。  
4. `inputMode ∈ {file, custom}` 时：行为、约束目录、评价结果与改前 **比特级一致**（以现有 golden/strategy 测试为准）。

### 非目标

- 不改写 `data/benchmarks/*.txt` 格式，不把 FAB 包塞进算例库目录。  
- 不把 FAB 硬约束默认并入 `HARD_CONSTRAINT_TYPES`（通用 catalog）。  
- 不要求一期改 GA/TS 内核编码；批处理可用 FAB 专用解码/评价 + 后续专用求解。  
- 不等于 MES 执行仿真。

---

## 1. 隔离边界（硬规则）

```text
┌─────────────────────────────────────────────────────────┐
│  APS UI                                                  │
│  [算例库] [自定义/数据库] [FAB场景]   ← 互斥 inputMode     │
└─────────────┬───────────────┬───────────────┬───────────┘
              │ file          │ custom        │ fab
              ▼               ▼               ▼
     data/benchmarks/   custom jobs      data/fab_scenarios/
     /api/benchmarks    /api/db…         /api/fab/scenarios…
              │               │               │
              └───────┬───────┘               │
                      ▼                       ▼
              通用 JSSP 问题            FabScenarioPack
              domain=jssp               domain=fab
                      │                       │
                      ▼                       ▼
         strategy.catalog (通用)    fab.catalog (仅 FAB)
         strategy.evaluator         + fab.evaluate 钩子
                      │                       │
                      └───────────┬───────────┘
                                  ▼
                     solvers/* 搜索壳（复用，不改默认解码语义）
```

| 层 | 通用 JSSP | FAB | 隔离手段 |
|----|-----------|-----|----------|
| 数据文件 | `data/benchmarks/` | `data/fab_scenarios/` | 目录分离；API 分离 |
| 前端模式 | `file` / `custom` | `fab` | 新 `inputMode`；互不串 payload |
| 问题元数据 | 无 / 隐式 jssp | `domain: "fab"` + `scenario_id` | 显式标记 |
| 硬约束类型集合 | `strategy/catalog.py` | `fab/catalog.py` | **两套集合，默认不合一** |
| Guardrails | 只认通用类型 | `domain=fab` 时额外认 FAB 类型 | 分支，不污染默认 |
| Evaluator | 现有 hard 检查 | FAB 检查只在 `domain=fab` 调用 | 钩子 + 早退 |
| NL / AI catalog | 通用列表 | FAB 模式才注入 FAB 类型 | context 按 domain 组装 |
| 求解器 registry | 不变 | 可复用 id；可选 `fab_*` 包装 | 包装放 `fab/`，不改 `solvers/*.py` 默认路径 |

**禁止**：

- 在 `file`/`custom` 路径自动加载任何 `fab_scenarios` 包。  
- 在通用 `list_constraint_catalog()` 无参默认返回里混入 FAB 类型。  
- 修改 `JobShopProblem.evaluate(sequence)` 的默认语义以「顺便」支持批处理（会破坏 ft/la 口径）。

---

## 2. 包与目录布局

```text
src/metaforge/fab/                 # 新包：FAB 专用，依赖 strategy/problems，反向不依赖
  __init__.py
  catalog.py                       # FAB 硬/软约束类型 + 目标名
  models.py                        # FabScenarioPack, FabLot 扩展字段
  schema.py                        # 场景包校验（JSON Schema 或手写 validator）
  loader.py                        # 读 data/fab_scenarios/*.yaml|json
  to_planning.py                   # pack → planning jobs + default strategy + meta.domain=fab
  evaluate.py                      # dedication / timelink / batch_* 判定
  decode_hooks.py                  # （可选）批处理专用解码；默认 JSSP 解码不走这里

data/fab_scenarios/
  fab_photo_dedication_v1.yaml
  fab_etch_timelink_v1.yaml
  fab_diffusion_batch_v1.yaml

tests/fab/
  test_schema.py
  test_loader_isolation.py         # 断言 benchmarks API 不含 fab 文件
  test_evaluator_fab.py
  test_jssp_unaffected.py          # 跑既有 strategy golden 子集或 import 不改 catalog

frontend: APSView inputMode === 'fab' 面板（场景下拉 + 物理说明）
API（建议）:
  GET  /api/fab/scenarios
  GET  /api/fab/scenarios/{id}
  POST /api/fab/scenarios/{id}/load   → { jobs, strategy_defaults, meta }
```

通用模块仅允许的「薄接线」：

| 文件 | 允许改动 | 禁止 |
|------|----------|------|
| `strategy/catalog.py` | 可选增加 `list_constraint_catalog(domain=...)`，**默认参数行为不变** | 把 FAB 类型写进 `HARD_CONSTRAINT_TYPES` 常量 |
| `strategy/evaluator.py` | 若 `meta.domain=="fab"`，调用 `fab.evaluate.check_hard` | 无 domain 时走新逻辑 |
| `strategy/guardrails.py` | `domain=="fab"` 时 union FAB 类型集 | 默认校验集变大 |
| `strategy/context_builder.py` | 按 domain 选 catalog | 全局 prompt 永远带 FAB |
| APSView / run payload | `inputMode==='fab'` 分支 | 改 file/custom 默认 |

---

## 3. 场景包 Schema（契约）

### 3.1 顶层

```yaml
schema_version: "1"
scenario_id: fab_photo_dedication_v1   # 唯一
domain: fab                            # 恒为 fab
area: photolithography                 # diffusion_furnace | photolithography | etch_timelink
title: 光刻粘机 Mini-Fab
physics_refs: ["natural bias → overlay → machine dedication"]
out_of_scope: ["overlay nm simulation", "reticle full library"]

entities:
  machines: [...]
  families: [...]          # 扩散用；其他可 []
  lots: [...]              # 统一用 lots；导入时映射为 jobs

constraints_hard: [...]
constraints_soft: [...]      # 可空
objectives_default: {...}    # 权重 dict，与 SchedulingStrategy.objectives 对齐或子集

solver_hint:                 # 可选，不强制换核
  preferred_primary: ["ts", "ga"]
  notes: "dedication: reuse sequence solvers + fixed machine_id"
```

### 3.2 Lot → Job 映射（隔离扩展字段）

导入后仍产出现有 planning `jobs[]` 形状，**额外字段放在 job/task 上且仅 FAB 评价器读取**：

| 场景包字段 | 导入后位置 | 通用 JSSP 是否依赖 |
|------------|------------|-------------------|
| `lot.id` | `job_id` / `name` | 否（仅标识） |
| `family_id` | `job.family_id` | 否；通用忽略 |
| `layer_index` / `is_dedication_mark` | `task.*` | 否 |
| `process_area` | `task.process_area` | 否 |
| `max_lag` 边 | `meta.fab.timelinks[]` 或 strategy hard params | 否 |
| `max_batch_size` | `machine.max_batch_size` 或 meta | 否 |

通用 `build_problem_from_custom_jobs`：**只读已有字段**；未知键忽略。禁止为兼容 FAB 而改默认加工时间/机器语义。

### 3.3 FAB 约束类型（仅 `fab/catalog.py`）

**Hard**

| type | 场景 | params（要点） |
|------|------|----------------|
| `photo_machine_dedication` | 光刻 | `lot_id` 或全局；粘机规则 |
| `max_lag_between_ops` | 刻蚀/清洗链路 | `from_op`, `to_op`, `max_lag`（同一 job 内或按 id） |
| `batch_same_family` | 扩散 | （批内 family 一致） |
| `batch_capacity` | 扩散 | `max_batch_size` 或读机台属性 |
| `batch_synchronized` | 扩散 | 同批 start/end 一致 |

**Soft（可选）**

| type | 含义 |
|------|------|
| `prefer_batch_fill` | 满炉偏好 |
| `dedication_load_balance` | 粘机负载均衡 |

命名前缀策略：类型名本身已领域化（`photo_*` / `batch_*` / `max_lag_*`），**不**进入通用 `HARD_CONSTRAINT_TYPES`。

### 3.4 与通用策略对象的组装

`fab/to_planning.py` 输出：

```json
{
  "domain": "fab",
  "scenario_id": "fab_photo_dedication_v1",
  "jobs": [ /* 可喂 problem_resolve */ ],
  "machines": [ /* 可选 */ ],
  "strategy_defaults": {
    "hard_constraints": [{ "type": "photo_machine_dedication", "...": {} }],
    "soft_constraints": [],
    "objectives": { "makespan": 1.0 }
  },
  "fab_meta": {
    "area": "photolithography",
    "physics_refs": [],
    "out_of_scope": [],
    "timelinks": [],
    "batch_machines": []
  }
}
```

下游 `run_planning` / `/api/run`：仅当 payload 带 `domain: "fab"`（或 `inputMode` 映射）时启用 FAB guardrails + evaluator。

---

## 4. 评价与求解复用（不破坏 JSSP）

### 4.1 Evaluator

```text
evaluate_candidates(strategy, candidates, …, meta=None):
  hard_ok, viol = 通用 _check_hard_constraints(...)
  if meta and meta.get("domain") == "fab":
      ok2, viol2 = fab.evaluate.check_hard(strategy, candidates, fab_meta)
      hard_ok = hard_ok and ok2
      viol += viol2
  ...
```

- 通用约束与 FAB 约束可同时存在（FAB 包默认只带 FAB 类型）。  
- `domain` 缺失或非 `fab`：**零调用** `fab.evaluate`。

### 4.2 求解器

| 场景 | 一期 | 对原 solvers 的影响 |
|------|------|---------------------|
| Dedication | 导入时写死后续层 `machine_id`；跑现有 `ts`/`ga`/`spt`… | **无**（数据层约束） |
| Timelink | 现有序列求解 + FAB evaluator 拒绝对窗解 / 大惩罚排序 | **无核改**；可选后加罚函数包装于 `fab/` |
| Batch | 一期：专用构造启发式放 `fab/batch_construct.py`，或「非法即淘汰」；二期再批序列编码 | **禁止**改 `JobShopProblem.evaluate` 默认路径 |

包装模式（推荐）：

```python
# fab/solver_adapt.py — 可选
def run_with_fab_filter(solver_id, problem, strategy, fab_meta):
    result = run_solver(solver_id, problem)  # 原函数
    # 仅过滤/重打分，不修改 run_solver
    return result
```

### 4.3 回归护栏

- `tests/fab/test_jssp_unaffected.py`：  
  - `HARD_CONSTRAINT_TYPES` 不含任何 `batch_*` / `photo_*` / `max_lag_*`  
  - `list_constraint_catalog()` 默认长度/集合与快照一致  
- 既有 `tests/strategy/test_golden_*`、`test_evaluator_hard_soft.py` 必须继续绿。  
- `GET /api/benchmarks` 的 `files` 不得出现 `fab_` 场景文件。

---

## 5. 前端「FAB 场景」面板（行为）

1. `inputMode = 'fab'` 时：展示场景下拉（来自 `/api/fab/scenarios`），展示 `physics_refs` / `out_of_scope`。  
2. 「载入」调用 `/api/fab/scenarios/{id}/load`，填入工作台 jobs + strategy 默认硬约束；**不**改写算例库选中项。  
3. 切回 `file`/`custom`：清空 FAB `domain` 标记与 FAB 专用 strategy 约束（或整策略重置为通用模板），避免 FAB 约束泄漏进 ft06 运行。  
4. 运行 payload：`domain: 'fab'`, `scenario_id`, `custom_jobs`（或等价），**不**传 `benchmark_file`。

---

## 6. 验收标准

1. 未选 FAB 时：全量既有 strategy/benchmark 测试通过；约束目录无 FAB 类型。  
2. 选 FAB 并载入光刻包：策略含 `photo_machine_dedication`；跨机甘特 → `hard_ok=false`。  
3. 同一次会话从 FAB 切回算例库再跑 ft06：不携带 FAB hard 类型；结果形态与改前一致。  
4. 代码复用：FAB 路径调用现有 `run_solver` / `resolve_planning_problem`，无复制整套 GA。  
5. 文档口径：与物理规格 §7「贴合调度语义、不贴合物理场」一致。

---

## 7. 实现顺序（摘要）

1. `metaforge/fab/`：catalog + schema + loader + 三份场景包骨架（可先 YAML）。  
2. API ` /api/fab/scenarios*` + 隔离测试。  
3. `to_planning` + evaluator/guardrails **按 domain 接线**（默认 no-op）。  
4. APSView 第三按钮 + 切换清理。  
5. Dedication 评价闭环 → Timelink → Batch 构造/评价。  

详细勾选任务见：`docs/superpowers/plans/2026-08-09-fab-scenario-isolation.md`。
