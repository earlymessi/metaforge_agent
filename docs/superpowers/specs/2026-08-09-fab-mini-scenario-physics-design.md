# 半导体 Mini-Fab 三工区物理场景复原（建模前置规格）

> 日期：2026-08-09  
> 状态：**待用户审查**（本文件只复原物理与约束语义，不实现求解器/工作台）  
> 目的：为后续「场景导入 → 参数化策略 → 评价/调度 → NL→AI 策略」提供**可答辩的真实工艺依据**  
> 非目标：整厂 FAB、AMHS 全物流、cluster 腔内毫秒级调度、真实 MES/IoT

---

## 0. 总原则

1. **物理先于算法**：每个硬约束必须能回答「哪道工序、什么失效模式、为何不能松」。  
2. **Mini-Fab 而非整厂**：规模可控；约束语义对齐文献与产线共识，不宣称 12 寸量产厂等价。  
3. **三类约束互不混淆**：扩散批处理 ≠ 光刻粘机 ≠ 刻蚀时间窗（根因不同）。  
4. **建模分层**：数据层（路由/机台/族）→ 策略层（硬/软约束字段）→ 求解/评价 →（可选）工作台场景包 / NL 解析。  
5. **明确不建模清单**写进每个场景，避免 AI「幻觉出」未声明约束。

### 0.1 Mini-Fab 工艺环（共用骨架）

对齐光刻 dedication 文献常用的简化环（Choi mini-fab 一类）：

```text
Lot 多层循环（重入）：
  … → [扩散/炉管 Diffusion] → [光刻 Photo] → [刻蚀 Etch] → [清洗 Clean] → …
每完成一层电路图案相关步骤后可能再次进入光刻（L ≥ 2）。
```

| 工区 | 本规格主角约束 | 在环中的角色 |
|------|----------------|--------------|
| 扩散 / 炉管 | 不兼容族 + 同步批处理 | 高温掺杂/氧化，长加工、批处理机 |
| 光刻 | Dedication（粘机）+ 重入 | 曝光对准，常为瓶颈 |
| 刻蚀 | Timelink / 驻留上界（跨步时间窗） | 图形转移；与上下游存在时效 |

运输、自动天车、库存架容量：**一期不建模**（假设 lot 在工区缓冲可用）。

---

## 1. 场景 Α — 扩散 / 炉管区：不兼容作业族 + 同步批处理

### 1.1 物理场景（复原）

| 项 | 内容 |
|----|------|
| **产线位置** | 前端 FAB **扩散 / 氧化炉管区**（Diffusion / Oxidation Furnace） |
| **加工对象** | Lot（常见 25 片晶圆为一物流与加工单元；模型可用 lot = job） |
| **设备形态** | **并行批处理机（p-batch）**：一台炉可同时加工多个 lot，但一次点火形成一批 |
| **工艺目的** | 高温下引入掺杂剂或生长氧化层，改变电学/表面特性 |
| **典型时长** | 文献常述单批恒温过程可达数小时量级（如 10–12h 量级叙述）；模型用参数 `batch_process_time`，不写死 |

### 1.2 为何产生硬约束（失效模式）

| 约束 | 物理/化学原因 | 违反后果 |
|------|----------------|----------|
| **同批必须同 recipe / 同族（incompatible families）** | 不同配方对应不同掺杂剂与热曲线；混炉导致交叉污染、热预算错误 | 批次报废 / 电性失效 |
| **批内 lot 同步开始与结束** | 炉内热场需稳定；中途加抽破坏均匀性，有过烧/掺杂不均风险 | 良率损失、设备异常 |
| **一批容量上限** | 炉管物理装载上限 | 不可行装载 |
| **（可选连带）有限等待进炉** | 前道清洗后表面状态有时效，超时氧化/污染 | 返工或报废（可与场景 C 联动） |

### 1.3 文献锚点（答辩用，优先 2022–2025）

- Wu et al., **EJOR 2022**：扩散炉作业调度（产线实现对照）[10.1016/j.ejor.2021.09.044](https://doi.org/10.1016/j.ejor.2021.09.044)  
- Yang et al., **EJOR 2022**：不兼容族 + 非等同尺寸并行批 / MILP·CG·B&P [10.1016/j.ejor.2022.03.027](https://doi.org/10.1016/j.ejor.2022.03.027)  
- 扩散区 p-batch、recipe 族、同步起止、CP vs MIP：[arXiv:2410.11981](https://arxiv.org/abs/2410.11981)（2024）  
- **复现边界**：本仓库复现的是 **约束语义 Mini-Fab**，不是 EJOR 真厂实例或精确求解器

### 1.4 一期建模范围

**要建模**

- 机台类型：`batch_furnace`，属性 `max_batch_size`  
- Job/Lot 属性：`family_id` / `recipe_id`（同族可批）  
- 硬规则：同一 batch 内 `family_id` 全相同；`|batch| ≤ max_batch_size`；batch 内开工时刻相同、加工时长取族加工时间  
- 评价：混族同批、超容量、批内不同步 → **hard illegal**

**明确不建模（一期）**

- 炉管管内片级温度场 CFD  
- 多腔 cluster 内机械手毫秒调度  
- 真实气体/化学品配方库  
- 与整厂 WIP 鼓点联立优化  

### 1.5 场景包参数（供日后「场景导入」）

```yaml
scenario_id: fab_diffusion_batch_v1
area: diffusion_furnace
physics_refs:
  - "incompatible job families / p-batch (diffusion)"
entities:
  machines:
    - { id: F1, type: batch_furnace, max_batch_size: 4 }
  families:
    - { id: ox_a, process_time: 8.0 }
    - { id: ox_b, process_time: 10.0 }
  lots:
    - { id: L1, family_id: ox_a, release: 0 }
    - { id: L2, family_id: ox_a, release: 0.5 }
    - { id: L3, family_id: ox_b, release: 0 }
constraints_hard:
  - type: batch_same_family
  - type: batch_capacity
  - type: batch_synchronized
objectives_default:
  - minimize_flow_time
  - maximize_batch_fill_ratio   # 可作为软目标
```

### 1.6 与策略工作台 / NL 的映射（仅定义，未实现）

| 自然语言意图（例） | 应解析出的策略字段 |
|--------------------|-------------------|
| 「同配方才能进同一炉」 | hard: `batch_same_family` |
| 「炉最多装 4 批」 | hard: `batch_capacity` + params.max_batch_size |
| 「尽量满炉再开」 | soft: 满批偏好 / 惩罚不满批 |

---

## 2. 场景 Β — 光刻区：Dedication（粘机）+ 重入

### 2.1 物理场景（复原）

| 项 | 内容 |
|----|------|
| **产线位置** | 前端 **光刻（Photolithography）**，Stepper/Scanner |
| **为何重入** | 芯片由多层电路构成；每层需再次曝光；lot 多次回到光刻区 |
| **设备特点** | 资本密集、常为瓶颈；同型号机台仍有个体差异 |

### 2.2 为何产生硬约束（失效模式）

| 约束 | 物理原因 | 违反后果 |
|------|----------|----------|
| **Dedication（关键层粘同一光刻机）** | 设备 **natural bias（固有偏差）**；不同机台对准/光罩姿态微小差异导致层间 **overlay** 不准 | 良率下降、先进制程不可接受 |
| **首层选机影响未来负载** | 一旦首层绑定机台 A，后续 re-entrant 层只能等 A | 局部空闲却不能跨机 → 产能损失（调度挑战，非可取消约束） |

**注意**：这与「为赶时间窗而工具专用」不同——根因是 **对准/良率**，不是时效。

### 2.3 文献锚点（优先 2022–2025）

- Deenen et al., **IEEE TSM 2023**：真厂光刻区 CP vs MIP（reticle/pod 双辅助资源）[10.1109/TSM.2023.3304517](https://doi.org/10.1109/TSM.2023.3304517) — **边界参照**（一期不建模 reticle）  
- WSC 2023：光刻 RL 选规则 vs 单规则/混合规则集（对照实验范式）  
- 物理根因（dedication ← natural bias / overlay）：沿用经典表述；Mini-Fab 重入环对齐 Choi 一类简化  
- **复现边界**：复现 **重入 + 粘机硬约束 + 规则/元启发式对照**；不复刻 TSM 公开真厂 10 实例与 CP 模型

### 2.4 一期建模范围

**要建模**

- 工序标记：`process_area: photo`，`layer_index`，`is_dedication_mark`（首层光刻）  
- 决策：首层光刻选定 `dedicated_machine_id`  
- 硬规则：同一 lot 后续 photo 工序必须 `machine_id == dedicated_machine_id`（或同 dedication 组，一期取单机）  
- 软目标（可选）：dedication load 均衡，减少粘机堆积  

**明确不建模（一期）**

- Overlay 计量数值仿真、套刻误差概率模型  
- Reticle（光罩）库存与换罩矩阵的完整工业库（可二期：序列相关 setup）  
- 光刻胶涂覆/显影整条 track 的片级调度  

### 2.5 场景包参数（草案）

```yaml
scenario_id: fab_photo_dedication_v1
area: photolithography
physics_refs:
  - "natural bias → overlay → machine dedication"
entities:
  machines:
    - { id: P1, type: stepper }
    - { id: P2, type: stepper }
  lots:
    - { id: L1, layers: 3, ops: [photo_L1, etch, clean, diff, photo_L2, ...] }
constraints_hard:
  - type: photo_machine_dedication
    params: { mark_step: photo_L1, sticky_steps: [photo_L*] }
objectives_default:
  - minimize_total_flow_time
  - balance_dedication_load   # soft
```

### 2.6 NL 映射（例）

| 自然语言 | 策略字段 |
|----------|----------|
| 「同一 lot 各层光刻必须同一台曝光机」 | hard: `photo_machine_dedication` |
| 「首层选机要考虑以后回流水」 | soft: `balance_dedication_load` |

---

## 3. 场景 C — 刻蚀 / 湿清相关：Timelink（跨步最大等待）

### 3.1 物理场景（复原）

刻蚀相关约束在文献中有两条粒度，**一期只取 FAB 工区级 Timelink**，不取 AWS 站内机械手。

| 粒度 | 内容 | 一期 |
|------|------|------|
| **A. 工区 Timelink** | 刻蚀或湿法清洗结束后，必须在时限 Q 内进入下一关键步（如进炉/下道），否则表面氧化/污染 | **做** |
| **B. AWS 站内** | 化学槽 Zero-Wait、水槽缓冲、机器人搬运互斥 | **不做**（另立规格） |

| 项 | 内容 |
|----|------|
| **产线位置** | 湿法清洗 / 湿刻 与下游（常耦合炉管）之间的 **time-link 区域**；干刻后同样可存在驻留/时效约束 |
| **工艺目的** | 去除薄膜/图形转移；清洗后表面活泼 |

### 3.2 为何产生硬约束（失效模式）

| 约束 | 物理原因 | 违反后果 |
|------|----------|----------|
| **Timelink：`start(next) − end(prev) ≤ Q`** | 防止清洗/刻蚀后不必要的等待导致氧化或污染 | 返工、良率损失、报废（文献明确 yield/scrap） |
| **（站内）化学槽不可久泡** | 过刻 | 一期不建模 |

**注意**：现场有时用「工具专用」减轻 timelink 排队——那是 **运营策略**，根因仍是时间窗，不要写成光刻 dedication。

### 3.3 文献锚点（优先 2022–2025）

- Flexciton–Renesas / Elaoud et al., **J. Manuf. Syst. 2022**：湿清+扩散批 + timelink，对照工厂规则派工与不确定性仿真  
- **J. Intell. Manuf. 2024**：半导体时间窗生产控制综述/方法（文献以 MIP/CP 为主；现场多为规则）  
- WSC 2021：并行批 + job timelink 多目标（同一问题族的会议版）  
- **复现边界**：复现 **simple timelink（相邻工序 max_lag）+ 可行实例 + hard_ok/违反计数**；不复刻工厂历史计划回放

### 3.4 一期建模范围

**要建模**

- 在工艺路由上标注有向边 `(op_i → op_j)` 带 `max_lag_hours: Q`  
- 硬规则：可行调度必须满足时间窗；评价器检测违反  
- 可选软：惩罚接近上界的等待（稳健性）  

**明确不建模（一期）**

- AWS 多浴槽 + 单臂/双臂机器人轨迹  
- 片级驻留 ≤15s 的设备内 JIT（集创赛/组合设备级）  
- 污染浓度随时间的连续化学动力学  

### 3.5 场景包参数（草案）

```yaml
scenario_id: fab_etch_timelink_v1
area: etch_wet_timelink
physics_refs:
  - "time-link / max lag after clean or etch before next critical step"
entities:
  lots:
    - id: L1
      ops:
        - { id: wet_clean, area: wet }
        - { id: diffusion, area: diffusion, after: wet_clean }
timelinks_hard:
  - { from_op: wet_clean, to_op: diffusion, max_lag_hours: 1.5 }
objectives_default:
  - minimize_timelink_violation   # 硬约束下应为 0
  - minimize_flow_time
```

### 3.6 NL 映射（例）

| 自然语言 | 策略字段 |
|----------|----------|
| 「清洗后 1.5 小时内必须进扩散炉」 | hard: `max_lag_between_ops` + Q=1.5 |
| 「宁可等炉空出来也别让清洗完的 lot 超时」 | 求解偏好 / 派工优先级（软） |

---

## 4. 三场景对照（防止混用）

| | 扩散批处理 | 光刻 Dedication | 刻蚀 Timelink |
|--|------------|-----------------|---------------|
| **根因** | 化学污染 + 热场同步 | 设备固有偏差 → overlay | 表面时效 → 氧化/污染 |
| **数学形态** | 同族批 + 容量 + 同步区间 | 决策变量粘连机台 | 相邻工序最大时间滞后 |
| **典型目标** | 流动时间、满批率 | 流动时间、粘机负载均衡 | 零违反、流动时间 |
| **一期机型** | `batch_furnace` | `stepper` | 普通机 + 路由边约束 |
| **AI 解析风险** | 勿与「换型」混淆 | 勿与「资格机台」仅偏好混淆 | 勿与光刻粘机混淆 |

---

## 5. 通往工作台与 AI 的路径（本规格之后）

### 5.1 工作台入口（已确认命名）

不新增独立导航页。在智能排程（APS）数据源区，与现有两项并列增加第三项：

```text
[ 算例库 ]  [ 自定义/数据库 ]  [ FAB场景 ]
```

| 项 | 约定 |
|----|------|
| **按钮文案** | **FAB 场景**（已确认） |
| **语义** | 导入 Mini-Fab **场景包**（工单/机台/默认硬约束），仍走现有策略工作台与求解/评价 |
| **非语义** | 不是 MES「执行仿真 / 预约事件」；避免用「FAB 仿真」以免混淆 |
| **选中后** | 场景包下拉（扩散批处理 / 光刻粘机 / 刻蚀时间窗）→ 载入 → 智能策略 / 参数化开跑 |

### 5.2 实现顺序

```text
① 本文件：物理复原 + 参数字典 + 不建模边界  ← 当前
② 场景包 Schema（JSON/YAML）+ 校验器
③ 策略 Catalog 增补硬约束类型 + Evaluator 判定
④ APS 第三数据源「FAB 场景」：载入实体与约束默认值
⑤ NL → Strategy：仅映射已登记约束类型（禁止发明物理）
⑥（可选）派工规则 / 小规模精确解实验
```

**AI 赋能前提（验收门槛）**

- 每个 NL 抽出的约束必须能追溯到上表某一 `type`  
- 无法映射则 **澄清提问**，不得静默生成未登记硬约束  
- 场景包带 `physics_refs` 与 `out_of_scope`，导入后 UI 可见

---

## 6. 决策收口（贴合场景优先）

用户原则：**尽量最贴合场景；做不到的地方必须明示，不得假装已建模。**

| # | 决策 | 收口 |
|---|------|------|
| 入口 | APS 第三数据源文案 | **FAB 场景**（已确认） |
| 1 | 场景包覆盖 | **三场景规格与场景包骨架都做**；求解算法可按 Dedication → Timelink → Batch 递进加深，但导入与评价语义三区齐备 |
| 2 | 刻蚀一期 | **硬约束以 Timelink（max lag）为主角**；AWS/机械手排队不进一期（见 §7：非「偷减物理」，而是刻蚀良率根因不在机器人） |
| 3 | Lot 抽象 | **lot ≈ 现有 `job` + 扩展字段**（`family_id` / dedication / layer）；不做片级（wafer）调度 |

---

## 7. 贴合度与「做不到」清单（答辩用）

### 7.1 能较真贴合的（一期目标 = 语义等价）

| 场景 | 贴合点 | 验收标准 |
|------|--------|----------|
| 扩散 | 同族才可同炉、容量、批内同步起止 | 违反 → evaluator **hard illegal**；合法解可解释「为何这几 lot 同批」 |
| 光刻 | 首层选机后后续 photo 层必须同机（dedication） | 跨机排程 → hard illegal；甘特上同 lot 光刻工序机台一致 |
| 刻蚀/清洗链路 | 指定工序对之间 `end(from)→start(to) ≤ Q` | 超时 → hard illegal（或显式「违反计数」若策略声明为软，默认硬） |
| 重入环 | lot 多层再次进入光刻 | 路由含 `layer_index` + 多道 photo op，非单次访问 |

### 7.2 只能近似、必须说清的

| 真实世界 | 我们怎么做 | 为何只能近似 |
|----------|------------|--------------|
| 炉管热预算 / 污染机理 | 用 `family_id` 离散等价「不可混」 | 无 CFD、无真实 recipe 库；贴合的是**调度语义**，不是物理仿真 |
| Overlay / natural bias 数值 | 用 dedication 硬约束代替 | 不仿真套刻误差 nm；贴合的是**因 bias 而产生的机台粘连决策** |
| 表面氧化/污染随时间连续变差 | 用单阈值 `max_lag` 阶跃约束 | 无连续退化函数；工业调度文献亦常如此离散化 |
| Lot = 25 片物流单元 | `job` 一条 + 可选 `lot_size` 字段 | 片级并行、片内缺陷不建模 |
| 批处理「满炉率」 | 软目标 / 惩罚，非热场优化 | 满炉是经济与产能偏好，不是扩散物理硬定律 |
| 现有 GA/TS 内核 | 一期以 **evaluator + 可行修复/预处理** 为主，不保证立刻有工业级批处理最优解 | 内核面向经典 JSSP/FJSP；真·批处理最优需专用算法（二期） |

### 7.3 明确做不到 / 一期不做（禁止对外宣称）

| 不做项 | 原因 |
|--------|------|
| 整厂 FAB、AMHS 天车/OHT 拥堵 | 规模与物流另一问题域 |
| AWS / 湿法机械手腔级毫秒调度 | 与 Timelink 根因正交；工程量另开课题 |
| Overlay 计量、良率概率模型 | 无量测闭环；超出排产骨架 |
| 光罩 reticle 全库 + 换罩矩阵工业完整版 | 可二期做序列相关 setup，一期不装 |
| Track（涂胶显影）片级、cluster 多腔机械手 | 设备内部控制层 |
| 与真实 MES/IoT 时钟、WIP 鼓点联立 | 本仓库 APS 场景包是离线/半离线问题实例 |
| 「FAB 场景」按钮 = MES 执行仿真 | 仅导入场景包；仿真看板是另一条链路 |

### 7.4 诚实结论（一句话）

**贴合的是「约束为何存在 + 调度上必须遵守的形态」；不贴合「设备物理场 / 片级 / 整厂物流」。**  
面试与文档对外口径统一用这句话。

**与近年顶刊的复现关系**：场景包 `paper_alignment.reproduce_level = semantic_mini_fab` ——  
可复现论文中的 **问题族与评价指标写法**；不可复现 **专有真厂数据、CP/MIP 工业求解栈、reticle/AMHS**。

**隔离与场景包契约（已另文）**：`2026-08-09-fab-scenario-isolation-design.md`  
（FAB 约束不进通用 `HARD_CONSTRAINT_TYPES`；`domain=fab` 才接线；实现计划见 `plans/2026-08-09-fab-scenario-isolation.md`。）
