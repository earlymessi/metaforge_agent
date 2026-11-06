# FAB 研究台（独立页）设计规格

> 日期：2026-08-09  
> 状态：实现中  
> 相关：`2026-08-09-fab-scenario-isolation-design.md`、`2026-08-09-fab-mini-scenario-physics-design.md`

## 1. 定位

独立研究页「FAB 研究台」：业务物理 → 形式化建模 → FAB 专用求解 → 约束可解释结果。  
与 APS「算例库 / 自定义 + 勾选 GA/TS」彻底分离。

一期：建模可视 + FAB 启发式/评价解释。  
训练：阶段占位，`POST /api/fab/research/train` → `not_implemented`（二期）。

## 2. 入口

- 侧栏「调度排程」→ **FAB 研究台**（`/fab-lab`）
- APS **不保留** FAB 数据源；可链到研究台

## 3. 五阶段 UI

`业务 → 建模 → 求解 → 结果 → 训练(二期)`

| 阶段 | 内容 |
|------|------|
| 业务 | 场景载入、physics_refs、out_of_scope、失效模式文案 |
| 建模 | 机台/Lot/工序表、硬软约束、工艺环示意 |
| 求解 | 按 area 方法卡（非通用 solver 清单） |
| 结果 | 甘特、fab_hard_ok、违反解释、method_trace |
| 训练 | disabled + 二期说明 |

## 4. API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/fab/scenarios` | 已有 |
| POST | `/api/fab/scenarios/{id}/load` | 已有 → planning payload |
| GET | `/api/fab/research/methods?area=` | 方法卡列表 |
| POST | `/api/fab/research/solve` | FAB 专用求解 |
| POST | `/api/fab/research/train` | 一期 `not_implemented` |

### 4.1 solve 请求

```json
{
  "scenario_id": "fab_photo_dedication_v1",
  "method": "dedication_bind_spt",
  "params": {}
}
```

### 4.2 solve 响应（要点）

```json
{
  "domain": "fab",
  "scenario_id": "...",
  "method": "...",
  "model_snapshot": { "jobs": [], "machines": [], "constraints_hard": [], "fab_meta": {} },
  "method_trace": [
    { "step": "physics", "detail": "..." },
    { "step": "constraints", "detail": "..." },
    { "step": "encode_decode", "detail": "..." },
    { "step": "hard_check", "detail": "..." },
    { "step": "metrics", "detail": "..." }
  ],
  "schedule": { "gantt_data": [], "metrics": {}, "fab_batches": null },
  "fab_evaluation": { "ranking": [], "hard_violations": [], "recommended_schedule_id": "..." }
}
```

### 4.3 方法 ID（一期）

| area | method | 说明 |
|------|--------|------|
| photolithography | `dedication_bind_spt` / `dedication_bind_edd` | 粘机绑定 + SPT/EDD |
| etch_timelink | `timelink_slack_spt` / `timelink_edd` | 窗敏感优先级 + 规则 |
| diffusion_furnace | `batch_construct` | 同族组批 + 批排序 |

## 5. 隔离

- 不改 `JobShopProblem.evaluate` 默认语义  
- FAB 类型仍只在 `fab/catalog.py`  
- 不把 FAB method 注册进通用 solver catalog  

## 6. 验收

侧栏进研究台 → 载入光刻 → 业务/建模有细节 → 方法卡求解 → 结果可解释；训练不可跑；APS 无 FAB 按钮。
