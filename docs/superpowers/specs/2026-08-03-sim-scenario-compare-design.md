# S4 仿真对接 + 扰动剧本 + R0/R1/R2 对比强化 设计规格

> 状态：已批准（头脑风暴 2026-08-03）  
> 前置：S1/S2/S3 ✅  
> 交付方式：单规格，**P0 → P1 → P2** 分期实现（各阶段可独立验收）  
> 实现计划：待 `writing-plans` 产出（可按阶段拆 plan 或一份 plan 分任务块）

---

## 1. 背景与目标

S3 已能产出 Production Plan Package。MES 侧已有 `production_execution` 倍速仿真与 `event_reschedule` 的 R0/R1/R2，但：

- Package 推荐计划 **不能一键**进入执行态  
- 扰动依赖手工点看板事件，**缺少可保存复现的剧本**  
- 对比主要在 `MesReschedulePanel` / 双甘特，**缺少独立三甘特对比页与导出**

**本轮目标：** 薄适配复用现网执行/重排内核，打通「推荐→仿真→可配置扰动→三方案对比导出」。

**本轮不做：** 新仿真引擎、后台定时无人值守跑剧本、LangGraph/MCP、替换 `event_reschedule` 算法内核。

---

## 2. 已确认决策

| 决策项 | 结论 |
|--------|------|
| 总范围 | Package→仿真 + 可配置扰动 + R0/R1/R2 强化 |
| 规格组织 | **一个规格**，P0/P1/P2 分期交付 |
| 架构 | **薄适配**：桥接 + scenario 小模块；复用 execution/events |
| P0 入口 | **双入口**：APS Package「送入执行仿真」+ 看板从计划库重选启动 |
| P1 扰动 | 预设 2–3 个剧本 + **可配置 JSON**（保存/加载）；一键按步调现有 events API |
| P2 对比 | **独立对比页** + **三甘特并排** + 指标条 + **导出 PDF/JSON** |
| 不做 | 真·后台定时自动扰动（原选项 C） |

---

## 3. 分期定义

### 3.1 P0 — Package → 执行仿真

1. 从 Package / planning run 取 `recommended_schedule_id` 对应候选的 `gantt_data`（及 solver_id）。  
2. Bridge：将甘特写入（或更新）计划文档 `schedule_result`，再调用现有 `start_execution(plan_id, solver_id)`。  
3. 若尚无 plan：支持 `persist_plan=true` 创建/更新临时或正式计划后再 start（与落库语义对齐，实现计划锁定具体集合字段）。  
4. APS：`PackageResultPanel` 增加「送入执行仿真」→ 调 bridge → 路由到看板（query 可带 `auto_start=1`）。  
5. 看板：保留/强化从计划库选择计划并 `POST /api/execution/start`；支持接收 APS 跳转后自动刷新执行态。

### 3.2 P1 — 可配置扰动剧本

1. Scenario 模型：`{ id, name, steps: [{ t?, event_type, params }], created_at, ... }`。  
2. 内置预设：至少 **设备故障 / 插单 / 改交期** 各一（或组合短剧本）。  
3. API：CRUD + `POST /api/scenarios/{id}/run`（顺序执行步骤，调用现有 `dispatch_event_reschedule` 或 events REST 等价路径）。  
4. UI：`ScenarioPanel`（看板侧）— 选预设、编辑 JSON、保存/加载、运行、timeline 日志。  
5. 某步失败：停止后续步骤，timeline 标记 failed，保留已有 impact。

### 3.3 P2 — R0/R1/R2 对比强化

1. 新路由例如 `/new-ui/compare`（或现有 router 惯例）。  
2. 输入：最近一次 impact_report / query 传入的 impact 快照。  
3. UI：R0、R1、R2 **三列甘特并排**（可基于扩展 `ImpactDualGantt` 或新 `ImpactTripleGantt`）；顶部统一指标条（makespan、延期相关、受影响工序数等，字段以现有 impact_summary 为准）。  
4. 导出：JSON（完整 impact + 元数据）；PDF（摘要指标 + 说明；甘特可用简化示意或关键表，不要求像素级打印）。  
5. 从事件完成 / 扰动跑完提供「打开对比页」入口。

---

## 4. 架构

```text
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ APS Package │────►│ package→execution    │────►│ production_execution│
│ 送入仿真     │     │ bridge API           │     │ + Dashboard 播放     │
└─────────────┘     └──────────────────────┘     └──────────┬──────────┘
┌─────────────┐                                              │
│ 看板选计划   │──────────────────────────────────────────────┘
└─────────────┘
                              ┌──────────────────────┐
                              │ metaforge.scenario   │
                              │ CRUD + run runner    │
                              └──────────┬───────────┘
                                         │ steps
                                         ▼
                              ┌──────────────────────┐
                              │ event_reschedule     │
                              │ R0/R1/R2 + impact    │
                              └──────────┬───────────┘
                                         ▼
                              ┌──────────────────────┐
                              │ CompareView + Export │
                              └──────────────────────┘
```

**原则：** LLM 不参与甘特计算；扰动与重排确定性在 Service/Tool。

---

## 5. API 草案（实现可微调路径名，语义锁定）

| 方法 | 路径 | 阶段 | 说明 |
|------|------|------|------|
| POST | `/api/execution/start_from_package` | P0 | body: `run_id` 或 `package` + 可选 `plan_id` / `persist_plan` / `sim_speed` |
| GET/POST | `/api/scenarios` | P1 | 列表 / 创建 |
| GET/PUT/DELETE | `/api/scenarios/{id}` | P1 | 读写删 |
| POST | `/api/scenarios/{id}/run` | P1 | 执行剧本，返回 `{ timeline, impact, status }` |
| GET | `/api/compare/latest`（可选） | P2 | 最近 impact 快照；或纯前端带 state |

现有保留：`/api/execution/*`、`/api/events/*`。

---

## 6. 前端文件级计划（示意）

```text
frontend/src/components/planning/PackageResultPanel.vue  # P0 按钮
frontend/src/views/DashboardView.vue                     # P0 自动 start；P1 ScenarioPanel
frontend/src/components/ScenarioPanel.vue                # P1
frontend/src/views/CompareView.vue                       # P2
frontend/src/components/ImpactTripleGantt.vue            # P2（或扩展 Dual）
frontend/src/router/...                                  # P2 路由
src/metaforge/scenario/                                  # P1 模型+store+runner
src/metaforge/services/package_to_execution.py           # P0 桥接
tests/...                                                # 各阶段测试
```

---

## 7. 错误处理

| 情况 | 行为 |
|------|------|
| 无 recommended / 无 gantt | 400，提示先完成排产 |
| plan 缺失且 `persist_plan` 未开 | 400 |
| 执行中再次 start | 要求确认覆盖或先 reset |
| 剧本步骤失败 | 中止后续；timeline 记录错误 |
| 剧本 JSON 非法 | 拒绝保存/运行 |
| 对比页无数据 | 空态引导 |
| PDF 失败 | 仍提供 JSON |

---

## 8. 测试要求

**P0**

1. start_from_package：有推荐 → execution.baseline_gantt 非空  
2. 无推荐 → 4xx  
3. 已有 plan_id 路径与 persist 路径至少一个覆盖  

**P1**

4. Scenario CRUD roundtrip  
5. 预设 run 至少成功一步并产生 timeline  
6. 中途失败不再执行后续步  

**P2**

7. Compare 绑定 R0/R1/R2 甘特键存在  
8. 导出 JSON 含 scenarios/metrics 关键字段  

**回归：** `tests/test_production_execution.py`、events 相关、`planning_collab`/`strategy` 冒烟仍绿。

---

## 9. 验收标准

1. APS 可将当前 Package 推荐计划送入看板仿真并播放。  
2. 看板仍可从计划库启动执行。  
3. 用户可编辑/保存/加载扰动 JSON 剧本并一键运行，看到时间线。  
4. 存在独立对比页，R0/R1/R2 三甘特并排 + 指标条。  
5. 支持导出 JSON；PDF 至少含文字摘要指标。  
6. 不引入第二套仿真内核；重排仍走现有 events 服务。  

---

## 10. 明确不做 / Backlog

| 项 | 归属 |
|----|------|
| 后台定时自动跑剧本 | 后续 |
| 像素级 PDF 甘特打印 | 后续 |
| events Agent 同构迁移 | S2 backlog |
| 数字孪生三维强化 | 另项 |

---

## 11. 规格自检

| 项 | 结果 |
|----|------|
| 占位符 | 无；API 路径名允许实现微调但语义已锁 |
| 一致性 | 与决策表、薄适配架构、分期一致 |
| 范围 | 单规格可覆盖；实现计划应按 P0/P1/P2 分任务块 |
| 模糊性 | 双入口、剧本可配置、三甘特+导出已写明 |

---

## 12. 参考

- `src/metaforge/services/production_execution.py`  
- `src/metaforge/services/event_reschedule.py`  
- `frontend/src/components/MesReschedulePanel.vue` / `ImpactDualGantt.vue`  
- S3：`docs/superpowers/specs/2026-08-03-planning-frontend-modes-design.md`  
- README 路线图 S4  
