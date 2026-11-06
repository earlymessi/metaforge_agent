# FAB 场景隔离 — 实现计划

> 规格：`docs/superpowers/specs/2026-08-09-fab-scenario-isolation-design.md`  
> 物理：`docs/superpowers/specs/2026-08-09-fab-mini-scenario-physics-design.md`

## 目标

APS 增加「FAB 场景」数据源；FAB 约束/数据与通用 JSSP 隔离；`file`/`custom` 行为不变。

## 任务

### Task 1：fab 包骨架 + catalog + schema

- [x] 新建 `src/metaforge/fab/`（`catalog.py`, `models.py`, `schema.py`, `loader.py`）
- [x] `HARD`/`SOFT` 仅定义在 `fab/catalog.py`
- [x] `data/fab_scenarios/` 下放三个 YAML 骨架（dedication / timelink / batch）
- [x] `tests/fab/test_schema.py`、`test_jssp_unaffected.py`（断言通用 `HARD_CONSTRAINT_TYPES` 不含 FAB 类型）

### Task 2：API 隔离

- [x] `GET /api/fab/scenarios`、`GET /api/fab/scenarios/{id}`、`POST .../load`
- [x] 确认 `/api/benchmarks` 不扫描 `fab_scenarios`
- [x] `tests/fab/test_loader_isolation.py`

### Task 3：to_planning + domain 接线

- [x] `fab/to_planning.py` → jobs + strategy_defaults + `domain=fab`
- [x] `guardrails` / `evaluator` / `context_builder`：**仅** `domain=="fab"` 时启用 FAB 类型与检查
- [x] 默认路径单测：无 domain 时与改前一致

### Task 4：前端第三按钮

- [x] `APSView`：`inputMode === 'fab'` 面板；切换回 file/custom 清理 FAB 约束
- [x] run payload 带 `domain` / `scenario_id`，不传 `benchmark_file`

### Task 5：评价闭环（按序）

- [x] `photo_machine_dedication` hard 判定
- [x] `max_lag_between_ops` hard 判定
- [x] `batch_*` 判定（无 `fab_batches` 时跳过，不改 `JobShopProblem.evaluate`）

## 验收

- 既有 `tests/strategy` golden / evaluator 全绿  
- FAB 载入后跨机 dedication → `hard_ok=false`  
- 切回算例库跑 ft06 无 FAB 约束泄漏  

## 非目标（本计划不做）

- 改 GA/TS 默认编码  
- 把 FAB 类型并入通用 `HARD_CONSTRAINT_TYPES`  
- MES 执行仿真联动  
