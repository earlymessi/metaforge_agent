# Events Collab 同构迁移 设计规格

> 状态：已批准（头脑风暴 2026-08-03）  
> 前置：S1–S4 ✅；本轮为五领域同构迁移 backlog 第 1 项（events）  
> 方案：**A — 薄 Bridge + 固定编排**  
> 实现计划：待 `writing-plans` 产出  

---

## 1. 背景与目标

S2 已将 scheduling 主路径替换为 `SchedulingCollabBridge` → `planning_collab`。events 仍由 `EventsAgentRunner`（`BaseAgent` + 规则/LLM plan + Tool 链）承担助手与 `/api/agents/events/run` 入口。

看板与 S4 剧本已直连 `/api/events/*` → `event_reschedule`，**不依赖** EventsAgentRunner。

**本轮目标：** 将 events 的 Agent 入口同构为「薄 Bridge + 固定阶段编排 + events_trace」，替换完成后删除旧 Runner 主路径。

**本轮不做：** Agent Harness 平台、A2A、kitting 及后续领域、新事件类型、改 R0/R1/R2 算法内核。

---

## 2. 已确认决策

| 决策项 | 结论 |
|--------|------|
| 交付节奏 | 本轮只做 **events**；其余领域仍 backlog |
| 架构 | **A：薄 Bridge + 固定编排**（不硬套三角色 Supervisor） |
| 看板 REST | `/api/events/*` **不变** |
| 确定性内核 | 继续 `events.*` / `delivery.*` Tools → `event_reschedule` |
| 旧路径 | 验收后 **删除** `EventsAgentRunner` 主路径（禁止永久双跑） |
| Flag | 可选 `EVENTS_COLLAB_V1` 默认 `1`；验收后可删 Flag 与回退 |

---

## 3. 运行时结构

```text
Orchestrator / POST /api/agents/events/run
        │
        ▼
EventsCollabBridge  (agent_id=events)
        │
        ▼
events_collab.run(message, context, params)
        │
        ├─ 固定阶段（见 §4）
        │
        └─ AgentResponse 兼容字段
             + events_trace
             + artifacts（impact_report 等）
             + 现有 _maybe_sync_events_agent_response 写回 MES
```

模块建议：

```text
src/metaforge/events_collab/
  __init__.py
  pipeline.py      # run() 固定编排
  trace.py         # build_events_trace
src/metaforge/agents/events_collab_bridge.py
```

也可放在 `planning_collab` 旁平行包名 `events_collab`，**不要**塞进 planning_collab 命名空间。

---

## 4. 固定阶段（从现 Runner 规则链收敛）

顺序与现网 `EventsAgentRunner` 规则行为对齐：

1. `execution.get_state`（optional）  
2. 若消息命中「支持哪些事件」类目录问询 → `events.list_event_types` → **结束**  
3. 若存在插单 intake pending → `events.merge_insert_job` → `events.check_insert_job`  
   - `need_input` → 返回 `status=need_input` + pending_action（写 Memory working），**不继续 reschedule**  
4. 否则（可 `skip_parse`）：`events.parse_event`  
5. `events.check_insert_job`  
6. `events.reschedule`（附着 `event_envelope`）  
7. `delivery.compare_commitment`（optional）  
8. `delivery.explain_impact`  

**原则：** LLM 不参与甘特计算；不在本轮恢复依赖 GLM 动态 plan 作为主路径（与 scheduling 替换后「规则/编排为主」一致）。若需保留 LLM plan 作增强，须 Flag 且不得阻塞规则链；**默认关闭或移出主路径**，实现计划锁定其一（推荐：主路径纯固定编排）。

---

## 5. 入口改造

| 入口 | 改造 |
|------|------|
| `POST /api/agents/events/run` | 使用 Bridge / `events_collab.run` |
| Orchestrator `get_agent("events")` | 注册 Bridge |
| `registry_meta` | endpoint 可不变；实现指向 collab |
| Flag=`EVENTS_COLLAB_V1=0` | （可选）回退旧 Runner，仅迁移窗口 |

成功响应须仍能触发现有 `_maybe_sync_events_agent_response`（`agent_id=events`、`impact_report` / results 等约定保持）。

---

## 6. `events_trace`（最小集）

建议字段（实现可微调键名，语义锁定）：

```json
{
  "stages": ["get_state", "parse", "reschedule", "explain"],
  "status": "success|need_input|failed",
  "event_type": "machine_breakdown|...",
  "tool_log": [{"tool": "...", "ok": true}],
  "warnings": []
}
```

挂在 `AgentResponse.artifacts.events_trace` 或顶层 `events_trace`（与 collab_trace 惯例对齐，实现计划二选一写死）。

---

## 7. 错误与降级

| 情况 | 行为 |
|------|------|
| parse 失败 / 无 event_type | failed + 可读 summary_zh |
| reschedule Tool 返回 error | failed；保留已有 artifacts |
| need_input | 停止后续；pending_action 与现网一致 |
| Flag=0 | 旧 Runner（若保留） |
| 看板 REST | 完全不受 Flag 影响 |

---

## 8. 删除门槛

同时满足后方可删除 `EventsAgentRunner` 主类/文件及 Flag 回退：

1. `/api/agents/events/run` 与 Orchestrator events 意图 e2e：解析→重排→impact  
2. 插单多轮 `need_input` 可用  
3. 目录问询短路径可用  
4. MES sync 仍触发  
5. 相关单测改为新路径且全绿；无生产引用旧类  

---

## 9. 测试要求

1. 编排：固定 envelope → 阶段顺序与 reschedule 调用  
2. catalog 短路径只调 list  
3. need_input 不调用 reschedule  
4. API：`events_trace` 存在且 status 正确  
5. 回归：`tests/test_events_*`、events tools、看板 events 冒烟仍绿  

---

## 10. 验收标准

1. events 意图默认走 Bridge + `events_collab`，不再依赖旧 Runner 主流程。  
2. 看板 `/api/events/*` 与 S4 剧本行为无回归。  
3. 插单补全与目录问询行为保持。  
4. 有可测的 `events_trace`。  
5. 文档更新：events 同构 ✅；backlog 余 kitting → commitment → whatif → plans。  
6. 旧 Runner 按 §8 删除或已提交删除 PR。  

---

## 11. 规格自检

| 项 | 结果 |
|----|------|
| 占位符 | 无；Flag 与 trace 挂载点由实现计划二选一写死 |
| 一致性 | 与方案 A、看板不变、删旧路径一致 |
| 范围 | 单领域单规格；Harness/五领域其余项外提 |
| 模糊性 | 阶段列表、删除门槛、入口已写明 |

---

## 12. 参考

- `src/metaforge/agents/events.py`（迁出源）  
- `src/metaforge/agents/scheduling_collab_bridge.py`（Bridge 模板）  
- `src/metaforge/planning_collab/`（同构参考，不复用包名）  
- S2：`docs/superpowers/specs/2026-08-03-planning-collab-multiagent-design.md` §10 backlog  
