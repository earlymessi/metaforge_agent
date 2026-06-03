"""各任务的 system / user 提示词（对标 LangChain PromptTemplate）。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from metaforge.agent.scheduling_agent import STRATEGY_TEMPLATES
from metaforge.orchestrator.llm.prompt_builder import build_structured_prompt, build_user_message, json_line
from metaforge.orchestrator.router import INTENT_TO_AGENT
from metaforge.scheduling.goals import goal_definitions_for_prompt
from metaforge.utils.solver_registry import get_solver_catalog

_INTENT_HINTS = {
    "schedule": "对已有机位/工单做排程计算、选求解器/策略、出甘特（不是 Mongo 里新建计划档案）",
    "reschedule": "已排计划因故障/插单/改某工单交期等动态事件要重排（如「订单106交期改为20」）",
    "kitting": "问物料够不够、能否开工、齐套检查（不是一般排程）",
    "commitment": "仅问询/评估当前计划交期能否满足、风险高低、对客户怎么说；用户未要求修改交期或重排",
    "whatif": "两种及以上策略/方案对比选优",
    "plans": "计划库增删改查、加载绑定；不涉及算甘特。完成后除删除/纯列表外应打开排程中心。",
}

_EVENT_TYPES = (
    "insert_order",
    "machine_breakdown",
    "due_date_change",
    "planned_downtime",
    "material_delay",
    "priority_change",
    "order_cancel",
    "quantity_change",
)

_AGENT_PLAN_HINTS = {
    "scheduling": (
        "仅当用户明确问「有哪些算法/求解器目录」→ scheduling.list_catalog（单步）。"
        "用户要对比遗传/禁忌/SPT 等算法、或「快速出结果」「排程」→ 必须 scheduling.parse_intent → scheduling.run，"
        "禁止用 list_catalog 或 ask_clarification 代替。"
        "目标极模糊且无算法/策略线索时 → scheduling.ask_clarification（单步）。"
        "其余排程 → scheduling.parse_intent → scheduling.run。"
        "skip_parse=true 时只保留 scheduling.run。"
        "排程并落库/保存到数据库 → 在 run 后追加 delivery.assess、data.propose_persist；"
        "有 plan_id 时可先 data.load_plan；confirm_token 时仅 data.confirm_persist。"
    ),
    "events": (
        "查能力/事件类型 → events.list_event_types（单步即可）。"
        "重排类典型链：execution.get_state(optional) → events.parse_event → events.check_insert_job "
        "→ events.reschedule → delivery.compare_commitment(optional) → delivery.explain_impact。"
        "skip_parse 或 params 已有 event_envelope 时可跳过 parse_event。"
    ),
    "kitting": "典型链：material.check_static → scheduling.run → material.predict → kitting.build_report。",
    "commitment": "典型链：scheduling.run → delivery.assess → delivery.customer_script。",
    "whatif": "使用 compare.variants，params 含 variants 数组。",
    "plans": "按意图择一 Tool：create→data.create_plan；list→data.list_plans；delete→data.delete_plan；bind/view→data.bind_plan(navigate_aps=true)；rename/duplicate/update_status 对应 data.*。删除与 list 不跳转 APS。",
}

_TOOL_HINTS = {
    "scheduling.parse_intent": "解析自然语言排程参数",
    "scheduling.run": "执行排程对比",
    "scheduling.list_catalog": "列出策略与求解器目录",
    "events.list_event_types": "列出支持的异常事件类型",
    "events.parse_event": "解析异常事件",
    "events.reschedule": "按事件重排",
    "delivery.explain_impact": "解读重排影响",
    "delivery.compare_commitment": "重排前后交期承诺对比",
    "material.check_static": "静态齐套检查",
    "material.compute_delays": "推算物料就绪延迟",
    "material.predict": "排程后物料仿真",
    "kitting.build_report": "齐套报告",
    "delivery.assess": "交期风险评估",
    "delivery.customer_script": "客户话术",
    "compare.variants": "多方案对比",
    "data.load_plan": "加载计划工单",
    "data.list_plans": "列出计划库",
    "data.create_plan": "新建计划",
    "data.delete_plan": "删除计划",
    "data.bind_plan": "绑定/加载计划",
    "data.rename_plan": "重命名计划",
    "data.duplicate_plan": "复制计划",
    "data.update_status": "更新计划状态",
    "data.propose_persist": "提议落库(HITL)",
    "data.confirm_persist": "确认落库",
}


_ROUTER_FEW_SHOTS = [
    (
        "用禁忌搜索和 SPT 对比一下排程",
        json_line(
            {
                "reasoning_steps": ["对比求解器", "非计划库", "排程计算", "选 schedule"],
                "intent": "schedule",
                "reason_zh": "对比算法排程，非计划库操作",
            }
        ),
    ),
    (
        "3号机坏了4小时，帮我重排",
        json_line(
            {
                "reasoning_steps": ["设备故障", "需重调度", "非计划库", "选 reschedule"],
                "intent": "reschedule",
                "reason_zh": "设备故障引发重排",
            }
        ),
    ),
    (
        "新建计划a",
        json_line(
            {
                "reasoning_steps": ["计划库 CRUD", "非排程", "选 plans"],
                "intent": "plans",
                "reason_zh": "新建计划档案",
            }
        ),
    ),
    (
        "检查一下齐套能否开工",
        json_line(
            {
                "reasoning_steps": ["齐套/物料检查", "非选算法排程", "选 kitting"],
                "intent": "kitting",
                "reason_zh": "齐套检查能否开工",
            }
        ),
    ),
    (
        "缺料会导致哪些工单延期",
        json_line(
            {
                "reasoning_steps": ["缺料因果", "非交期承诺话术", "选 kitting"],
                "intent": "kitting",
                "reason_zh": "分析缺料对工单延期的影响，属齐套顾问",
            }
        ),
    ),
    (
        "缺料会导致哪些工单延期？哪些工单可能延期",
        json_line(
            {
                "reasoning_steps": ["缺料/延期问询", "非排程计算", "选 kitting"],
                "intent": "kitting",
                "reason_zh": "齐套缺料导致的延期分析",
            }
        ),
    ),
    (
        "交期能不能满足客户",
        json_line(
            {
                "reasoning_steps": ["仅问询交付风险", "未改交期", "选 commitment"],
                "intent": "commitment",
                "reason_zh": "评估交付承诺，非改期重排",
            }
        ),
    ),
    (
        "哪些工单可能延期",
        json_line(
            {
                "reasoning_steps": ["延期风险问询", "非缺料因果", "选 commitment"],
                "intent": "commitment",
                "reason_zh": "基于当前排程评估哪些工单可能延期",
            }
        ),
    ),
    (
        "对比一下交付优先和吞吐优先两种策略",
        json_line(
            {
                "reasoning_steps": ["多策略方案对比", "非对比求解器名", "选 whatif"],
                "intent": "whatif",
                "reason_zh": "对比策略方案，非 schedule",
            }
        ),
    ),
    (
        "对比一下遗传算法和模拟退火",
        json_line(
            {
                "reasoning_steps": ["对比两种算法", "是排程计算", "选 schedule"],
                "intent": "schedule",
                "reason_zh": "对比求解器排程，非 whatif",
            }
        ),
    ),
    (
        "做一个生产计划并排程落库",
        json_line(
            {
                "reasoning_steps": ["排程+落库", "算甘特并写库", "选 schedule"],
                "intent": "schedule",
                "reason_zh": "排程并写入数据库，属智能排程",
            }
        ),
    ),
    (
        "订单106交期改为20",
        json_line(
            {
                "reasoning_steps": ["修改交期数值", "动态事件", "选 reschedule"],
                "intent": "reschedule",
                "reason_zh": "改交期触发重排",
            }
        ),
    ),
]


def router_system() -> str:
    intent_lines = "\n".join(
        f"- {k} → {v}：{_INTENT_HINTS.get(k, '')}" for k, v in INTENT_TO_AGENT.items()
    )
    return build_structured_prompt(
        role="你是 MES 的「意图识别 Agent」（Intent Router），负责将用户一句中文映射到唯一 intent。",
        scope="只输出 JSON；必须结合整句语义，禁止仅凭单字（「计划」「查」「排」）碰运气；不要编造未列出的 intent。",
        tool_scope=f"intent 必须且只能是下列之一：\n{intent_lines}",
        business_rules="""判别要点：
- **plans**：计划库 CRUD/加载/绑定（新建计划、删除计划、查看计划XXX），不涉及选求解器、不算甘特。
- **schedule**：对已有工单排程计算、选算法、出甘特；「对比遗传算法和模拟退火」→ schedule（对比求解器）。
- **whatif**：对比两种及以上**策略/方案**（如交付优先 vs 吞吐优先），不是对比算法名称。
- **kitting**：齐套、缺料、物料够不够、能否开工、齐套检查；**「缺料会导致哪些工单延期」** 属 kitting（物料因果），不是 commitment。
- **commitment**：只问当前排程下交期能否满足、整体交付风险、客户话术；**「哪些工单可能延期」**（无缺料/BOM）→ commitment；**没有**改交期或重排指令。
- **reschedule**：改交期、插单、故障、改优先级等动态事件并重排。
- **schedule（落库）**：排程并落库/保存到数据库 → 仍选 **schedule**（智能排程 Agent），不是 plans。""",
        output_format="""JSON 字段：
- reasoning_steps：3～5 条简短中文（先写）
- intent：上表之一
- reason_zh：一句话中文理由""",
        few_shots=_ROUTER_FEW_SHOTS,
    )


def router_user(message: str) -> str:
    return build_user_message(
        message,
        context_lines=[
            "含「查看计划XXX」且 XXX 为具体名称 → plans。",
            "模糊「生产计划」若指排产计算 → schedule。",
        ],
    )


_SCHEDULING_FEW_SHOTS = [
    (
        "交付优先，对比禁忌搜索和 SPT",
        json_line(
            {
                "reasoning_steps": ["交付导向", "需多算法对比", "选 delivery 策略"],
                "solvers": ["spt", "ts"],
                "strategy_id": "delivery",
                "schedule_goal": "weighted_tardiness_total",
                "recommend_metric": "weighted_tardiness_total",
                "is_fast_mode": False,
                "full_compare": False,
                "confidence": 0.85,
                "intent_type": "COMPARE_SOLVERS",
                "summary_zh": "交付优先，对比 SPT 与禁忌搜索",
            }
        ),
    ),
    (
        "用遗传算法快速排一下",
        json_line(
            {
                "reasoning_steps": ["用户指定 GA", "快速模式保留 GA"],
                "solvers": ["ga"],
                "strategy_id": "balanced",
                "schedule_goal": "composite",
                "is_fast_mode": True,
                "full_compare": False,
                "confidence": 0.9,
                "intent_type": "RUN_SCHEDULE",
            }
        ),
    ),
    (
        "对比一下遗传算法和模拟退火",
        json_line(
            {
                "reasoning_steps": ["对比两种元启发式", "非 whatif"],
                "solvers": ["ga", "sa"],
                "strategy_id": "balanced",
                "is_fast_mode": False,
                "full_compare": False,
                "confidence": 0.88,
                "intent_type": "COMPARE_SOLVERS",
                "summary_zh": "对比遗传算法与模拟退火",
            }
        ),
    ),
    (
        "最短时间排程",
        json_line(
            {
                "reasoning_steps": ["明确 makespan 目标", "未指定单一算法", "应全量对比"],
                "schedule_goal": "makespan",
                "strategy_id": "makespan",
                "recommend_metric": "makespan",
                "full_compare": True,
                "intent_type": "COMPARE_SOLVERS",
                "confidence": 0.9,
            }
        ),
    ),
    (
        "帮我排一下",
        json_line(
            {
                "reasoning_steps": ["目标模糊", "需澄清优先级"],
                "intent_type": "CLARIFICATION",
                "confidence": 0.45,
                "solvers": [],
                "clarification_question": "请说明更看重：①交期 ②完工时间 ③能耗 ④负载均衡；是否启用物料？",
            }
        ),
    ),
    (
        "有哪些算法",
        json_line(
            {
                "reasoning_steps": ["用户要目录", "非执行排程"],
                "intent_type": "LIST_SOLVERS",
                "confidence": 0.98,
                "solvers": [],
                "strategy_id": "balanced",
                "summary_zh": "列出可用求解器",
            }
        ),
    ),
    (
        "跑一下 ft06 算例，吞吐优先",
        json_line(
            {
                "reasoning_steps": ["标准 benchmark", "吞吐目标"],
                "intent_type": "RUN_BENCHMARK",
                "benchmark_file": "ft06.txt",
                "schedule_goal": "throughput",
                "strategy_id": "throughput",
                "solvers": ["spt", "ts"],
                "confidence": 0.92,
                "summary_zh": "ft06 算例，吞吐优先",
            }
        ),
    ),
]


def scheduling_system() -> str:
    strategies = [{"id": t["id"], "name": t["name"]} for t in STRATEGY_TEMPLATES]
    catalog = get_solver_catalog()
    solvers = [
        {"id": s["id"], "name_zh": s.get("name_zh") or s.get("name_en")}
        for s in (catalog.get("solvers") or [])[:24]
    ]
    goals = goal_definitions_for_prompt()
    return build_structured_prompt(
        role="你是 MES 车间排程专家，负责把用户中文描述转为可执行的排程参数 JSON。",
        scope=(
            "你只解析求解器、策略、业务目标与 intent_type，不执行排程、不生成甘特。"
            "计划库 CRUD 不属于本解析器。"
        ),
        tool_scope=(
            f"策略模板 strategy_id：{json.dumps(strategies, ensure_ascii=False)}\n"
            f"可用算法 solvers（id）：{json.dumps(solvers, ensure_ascii=False)}\n"
            f"业务目标 schedule_goal 目录：{json.dumps(goals, ensure_ascii=False)}"
        ),
        business_rules="""目标映射（理解语义，非死板触发词）：
- 最短完工/时间最短 → schedule_goal=makespan, strategy_id=makespan（勿误用 throughput）
- 产能/吞吐 → schedule_goal=throughput, strategy_id=throughput
- 少拖期/交期/交付 → schedule_goal=weighted_tardiness_total, strategy_id=delivery
- 省电/成本 → schedule_goal=energy_cost, strategy_id=cost
- 负载均衡 → schedule_goal=machine_busy_cv, strategy_id=balance_load

对比与 intent_type：
- 用户未指定单一算法且目标明确 → solvers=全部非 RL、full_compare=true、intent_type=COMPARE_SOLVERS；recommend_metric 与 schedule_goal 一致；勿只选 SPT
- 「对比/多算法/对比遗传算法和模拟退火」→ COMPARE_SOLVERS（不是 whatif）
- 「对比交付优先和吞吐优先两种策略」→ whatif；对比两个算法名称 → schedule
- 用户已指定单一算法 → 保留该算法，intent_type=RUN_SCHEDULE，full_compare=false

快速模式：
- 「快速」且已指定算法（如遗传算法）→ is_fast_mode=true，保留该算法
- 「快速」且未指定算法 → 2～6 个非 RL 算法（rule 优先，排除 rl）

澄清：
- 「帮我排一下」等目标模糊 → intent_type=CLARIFICATION，confidence<0.7，solvers=[]，填写 clarification_question
- 「满意度/体验最好」等无法映射到上表目标 → CLARIFICATION，confidence≤0.5，禁止默认 spt/ts

物料：「不考虑物料/忽略物料」→ enforce_material=false

目录与算例（非 RUN_SCHEDULE）：
- 「有哪些算法/求解器/支持什么算法」→ intent_type=LIST_SOLVERS，solvers=[]，confidence≥0.9
- 「策略列表/优化目标有哪些」→ intent_type=LIST_STRATEGIES，solvers=[]
- 「跑 ft06/la01 算例」「benchmark」→ intent_type=RUN_BENCHMARK，benchmark_file 如 ft06.txt""",
        output_format="""JSON 字段：
- reasoning_steps：2～4 条简短中文（先写）
- intent_type：RUN_SCHEDULE | COMPARE_SOLVERS | RUN_BENCHMARK | CLARIFICATION | LIST_SOLVERS 等
- confidence：0～1
- schedule_goal、schedule_goal_name_zh、recommend_metric
- is_fast_mode、full_compare：布尔
- solvers：字符串数组
- weights：含 makespan, weighted_tardiness_total, energy_cost, machine_busy_cv
- strategy_id、strategy_name、enforce_material
- benchmark_file：字符串或 null
- clarification_question：CLARIFICATION 时必填
- summary_zh、solver_match_notes、strategy_match_note""",
        few_shots=_SCHEDULING_FEW_SHOTS,
    )


def scheduling_user(
    message: str,
    *,
    benchmark_file: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    session_context: Optional[Dict[str, Any]] = None,
) -> str:
    ctx: List[str] = []
    if benchmark_file:
        ctx.append(f"已知算例文件：{benchmark_file}")
    if params and params.get("solvers"):
        ctx.append(f"用户已手动指定算法（可参考）：{params['solvers']}")
    if session_context:
        ctx.append(f"会话上下文（可参考）：{json.dumps(session_context, ensure_ascii=False)}")
    return build_user_message(message, context_lines=ctx)


_EVENT_FEW_SHOTS = [
    (
        "3号机坏了4小时",
        json_line(
            {
                "reasoning_steps": ["设备故障", "3号机→machine_id=2", "时长4小时"],
                "event_type": "machine_breakdown",
                "params": {"machine_id": 2, "breakdown_start": 0, "breakdown_duration": 4},
                "summary_zh": "3号机故障4小时",
                "reschedule_options": {},
            }
        ),
    ),
    (
        "紧急插单",
        json_line(
            {
                "reasoning_steps": ["用户要插入新工单", "工艺未说明可后续补全"],
                "event_type": "insert_order",
                "params": {"mode": "local_repair", "insert_job": {"name": "急单", "priority": 100, "tasks": []}},
                "summary_zh": "紧急插单",
                "reschedule_options": {},
            }
        ),
    ),
    (
        "订单106交期改为20",
        json_line(
            {
                "reasoning_steps": ["修改指定订单交期", "new_due_date=20"],
                "event_type": "due_date_change",
                "params": {"due_date_changes": [{"job_name": "订单106", "new_due_date": 20}]},
                "summary_zh": "订单106交期改为20",
                "reschedule_options": {},
            }
        ),
    ),
    (
        "1号机停机大修8小时",
        json_line(
            {
                "reasoning_steps": ["计划性停机", "1号机→machine_id=0", "8小时"],
                "event_type": "planned_downtime",
                "params": {
                    "downtime_blocks": [
                        {"machine_id": 0, "start": 0, "end": 8, "label": "planned_downtime"}
                    ]
                },
                "summary_zh": "1号机计划停机8小时",
                "reschedule_options": {},
            }
        ),
    ),
    (
        "工单A加急",
        json_line(
            {
                "reasoning_steps": ["提高优先级", "默认 new_priority=100"],
                "event_type": "priority_change",
                "params": {"changes": [{"job_name": "工单A", "new_priority": 100}]},
                "summary_zh": "工单A加急",
                "reschedule_options": {},
            }
        ),
    ),
    (
        "物料延迟24小时",
        json_line(
            {
                "reasoning_steps": ["到料延迟", "默认作用于首个工单"],
                "event_type": "material_delay",
                "params": {"job_name": "工单A", "delay_hours": 24},
                "summary_zh": "物料延迟24小时",
                "reschedule_options": {},
            }
        ),
    ),
    (
        "撤单工单B",
        json_line(
            {
                "reasoning_steps": ["取消工单"],
                "event_type": "order_cancel",
                "params": {"job_names": ["工单B"]},
                "summary_zh": "撤销工单B",
                "reschedule_options": {},
            }
        ),
    ),
    (
        "9小时后插单急单「特急A」",
        json_line(
            {
                "reasoning_steps": ["插单", "freeze_time=9", "工单名特急A"],
                "event_type": "insert_order",
                "params": {
                    "mode": "local_repair",
                    "freeze_time": 9,
                    "insert_job": {"name": "特急A", "priority": 100, "tasks": []},
                },
                "summary_zh": "9小时后插入特急A",
                "reschedule_options": {},
            }
        ),
    ),
]


def event_system() -> str:
    event_types = list(_EVENT_TYPES)
    return build_structured_prompt(
        role="你是 MES「异常重排 Agent」的参数解析专家，负责把车间主管的中文描述转为结构化 event 信封，供 events.reschedule 等 Tool 直接调用。",
        scope=(
            "你只负责解析动态事件类型与 params，不执行重排、不生成甘特、不回答交期风险问询。"
            "若用户仅问「交期能不能满足」而无改期/重排指令，不应在本节点处理（属于 commitment Agent）。"
        ),
        tool_scope=f"event_type 只能是：{json.dumps(event_types, ensure_ascii=False)}",
        business_rules="""判定优先级（冲突时从上到下）：
1. 插入新工单/急单/新增订单 → insert_order（即使同时提到重排）
2. 修改某工单/订单交期数值 → due_date_change
3. 设备故障/坏了/breakdown → machine_breakdown
4. 计划性停机/大修 → planned_downtime
5. 物料晚到/延迟到料 → material_delay
6. 加急/改优先级 → priority_change
7. 取消/撤单 → order_cancel
8. 改数量 → quantity_change

params 结构：
- machine_breakdown: machine_id(0起算), breakdown_start, breakdown_duration(小时)
- insert_order: mode=local_repair|global；freeze_time(小时)；insert_job 可留空 tasks 由后续补全
- planned_downtime: downtime_blocks [{machine_id, start, end, label}]
- material_delay: job_name, delay_hours
- priority_change: changes [{job_name, new_priority}]
- order_cancel: job_names[]
- quantity_change: changes [{job_name, new_quantity}]
- due_date_change: due_date_changes [{job_name, new_due_date}]

机台：「N号机」→ machine_id = N-1。
时间：必须是数字小时；「现在/马上」→ 0；禁止输出 "now" 字符串。
「全局重排/全局插单」→ insert_order.mode=global。""",
        output_format="""JSON 字段：
- reasoning_steps：2～4 条简短中文（必须先写）
- event_type：上表之一
- params：对象
- summary_zh：面向用户的一句话
- reschedule_options：对象，可为 {}""",
        few_shots=_EVENT_FEW_SHOTS,
    )


def event_user(message: str, *, job_names: Optional[List[str]] = None) -> str:
    ctx: List[str] = []
    if job_names:
        ctx.append(f"当前工单名称列表（job_name 须从中选取或用户明确指定的名称）：{json.dumps(job_names, ensure_ascii=False)}")
    return build_user_message(message, context_lines=ctx)


_PLAN_FEW_SHOTS: Dict[str, tuple] = {
    "scheduling": (
        (
            "有哪些算法",
            '{"reasoning_steps":["用户查目录","单步即可"],"steps":[{"step_id":"s0","tool":"scheduling.list_catalog","params":{},"optional":false}]}',
        ),
        (
            "帮我排一下",
            '{"reasoning_steps":["目标模糊","阻塞澄清"],"steps":[{"step_id":"s0","tool":"scheduling.ask_clarification","params":{},"optional":false}]}',
        ),
        (
            "交付优先，对比禁忌搜索和 SPT",
            '{"reasoning_steps":["先解析","再执行"],"steps":[{"step_id":"s1","tool":"scheduling.parse_intent","params":{},"optional":false},{"step_id":"s2","tool":"scheduling.run","params":{},"optional":false}]}',
        ),
        (
            "对当前计划排程并落库",
            '{"reasoning_steps":["加载计划","解析排程","交期评估","提议落库"],"steps":[{"step_id":"s0","tool":"data.load_plan","params":{},"optional":false},{"step_id":"s1","tool":"scheduling.parse_intent","params":{},"optional":false},{"step_id":"s2","tool":"scheduling.run","params":{},"optional":false},{"step_id":"s3","tool":"delivery.assess","params":{},"optional":false},{"step_id":"s4","tool":"data.propose_persist","params":{},"optional":false}]}',
        ),
    ),
    "events": (
        (
            "支持哪些异常",
            '{"reasoning_steps":["能力问询"],"steps":[{"step_id":"s0","tool":"events.list_event_types","params":{},"optional":false}]}',
        ),
        (
            "3号机故障4小时",
            '{"reasoning_steps":["解析","校验","重排","解读"],"steps":[{"step_id":"s0","tool":"execution.get_state","params":{},"optional":true},{"step_id":"s1","tool":"events.parse_event","params":{},"optional":false},{"step_id":"s1b","tool":"events.check_insert_job","params":{},"optional":false},{"step_id":"s2","tool":"events.reschedule","params":{},"optional":false},{"step_id":"s4","tool":"delivery.explain_impact","params":{},"optional":false}]}',
        ),
    ),
    "plans": (
        (
            "新建计划试产01",
            '{"reasoning_steps":["新建档案"],"steps":[{"step_id":"s1","tool":"data.create_plan","params":{"plan_name":"试产01"},"optional":false}]}',
        ),
        (
            "查看计划A",
            '{"reasoning_steps":["绑定具名计划"],"steps":[{"step_id":"s1","tool":"data.bind_plan","params":{"query":"A","navigate_aps":true},"optional":false}]}',
        ),
    ),
    "kitting": (
        (
            "缺料会导致哪些工单延期",
            '{"reasoning_steps":["静态齐套","推算延迟","报告"],"steps":[{"step_id":"s1","tool":"material.check_static","params":{},"optional":false},{"step_id":"s2","tool":"material.compute_delays","params":{},"optional":false},{"step_id":"s3","tool":"kitting.build_report","params":{},"optional":false}]}',
        ),
        (
            "检查一下齐套能否开工",
            '{"reasoning_steps":["静态齐套检查","出报告"],"steps":[{"step_id":"s1","tool":"material.check_static","params":{},"optional":false},{"step_id":"s2","tool":"material.compute_delays","params":{},"optional":true},{"step_id":"s3","tool":"kitting.build_report","params":{},"optional":false}]}',
        ),
        (
            "先排程再预测物料",
            '{"reasoning_steps":["先跑排程","再物料仿真"],"steps":[{"step_id":"s1","tool":"scheduling.run","params":{"solvers":["spt"]},"optional":false},{"step_id":"s2","tool":"material.predict","params":{},"optional":false},{"step_id":"s3","tool":"kitting.build_report","params":{},"optional":false}]}',
        ),
    ),
    "commitment": (
        (
            "交期能不能满足客户",
            '{"reasoning_steps":["用已有排程评估","不重新排程"],"steps":[{"step_id":"s1","tool":"delivery.assess","params":{},"optional":false},{"step_id":"s2","tool":"delivery.customer_script","params":{},"optional":true}]}',
        ),
    ),
    "whatif": (
        (
            "对比一下交付优先和吞吐优先",
            '{"reasoning_steps":["多方案对比","用 compare.variants"],"steps":[{"step_id":"s1","tool":"compare.variants","params":{"variants":[{"variant_id":"delivery","label":"交付优先"},{"variant_id":"throughput","label":"吞吐优先"}]},"optional":false}]}',
        ),
    ),
}


def plan_system(*, agent_id: str, name_zh: str, allowed_tools: List[str]) -> str:
    tools = [{"tool": t, "hint": _TOOL_HINTS.get(t, "")} for t in allowed_tools]
    hint = _AGENT_PLAN_HINTS.get(agent_id, "")
    few = _PLAN_FEW_SHOTS.get(agent_id, ())
    return build_structured_prompt(
        role=f"你是 MES「{name_zh}」内部的 Plan-and-Solve 规划器，负责生成可执行的 Tool 调用链。",
        scope="你只规划、不执行；复杂数据在 context 中，params 可留空 {}。",
        tool_scope=json.dumps(tools, ensure_ascii=False),
        business_rules=hint or "按用户意图选择最短可执行链。",
        output_format="""JSON 字段：
- reasoning_steps：2～4 条简短中文（先写）
- steps：数组；每项含 step_id、tool、params(对象)、optional(布尔，默认 false)
- tool 必须来自允许列表；顺序应可执行""",
        few_shots=few if few else None,
    )


def plan_user(*, agent_id: str, message: str, params: Optional[Dict[str, Any]] = None) -> str:
    ctx: List[str] = []
    if agent_id == "events":
        ctx.append(
            "若 events:insert_job_intake.status=need_input，应 merge_insert_job → check_insert_job "
            "→ reschedule → explain_impact。"
        )
    if agent_id == "kitting" and params and params.get("mode"):
        ctx.append(f"约束：mode={params['mode']}（check_only | schedule_then_predict | kit_then_schedule）。")
    if agent_id == "whatif" and params and params.get("strategy_ids"):
        ctx.append(f"已指定 strategy_ids：{params['strategy_ids']}")
    if agent_id == "scheduling" and params:
        if params.get("confirm_token"):
            ctx.append(
                "约束：params 含 confirm_token，只规划单步 data.confirm_persist，"
                "params 使用提供的 confirm_token，不要 parse/run。"
            )
        elif params.get("persist_after"):
            ctx.append(
                "约束：persist_after=true，排程后须 delivery.assess 与 data.propose_persist；"
                "有 plan 时可先 data.load_plan。"
            )
    if params:
        if params.get("skip_parse"):
            ctx.append("约束：skip_parse=true，可跳过 parse 类工具。")
        if params.get("solvers"):
            ctx.append(f"已指定 solvers：{params['solvers']}")
    return build_user_message(message, context_lines=ctx)


_REACT_FEW_SHOTS = [
    (
        "（已执行 parse_intent，artifacts 含 interpretation）",
        json_line(
            {
                "action": "call_tool",
                "tool": "scheduling.run",
                "params": {},
                "reasoning_zh": "解析完成，执行排程",
            }
        ),
    ),
    (
        "（排程已完成，artifacts 含 compare_result）",
        json_line(
            {
                "action": "finish",
                "answer": "排程对比已完成，可在结果区查看甘特与指标。",
                "reasoning_zh": "无后续工具",
            }
        ),
    ),
]


def react_system(*, agent_id: str, name_zh: str, allowed_tools: List[str]) -> str:
    tools = [{"tool": t, "hint": _TOOL_HINTS.get(t, "")} for t in allowed_tools]
    hint = _AGENT_PLAN_HINTS.get(agent_id, "")
    return build_structured_prompt(
        role=f"你是 MES「{name_zh}」的执行 Agent（ReAct 单步决策）。",
        scope="根据用户消息、已执行步骤与 artifacts，每轮只选一个工具或结束；不编造未执行的结果。",
        tool_scope=json.dumps(tools, ensure_ascii=False),
        business_rules=hint or "按用户意图逐步执行，先解析再计算再解读。",
        output_format="""JSON（不要 markdown）：
- action：finish 或 call_tool
- tool：action=call_tool 时必填，且必须来自允许列表
- params：工具参数字典，可为 {}
- answer：action=finish 时必填，面向用户的中文摘要
- reasoning_zh：可选，一步决策理由（≤80字）""",
        few_shots=_REACT_FEW_SHOTS,
    )


def react_user(
    *,
    agent_id: str,
    message: str,
    params: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
) -> str:
    parts = [f"用户消息：{(message or '').strip() or '（无）'}"]
    if params:
        if params.get("skip_parse"):
            parts.append("约束：skip_parse=true")
        if params.get("event_envelope"):
            parts.append("已有 event_envelope，可跳过 parse_event")
    hist = history or []
    if hist:
        parts.append("已执行步骤：")
        for h in hist[-6:]:
            parts.append(
                f"- {h.get('tool')}: {'ok' if h.get('ok') else 'fail'} "
                f"{h.get('note') or h.get('error') or ''}"
            )
    art = artifacts or {}
    art_keys = [k for k in art.keys() if not k.startswith("_")][:12]
    if art_keys:
        parts.append(f"当前 artifacts 键：{', '.join(art_keys)}")
    if agent_id == "events" and (art.get("insert_job_intake") or {}).get("status") == "need_input":
        parts.append("插单信息不完整：优先 events.merge_insert_job 或向用户追问，勿直接 reschedule。")
    return "\n".join(parts)


_REFLECT_FEW_SHOTS = [
    (
        "scheduling.run 失败：缺少 custom_data",
        json_line(
            {
                "is_valid": False,
                "action": "clarify",
                "message_zh": "请先在数据中心加载工单或绑定计划后再排程。",
            }
        ),
    ),
    (
        "events.reschedule 失败：同一错误第 2 次",
        json_line(
            {
                "is_valid": False,
                "action": "human",
                "message_zh": "重排连续失败，请人工核对事件参数与执行态。",
            }
        ),
    ),
]


def reflect_system(*, agent_id: str, name_zh: str, allowed_tools: List[str]) -> str:
    tools = [{"tool": t, "hint": _TOOL_HINTS.get(t, "")} for t in allowed_tools]
    return build_structured_prompt(
        role=f"你是 MES「{name_zh}」的反思 Agent。",
        scope="某一步 Tool 执行失败，判断 retry / 向用户澄清 / 人工介入 / 带说明结束。",
        tool_scope=json.dumps(tools, ensure_ascii=False),
        business_rules="""action=human（勿编造数据）当：
- 批量变更影响多个工单交期且无法自动修复
- 缺少关键业务数据且无法从消息推断
- 同一错误已重试仍失败""",
        output_format="""JSON（不要 markdown）：
- is_valid：当前路径是否仍可继续（布尔）
- action：retry | finish | clarify | human
- tool/params：action=retry 时给出修正后的工具与参数
- message_zh：finish/clarify/human 时必填
- feedback_zh：retry 时给下一步的简短修正建议""",
        few_shots=_REFLECT_FEW_SHOTS,
    )


def reflect_user(
    *,
    agent_id: str,
    message: str,
    failed_tool: str,
    error: str,
    retry_count: int = 0,
    params: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
) -> str:
    parts = [
        f"用户消息：{(message or '').strip() or '（无）'}",
        f"失败工具：{failed_tool}",
        f"错误信息：{(error or '')[:400]}",
        f"已重试次数：{retry_count}",
    ]
    hist = history or []
    if hist:
        parts.append("此前步骤：")
        for h in hist[-5:]:
            parts.append(
                f"- {h.get('tool')}: {'ok' if h.get('ok') else 'fail'} "
                f"{h.get('error') or h.get('note') or ''}"
            )
    art = artifacts or {}
    art_keys = [k for k in art.keys() if not k.startswith("_")][:10]
    if art_keys:
        parts.append(f"artifacts 键：{', '.join(art_keys)}")
    if params and params.get("event_envelope"):
        parts.append("已有 event_envelope，重试 reschedule 时请带上。")
    return "\n".join(parts)


_PLANS_ACTIONS = (
    "create",
    "list",
    "delete",
    "view",
    "bind",
    "rename",
    "duplicate",
    "update_status",
    "clear",
    "goto_aps",
)


_PLANS_FEW_SHOTS = [
    (
        "新建计划试产01",
        json_line(
            {
                "reasoning_steps": ["用户要新建档案", "名称试产01", "不是 list/delete", "选 create"],
                "action": "create",
                "plan_name": "试产01",
                "query": "",
                "new_name": "",
                "status": "",
                "summary_zh": "新建计划试产01",
            }
        ),
    ),
    (
        "查看计划sss",
        json_line(
            {
                "reasoning_steps": ["查看具名计划 sss", "sss 是计划名不是「所有」", "不是 list", "选 view"],
                "action": "view",
                "plan_name": "",
                "query": "sss",
                "new_name": "",
                "status": "",
                "summary_zh": "查看并绑定计划 sss",
            }
        ),
    ),
    (
        "查看所有计划",
        json_line(
            {
                "reasoning_steps": ["查看全部计划", "无具名 query", "选 list"],
                "action": "list",
                "plan_name": "",
                "query": "",
                "new_name": "",
                "status": "",
                "summary_zh": "列出全部计划",
            }
        ),
    ),
    (
        "加载计划试产01",
        json_line(
            {
                "reasoning_steps": ["加载具名计划", "选 bind"],
                "action": "bind",
                "plan_name": "",
                "query": "试产01",
                "new_name": "",
                "status": "",
                "summary_zh": "加载计划试产01",
            }
        ),
    ),
    (
        "删除计划旧版",
        json_line(
            {
                "reasoning_steps": ["删除档案", "不跳转 APS", "选 delete"],
                "action": "delete",
                "plan_name": "",
                "query": "旧版",
                "new_name": "",
                "status": "",
                "summary_zh": "删除计划旧版",
            }
        ),
    ),
    (
        "把计划A改名为计划B",
        json_line(
            {
                "reasoning_steps": ["重命名", "旧名A新名B", "选 rename"],
                "action": "rename",
                "plan_name": "",
                "query": "A",
                "new_name": "B",
                "status": "",
                "summary_zh": "计划A改名为B",
            }
        ),
    ),
    (
        "复制计划试产01为试产02",
        json_line(
            {
                "reasoning_steps": ["复制计划", "源试产01目标试产02", "选 duplicate"],
                "action": "duplicate",
                "plan_name": "",
                "query": "试产01",
                "new_name": "试产02",
                "status": "",
                "summary_zh": "复制试产01为试产02",
            }
        ),
    ),
    (
        "标记计划A为已完成",
        json_line(
            {
                "reasoning_steps": ["改状态", "status=done", "选 update_status"],
                "action": "update_status",
                "plan_name": "",
                "query": "A",
                "new_name": "",
                "status": "done",
                "summary_zh": "标记计划A已完成",
            }
        ),
    ),
]


def plans_intent_system() -> str:
    return build_structured_prompt(
        role="你是 MES「计划库管理」专用意图解析器，负责把用户对 MongoDB 计划档案库的操作描述转为结构化 action。",
        scope=(
            "你只解析计划库 CRUD 与跳转 APS 意图，不执行排程计算、不解析车间异常事件。"
            "「用遗传算法排产」等排程类语句不属于本解析器。"
        ),
        tool_scope=f"action 必须且只能是：{json.dumps(list(_PLANS_ACTIONS), ensure_ascii=False)}",
        business_rules="""各 action 语义与是否跳转 APS（智能排程页 /aps）：
| action | 含义 | 完成后跳转 APS |
| create | 新建空计划档案 | 是 |
| view | 查看/查询具名计划（加载并绑定） | 是 |
| bind | 加载/打开/切换/使用具名计划 | 是 |
| rename | 重命名计划 | 是 |
| duplicate | 复制计划为新计划 | 是 |
| update_status | 修改计划状态 pending/done/archived | 是 |
| goto_aps | 仅打开智能排程页面 | 是 |
| list | 列出/刷新全部计划（不绑定具体计划） | 否 |
| delete | 删除具名计划 | 否 |
| clear | 解绑当前计划 | 否 |

判别优先级：
1. view / bind / list 三分法：句末或「计划」后紧跟具体名称 → view 或 bind；「所有/全部/列表」→ list
2. create：新建/创建/添加 + 计划，可解析 plan_name
3. delete：删除/删掉/移除 + 计划 + 名称（不跳转 APS）
4. rename / duplicate：query=源计划，new_name=新名
5. update_status：status=pending|done|archived
6. 模糊输入 → action=list，各字段留空

禁止：仅因句中出现单字「查」「看」「计划」就判 list；必须分析整句结构。""",
        output_format="""JSON 字段（全部必填，无值用空字符串）：
- reasoning_steps：3～6 条简短中文，先写此项；说明为何不是 list/delete、如何提取 query
- action：上表之一
- plan_name：create 时的新计划名
- query：目标计划名（bind/view/delete/rename/duplicate/update_status）
- new_name：rename/duplicate 的新名称
- status：update_status 时 pending|done|archived，否则 ""
- summary_zh：一句话中文摘要""",
        few_shots=_PLANS_FEW_SHOTS,
    )


def plans_intent_user(message: str) -> str:
    return build_user_message(
        message,
        context_lines=[
            "反例：「查看计划sss」绝不是 list（「查看」含「查」字但后面是具名计划）。",
            "反例：「用遗传算法排产」不属于本解析器。",
        ],
    )


def insert_job_followup_system() -> str:
    return """你是 MES 插单工艺补全助手。用户正在多轮对话中补充插单工单的工序细节。
只输出一个 JSON 对象，不要 markdown。

输出字段：
- name: 工单名称（可选，若用户未提则省略）
- priority: 整数优先级（可选）
- due_date: 交期小时数（可选）
- confirm_default_stub: 布尔，用户明确说「确认默认/使用默认工艺」时为 true
- tasks: 数组，每项含 name, machine_id(0起算), duration(小时)；用户说 N号机 → machine_id=N-1

若用户一次补充多道工序，tasks 应包含多条。只输出 JSON。"""


def insert_job_followup_user(message: str, *, draft: Optional[Dict[str, Any]] = None) -> str:
    parts = [f"用户补充：{message.strip()}"]
    if draft:
        parts.append(f"当前草稿：{json.dumps(draft, ensure_ascii=False)}")
    return "\n".join(parts)


def summarize_system(*, agent_id: str, name_zh: str) -> str:
    return build_structured_prompt(
        role=f"你是 MES「{name_zh}」的汇报助手，负责把 Tool 执行结果组织成车间主管能直接看懂的中文答复。",
        scope=(
            "你只根据已执行的 Tool 结果与用户原始问题生成 summary，不重新解析参数、不调用 Tool。"
            "禁止编造 artifacts 中不存在的数据；数字、工单名、算法名须来自 Tool 结果。"
        ),
        output_format="""JSON 字段：
- reasoning_steps：2～3 条简短中文（先写）
- summary_zh：2～4 句面向用户的完整答复
- follow_up：可选，若需用户补充信息则填写追问，否则 null""",
        business_rules="""写作要求：
- 先回答用户「做了什么、结果如何」
- 排程类：提及最优算法/完工时间/是否可查看报表
- 异常重排类：提及事件类型、影响工单数、是否可查看双甘特
- 计划库类：提及计划名、工单数、是否已跳转排程中心
- 若 status 为 need_input / pending_clarification，summary 改为清晰追问""",
        few_shots=[
            (
                "用户：3号机坏了4小时；Tool：重排完成，2个工单拖期",
                json_line(
                    {
                        "reasoning_steps": ["故障重排已完成", "2工单拖期"],
                        "summary_zh": "已按3号机故障4小时完成重排。共有2个工单交期受影响，可在生产看板查看双甘特对比。",
                        "follow_up": None,
                    }
                ),
            ),
            (
                "用户：交付优先排程；Tool：对比8个算法，ts最优 makespan=42",
                json_line(
                    {
                        "reasoning_steps": ["全量对比完成", "ts最优"],
                        "summary_zh": "已按交付优先对比8种算法，禁忌搜索完工时间最短（42）。请点击「查看分析报表」查看甘特与指标。",
                        "follow_up": None,
                    }
                ),
            ),
        ],
    )


def summarize_user(
    *,
    message: str,
    agent_id: str,
    plan_log: Optional[List[Dict[str, Any]]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
) -> str:
    parts = [f"用户原始问题：{(message or '').strip() or '（无）'}"]
    log = plan_log or []
    if log:
        parts.append("已执行 Tool：")
        for entry in log[-8:]:
            parts.append(
                f"- {entry.get('tool')} ({entry.get('status')})"
                + (f" err={entry.get('error')}" if entry.get("error") else "")
            )
    art = artifacts or {}
    # 只传摘要性字段，避免 token 爆炸
    summary_keys = (
        "interpretation",
        "impact_summary",
        "schedule_results",
        "event_envelope",
        "active_plan",
        "insert_job_intake",
    )
    payload: Dict[str, Any] = {}
    for k in summary_keys:
        if k in art:
            v = art[k]
            if k == "schedule_results" and isinstance(v, dict):
                payload[k] = {
                    sid: {
                        "name": (r or {}).get("name"),
                        "best_score": (r or {}).get("best_score"),
                        "error": (r or {}).get("error"),
                    }
                    for sid, r in list(v.items())[:8]
                    if isinstance(r, dict)
                }
            elif k == "impact_summary" and isinstance(v, dict):
                payload[k] = {kk: v.get(kk) for kk in ("summary_zh", "delay_count") if kk in v}
            else:
                payload[k] = v
    if payload:
        parts.append(f"Tool 结果摘要：{json.dumps(payload, ensure_ascii=False)[:3000]}")
    return "\n".join(parts)
