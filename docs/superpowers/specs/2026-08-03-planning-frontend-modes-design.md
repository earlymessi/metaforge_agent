# S3 前端三模式 + Package 结果页 设计规格

> 状态：已批准（头脑风暴 2026-08-03）  
> 前置：S1 参数化策略 ✅、S2 Planning Collab ✅  
> 实现计划：待 `writing-plans` 产出

---

## 1. 背景与目标

S1/S2 已打通「策略生成 → Collab 分析 → HITL → Package」。APS 右侧仍是轻量协同排产面板 + 旧 NL/权重区，缺少产品化的 **Mode A/B/C** 与完整结果展示。

**本轮目标：** 在现有 `APSView` 内，用 Tab 工作台替换旧排产策略入口，支持三种策略配置方式，并展示可读的 Production Plan Package 结果。

**本轮不目标：** 新路由页、甘特预览、collab/strategy trace 卡片、删 Solver/Collab 内核、五 Agent 同构迁移、LangGraph/MCP。

---

## 2. 已确认决策

| 决策项 | 结论 |
|--------|------|
| 落点 | 仅增强 `APSView`（不新建独立路由） |
| 布局 | Tab 切换 Mode A/B/C；配置 → HITL → 结果纵向堆叠 |
| Mode A | Preset 模板一键跑；默认 `skip_strategy_hitl=true`（可选手动开确认） |
| Mode B | 权重 + critical_orders + **catalog 全量**硬/软约束可视化编辑；默认需 HITL |
| Mode C | 现有 NL → `/api/planning/collab/run` + 三分析摘要 + HITL |
| 结果页 | KPI、硬约束违反、推荐理由、候选对比、`simulated_fields` |
| 结果页不做 | 甘特预览、trace 阶段卡片 |
| 旧面板 | **隐藏/移除** NL 排程与权重面板，全部收进三模式 |
| 后端 | 优先复用现有 API；必要时为 Mode A 增加可选 `preset_id` 小补丁 |

---

## 3. 三模式定义

### 3.1 Mode A · 模板（Quick Template）

- 加载 `GET /api/planning/strategy/presets`
- 用户选择一个 preset → 构造/加载对应 `SchedulingStrategy`
- 调用 `POST /api/planning/run`（jobs/machines 来自现有 `buildPlanningJobs/Machines`）
- 默认跳过策略 HITL；提供「运行前需确认」开关

### 3.2 Mode B · 参数（Parameter）

- 编辑：
  - `objectives` 权重（与现有多目标语义一致）
  - `critical_orders`（从当前 jobs 多选）
  - `hard_constraints` / `soft_constraints`：按 `GET /api/planning/constraints/catalog` 全量类型增删改
- 约束表单：hard/soft 分组折叠；未知类型禁止提交
- 流程：`POST /api/planning/strategy/validate` → 通过后 `POST /api/planning/run`（默认 `skip_strategy_hitl=false`）
- 支持将当前草稿展示为可编辑 Strategy JSON（与 S1 预览兼容）

### 3.3 Mode C · AI 策略（AI Strategy）

- 自然语言目标输入
- `POST /api/planning/collab/run`（`skip_strategy_hitl=false` 默认）
- 展示 order / constraint / resource 三分析摘要（现有折叠区能力迁入）
- HITL：`/api/planning/runs/{id}/strategy/approve|reject|edit_and_approve`

### 3.4 共用结果区

从 run / collab 响应的 `package` + `evaluation` 提取并展示：

- `recommended_schedule_id`
- KPI / metrics（来自推荐候选或 evaluation 摘要）
- `hard_violations`
- `recommendation_reason`
- 候选列表对比（schedule_id、solver、关键指标）
- `strategy.provenance.simulated_fields`

无推荐时明确显示「无合法推荐」及违规摘要。

---

## 4. 架构与组件

```text
APSView（左侧工单/资源不变）
  └── PlanningWorkbench
        ├── Mode tabs: A | B | C
        ├── ModeTemplatePanel
        ├── ModeParameterPanel
        │     └── ConstraintEditor
        ├── ModeAiPanel
        ├── StrategyHitlBar
        └── PackageResultPanel
```

| 组件 | 职责 | 非职责 |
|------|------|--------|
| `PlanningWorkbench` | Tab、共享 run 状态、调度 HITL/结果 | 求解算法 |
| `ModeTemplatePanel` | Preset 选择与一键运行 | 约束全量表单 |
| `ModeParameterPanel` | 参数化策略编辑 | Collab 编排 |
| `ConstraintEditor` | catalog 驱动的约束 CRUD UI | Guardrails 服务端逻辑 |
| `ModeAiPanel` | NL + 三分析展示 + collab 入口 | Preset 选择 |
| `StrategyHitlBar` | 批准/拒绝/编辑后批准 | 改 Package 评价规则 |
| `PackageResultPanel` | Package 只读展示 | 甘特渲染 |

建议目录（实现时可微调，保持单一职责）：

```text
frontend/src/components/planning/
  PlanningWorkbench.vue
  ModeTemplatePanel.vue
  ModeParameterPanel.vue
  ModeAiPanel.vue
  ConstraintEditor.vue
  StrategyHitlBar.vue
  PackageResultPanel.vue
```

`APSView.vue`：挂载 Workbench；删除/隐藏旧 `scheduleMessage`、权重面板及相关运行按钮。

---

## 5. 数据流

```text
共用输入: jobs = buildPlanningJobs(), machines = buildPlanningMachines()

Mode A:
  presets → strategy(from preset) → POST /api/planning/run
           → PackageResultPanel

Mode B:
  local Strategy draft → POST /api/planning/strategy/validate
                      → (ok) POST /api/planning/run [HITL 可选]
                      → PackageResultPanel

Mode C:
  user_goal → POST /api/planning/collab/run
           → WAITING_APPROVAL → HITL endpoints
           → COMPLETED PackageResultPanel
```

**Mode A preset 落地方式（二选一，实现计划锁定其一）：**

1. **优选：** `POST /api/planning/run` 增加可选 `preset_id`，服务端 `strategy_from_preset` 后走 pipeline  
2. **备选：** 前端根据 presets 响应拼出 strategy 对象，经 validate 后 run（若现有 run 已支持传入 strategy；否则仍用 generate 规则路径）

以「少改后端、行为正确」为准；实现阶段先查 `run_planning` 是否接受已有 strategy，再定。

---

## 6. HITL 与 Flag

| 模式 | 默认 `skip_strategy_hitl` | 说明 |
|------|--------------------------|------|
| A | `true` | 可 UI 开关改为 `false` |
| B | `false` | validate 失败不得进入求解 |
| C | `false` | 与 S2 现状一致 |

- `PLANNING_STRATEGY_V1=0`：Mode A/B 禁用并提示  
- `PLANNING_COLLAB_V1=0`：Mode C 禁用并提示（A/B 仍可用）

---

## 7. 错误处理

| 情况 | 行为 |
|------|------|
| 非 custom / 无工单 | 禁用运行，提示配置工单 |
| Mode B validate 失败 | 展示 errors，停留编辑态 |
| run / collab FAILED | 展示 error/warnings，保留配置 |
| Collab LLM 摘要失败 | 跳过摘要，流程继续（S2 行为） |
| 无 recommended | 结果区明确「无合法推荐」+ 违规列表 |

---

## 8. 测试要求

1. Tab 切换：三模式面板互斥渲染  
2. Mode A：mock presets → run → Package 关键字段存在  
3. Mode B：非法约束类型无法提交；合法草稿 validate ok  
4. Mode C：collab → WAITING_APPROVAL → approve（可 mock API）  
5. 旧 NL/权重面板 DOM 不再出现（或 `v-if` 永久关闭）  
6. 回归：`pytest tests/planning_collab/ tests/strategy/ -q` 全绿  
7. `npm run build` 通过  

---

## 9. 验收标准

1. APS 右侧仅见 Mode A/B/C 工作台，无旧 NL/权重主入口。  
2. 三模式均可在 custom 工单下产出 Package（或明确无推荐）。  
3. Mode B 可编辑 catalog 中全部硬/软约束类型。  
4. 结果区含：推荐 ID、违规、理由、候选对比、模拟字段。  
5. Mode A 默认可一键完成；B/C 默认走 HITL（A 可选手动开）。  
6. 不引入新路由、不画甘特预览、不展示 trace 卡片。  

---

## 10. 明确不做 / Backlog

| 项 | 归属 |
|----|------|
| 甘特预览 recommended | S3.1 或 S4 |
| collab_trace / strategy_trace 卡片 | 后续 |
| 独立策略工作台路由 | 可选后续 |
| 删除 `SchedulingAgentRunner` 文件 | 独立清理 PR |
| events 等五 Agent 同构迁移 | S2 backlog |
| S4 仿真对接 | 下一主线阶段 |

---

## 11. 规格自检

| 项 | 结果 |
|----|------|
| 占位符 | 无 TODO 实现洞；Mode A preset 接入留「二选一」由实现计划锁定 |
| 一致性 | 与已确认决策、S1/S2 API 复用一致 |
| 范围 | 单规格可覆盖一个实现计划（前端为主 + 可选小 API） |
| 模糊性 | HITL 默认、结果字段、旧面板处理已写明 |

---

## 12. 参考

- S1 规格：`docs/superpowers/specs/2026-08-03-parameterized-scheduling-strategy-design.md` §14/§16  
- S2 规格：`docs/superpowers/specs/2026-08-03-planning-collab-multiagent-design.md`  
- 现状 UI：`frontend/src/views/APSView.vue`  
- API：`/api/planning/*`、`/api/planning/collab/*`  
