"""6 个业务 Agent 静态元数据（pipeline 已合并入 scheduling）。"""



from __future__ import annotations



from typing import Any, Dict, List



AGENT_REGISTRY: List[Dict[str, Any]] = [

    {

        "id": "scheduling",

        "name_zh": "智能排程 Agent",

        "intent": "schedule",

        "scenario": "排程",

        "replaced_by": "planning_collab",

        "endpoint": "/api/agents/scheduling/run",

        "allowed_tools": [

            "scheduling.parse_intent",

            "scheduling.run",

            "scheduling.list_catalog",

            "scheduling.ask_clarification",

            "data.load_plan",

            "delivery.assess",

            "data.propose_persist",

            "data.confirm_persist",

        ],

        "nl_keywords": [

            "排程",

            "算法",

            "禁忌搜索",

            "遗传",

            "策略",

            "有哪些算法",

            "保存",

            "落库",

            "排程并保存",

        ],

        "implemented": True,

    },

    {

        "id": "events",

        "name_zh": "异常重排 Agent",

        "intent": "reschedule",

        "scenario": "A",

        "endpoint": "/api/agents/events/run",

        "allowed_tools": [

            "execution.get_state",

            "events.list_event_types",

            "events.parse_event",

            "events.merge_insert_job",

            "events.check_insert_job",

            "events.reschedule",

            "delivery.explain_impact",

            "delivery.compare_commitment",

        ],

        "nl_keywords": ["插单", "故障", "改交期", "重排", "支持哪些异常"],

        "implemented": True,

    },

    {

        "id": "kitting",

        "name_zh": "齐套顾问 Agent",

        "intent": "kitting",

        "scenario": "B",

        "endpoint": "/api/agents/kitting/run",

        "allowed_tools": [

            "material.check_static",

            "material.compute_delays",

            "material.predict",

            "scheduling.run",

            "kitting.build_report",

        ],

        "nl_keywords": ["齐套", "缺料", "BOM", "能否开工"],

        "implemented": True,

    },

    {

        "id": "commitment",

        "name_zh": "交期承诺 Agent",

        "intent": "commitment",

        "scenario": "C",

        "endpoint": "/api/agents/commitment/run",

        "allowed_tools": [

            "delivery.assess",

            "delivery.customer_script",

            "scheduling.run",

        ],

        "nl_keywords": ["交期", "承诺", "客户", "延期", "哪些工单可能延期"],

        "implemented": True,

    },

    {

        "id": "whatif",

        "name_zh": "方案对比 Agent",

        "intent": "whatif",

        "scenario": "D",

        "endpoint": "/api/agents/whatif/run",

        "allowed_tools": [

            "scheduling.run",

            "events.reschedule",

            "compare.variants",

            "delivery.assess",

        ],

        "nl_keywords": ["对比", "假设", "如果"],

        "implemented": True,

    },

    {

        "id": "plans",

        "name_zh": "计划管理 Agent",

        "intent": "plans",

        "scenario": "F",

        "endpoint": "/api/agents/plans/run",

        "allowed_tools": [

            "data.list_plans",

            "data.create_plan",

            "data.delete_plan",

            "data.bind_plan",

            "data.rename_plan",

            "data.duplicate_plan",

            "data.update_status",

        ],

        "nl_keywords": ["新建计划", "删除计划", "复制计划", "重命名", "列出计划", "加载计划"],

        "implemented": True,

    },

]





def list_agents() -> List[Dict[str, Any]]:

    return list(AGENT_REGISTRY)


