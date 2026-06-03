"""
智能排程 Agent：离线规则回退解析器（非主路径）。

主路径为 ``scheduling/resolve_intent`` → GLM ``scheduling`` prompt → ``finalize_intent``。
本模块仅在 ``LLM_ENABLED=0`` 或 GLM 失败且 ``LLM_FALLBACK_RULE=1`` 时由
``_rule_interpretation`` 调用；自然语言判别规则应维护在
``orchestrator/llm/prompts.scheduling_*`` few-shots 中。

多智能体路由仍可将排程对话转发到 ``POST /api/agent/schedule``，
或 ``parse_only=true`` 预览解析结果。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from metaforge.scheduling.goals import (
    goal_summary_note,
    infer_schedule_goal,
    should_run_full_compare,
)
from metaforge.scheduling.intent_types import (
    CONFIDENCE_HIGH,
    FAST_COMPARE_MAX_SOLVERS,
    FAST_MAKESPAN_BOOST,
    RL_EXCLUDED_FAMILIES,
    ScheduleIntentType,
    detect_list_intent,
)
from metaforge.utils.solver_registry import SOLVER_REGISTRY

# 与 tests/main.py 策略模板保持一致（Agent 内聚，main 从此处导入）
STRATEGY_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "balanced",
        "name": "综合平衡",
        "weights": {
            "makespan": 1.0,
            "weighted_tardiness_total": 0.5,
            "energy_cost": 0.05,
            "machine_busy_cv": 10.0,
        },
    },
    {
        "id": "delivery",
        "name": "交付优先",
        "weights": {
            "makespan": 0.8,
            "weighted_tardiness_total": 2.0,
            "energy_cost": 0.03,
            "machine_busy_cv": 8.0,
        },
    },
    {
        "id": "cost",
        "name": "成本优先",
        "weights": {
            "makespan": 0.6,
            "weighted_tardiness_total": 0.2,
            "energy_cost": 2.5,
            "machine_busy_cv": 4.0,
        },
    },
    {
        "id": "balance_load",
        "name": "负载均衡",
        "weights": {
            "makespan": 0.9,
            "weighted_tardiness_total": 0.4,
            "energy_cost": 0.05,
            "machine_busy_cv": 20.0,
        },
    },
    {
        "id": "makespan",
        "name": "完工时间最短",
        "weights": {
            "makespan": 3.0,
            "weighted_tardiness_total": 0.2,
            "energy_cost": 0.02,
            "machine_busy_cv": 4.0,
        },
    },
    {
        "id": "throughput",
        "name": "吞吐优先",
        "weights": {
            "makespan": 2.0,
            "weighted_tardiness_total": 0.3,
            "energy_cost": 0.02,
            "machine_busy_cv": 5.0,
        },
    },
]

_STRATEGY_BY_ID = {t["id"]: t for t in STRATEGY_TEMPLATES}

_STRATEGY_NL: Dict[str, List[str]] = {
    "delivery": ["交付优先", "交付", "交期", "按期", "急单", "违约", "tardiness"],
    "makespan": [
        "完工时间最短",
        "时间最短",
        "最短时间",
        "最短完工",
        "加工时间最短",
        "makespan",
        "周期短",
        "完工时间",
    ],
    "throughput": ["吞吐", "产能", "产出最大", "产量优先"],
    "cost": ["成本", "能耗", "省电", "电费", "能源"],
    "balance_load": ["负载均衡", "均衡", "平衡负载", "机器负载", "cv"],
    "balanced": ["综合", "平衡", "默认"],
}

_BENCHMARK_RE = re.compile(r"\b(ft\d{2}|la\d{2})\b", re.IGNORECASE)

_COMPARE_HINTS = ("对比", "比较", "多个算法", "分别跑", "都跑", "对比一下", "compare")

_FAST_HINTS = ("快速", "马上", "先出结果", "简单排", "快点")

_MATERIAL_HINTS = ("物料", "缺料", "bom", "库存", "齐套")

_NO_MATERIAL_HINTS = ("不考虑物料", "忽略物料", "不管物料")


def all_non_rl_solvers() -> List[str]:
    """全部非 RL 算法（rule + metaheuristic），按 registry 注册顺序。"""
    return [
        sid
        for sid, spec in SOLVER_REGISTRY.items()
        if spec.family not in RL_EXCLUDED_FAMILIES
    ]


def fast_compare_solvers() -> List[str]:
    """快速对比：非 RL 算法，registry 顺序 rule 优先，再 metaheuristic，上限 6。"""
    out: List[str] = []
    for sid, spec in SOLVER_REGISTRY.items():
        if spec.family in RL_EXCLUDED_FAMILIES:
            continue
        if spec.family == "rule":
            out.append(sid)
    for sid, spec in SOLVER_REGISTRY.items():
        if spec.family == "metaheuristic" and sid not in out:
            out.append(sid)
        if len(out) >= FAST_COMPARE_MAX_SOLVERS:
            return out[:FAST_COMPARE_MAX_SOLVERS]
    return out[:FAST_COMPARE_MAX_SOLVERS]


@dataclass
class ScheduleIntent:
    """Agent 解析后的排程意图（可直接映射 CompareRequest）。"""

    message: str
    solvers: List[str]
    weights: Dict[str, float]
    strategy_id: str
    strategy_name: str
    enforce_material: bool
    benchmark_file: Optional[str] = None
    solver_match_notes: List[str] = field(default_factory=list)
    strategy_match_note: str = ""
    summary_zh: str = ""
    intent_type: str = ScheduleIntentType.RUN_SCHEDULE.value
    confidence: float = 0.75
    is_fast_mode: bool = False
    full_compare: bool = False
    schedule_goal: str = "composite"
    schedule_goal_name_zh: str = "综合最优"
    recommend_metric: str = "score"
    clarification_question: Optional[str] = None
    clarification_context: Optional[Dict[str, Any]] = None

    def to_compare_kwargs(self) -> Dict[str, Any]:
        return {
            "solvers": self.solvers,
            "weights": self.weights,
            "enforce_material": self.enforce_material,
            "benchmark_file": self.benchmark_file,
        }


class SchedulingAgent:
    """规则回退解析器：仅在 LLM 不可用或失败时由 resolve_schedule_intent 调用。"""

    agent_id = "scheduling"
    agent_name_zh = "智能排程"

    @classmethod
    def capabilities(cls) -> Dict[str, Any]:
        return {
            "id": cls.agent_id,
            "name": cls.agent_name_zh,
            "endpoint": "/api/agent/schedule",
            "description_zh": (
                "接收自然语言排程需求，自动选择算法与优化目标权重并执行排程。"
                "多智能体路由时把排程类对话转发到此接口即可。"
            ),
            "inputs": {
                "message": "必填，用户自然语言描述",
                "custom_data": "可选，工单工序数据（与 APS 一致）",
                "benchmark_file": "可选，标准算例文件名",
                "plan_id": "可选，从数据中心加载已保存计划",
                "solvers": "可选，显式覆盖算法列表",
                "weights": "可选，显式覆盖权重",
                "enforce_material": "可选，是否启用物料约束",
                "parse_only": "true 时只解析不计算",
                "async_run": "true 时走异步任务",
            },
            "strategy_templates": [t["id"] for t in STRATEGY_TEMPLATES],
            "solver_count": len(SOLVER_REGISTRY),
        }

    def parse(
        self,
        message: str,
        *,
        solvers: Optional[List[str]] = None,
        weights: Optional[Dict[str, float]] = None,
        strategy_id: Optional[str] = None,
        enforce_material: Optional[bool] = None,
        benchmark_file: Optional[str] = None,
    ) -> ScheduleIntent:
        text = (message or "").strip()
        text_l = text.lower()

        list_type = detect_list_intent(text)
        if list_type:
            return ScheduleIntent(
                message=text,
                solvers=[],
                weights={},
                strategy_id="balanced",
                strategy_name="综合平衡",
                enforce_material=True,
                benchmark_file=None,
                intent_type=list_type.value,
                confidence=CONFIDENCE_HIGH,
                summary_zh="列出可用算法或策略。",
            )

        is_fast = any(h in text for h in _FAST_HINTS)
        goal_inf = infer_schedule_goal(text)
        matched_solvers, solver_notes, had_solver_hit = self._match_solvers(
            text_l, text, is_fast=is_fast
        )
        full_compare = should_run_full_compare(
            goal_inf, text, explicit_solvers=bool(solvers), is_fast=is_fast
        )

        if full_compare:
            matched_solvers = all_non_rl_solvers()
            solver_notes = [
                f"目标驱动全量对比：{goal_inf.goal_name_zh}，"
                f"已选全部 {len(matched_solvers)} 个非 RL 算法，"
                f"跑完后按{goal_inf.goal_name_zh}对应指标选最优"
            ]
            had_solver_hit = True
        elif is_fast and not full_compare:
            if had_solver_hit or any(h in text for h in _COMPARE_HINTS):
                solver_notes = list(solver_notes) + [
                    "检测到「快速」类表述，保留用户指定/命中的算法"
                ]
            else:
                matched_solvers = fast_compare_solvers()
                solver_notes = [
                    "快速对比模式：对比非 RL 算法（rule 优先，再 metaheuristic），"
                    f"最多 {FAST_COMPARE_MAX_SOLVERS} 个，已排除 RL 实验算法"
                ]

        if goal_inf.is_clear and not strategy_id:
            tpl = _STRATEGY_BY_ID[goal_inf.strategy_id]
            w = dict(tpl["weights"])
            sid = goal_inf.strategy_id
            sname = goal_inf.strategy_name
            strat_note = ""
        else:
            w, sid, sname, strat_note = self._match_strategy(text, strategy_id)
        if weights:
            w = dict(weights)
            strat_note = "使用调用方显式传入的 weights"

        if is_fast and w.get("makespan") is not None:
            w = dict(w)
            w["makespan"] = float(w["makespan"]) * FAST_MAKESPAN_BOOST

        bench = benchmark_file
        if not bench:
            m = _BENCHMARK_RE.search(text)
            if m:
                bench = f"{m.group(1).lower()}.txt"

        mat = self._match_material(text, enforce_material)

        final_solvers = solvers if solvers else matched_solvers
        if not final_solvers:
            final_solvers = ["spt", "ts"]

        intent_type = ScheduleIntentType.RUN_BENCHMARK if bench and any(
            k in text for k in ("算例", "benchmark", "跑一下", "跑 ")
        ) else ScheduleIntentType.RUN_SCHEDULE
        if any(h in text for h in _COMPARE_HINTS) or full_compare:
            intent_type = ScheduleIntentType.COMPARE_SOLVERS

        confidence = (
            max(0.9, goal_inf.confidence)
            if full_compare
            else (0.75 if (had_solver_hit or solvers) else 0.55)
        )
        if had_solver_hit and sid != "balanced":
            confidence = max(confidence, 0.85)

        intent = ScheduleIntent(
            message=text,
            solvers=final_solvers,
            weights=w,
            strategy_id=sid,
            strategy_name=sname,
            enforce_material=mat,
            benchmark_file=bench,
            solver_match_notes=solver_notes,
            strategy_match_note=strat_note,
            intent_type=intent_type.value,
            confidence=confidence,
            is_fast_mode=is_fast,
            full_compare=full_compare,
            schedule_goal=goal_inf.goal_id,
            schedule_goal_name_zh=goal_inf.goal_name_zh,
            recommend_metric=goal_inf.recommend_metric if full_compare else "makespan",
        )
        if full_compare:
            strat_note = goal_summary_note(goal_inf, n_solvers=len(final_solvers))
            intent.strategy_match_note = strat_note
        intent.summary_zh = self._build_summary(intent)
        if full_compare:
            intent.summary_zh += f"；{goal_summary_note(goal_inf, n_solvers=len(final_solvers))}"
        elif is_fast and not had_solver_hit and not solvers:
            intent.summary_zh += "；快速对比模式，已排除 RL 实验算法"
        return intent

    def _match_solvers(
        self, text_l: str, text: str, *, is_fast: bool = False
    ) -> Tuple[List[str], List[str], bool]:
        scored: List[Tuple[int, str, List[str]]] = []
        for sid, spec in SOLVER_REGISTRY.items():
            hits: List[str] = []
            candidates = list(spec.nl_keywords) + [spec.name_en, spec.name_zh, spec.id]
            for alias in spec.aliases:
                candidates.append(alias)
            for kw in candidates:
                if not kw:
                    continue
                k = str(kw).lower()
                if k in text_l or kw in text:
                    hits.append(kw)
            if hits:
                scored.append((len(hits), sid, hits))

        scored.sort(key=lambda x: (-x[0], x[1]))
        notes: List[str] = []

        if not scored:
            notes.append("未命中具体算法，默认 SPT + 禁忌搜索对比")
            return ["spt", "ts"], notes, False

        if any(h in text for h in _COMPARE_HINTS):
            solvers = [s[1] for s in scored[:4]]
            notes.append(f"对比模式：{', '.join(solvers)}")
            return solvers, notes, True

        best = scored[0][1]
        notes.append(f"命中算法 {best}（关键词：{', '.join(scored[0][2][:5])}）")
        solvers = [best]
        if (
            not is_fast
            and best not in ("spt", "edd", "lpt")
            and "spt" not in solvers
        ):
            solvers.append("spt")
            notes.append("附加 SPT 作为规则基线")
        return solvers, notes, True

    def _match_strategy(
        self,
        text: str,
        strategy_id: Optional[str],
    ) -> Tuple[Dict[str, float], str, str, str]:
        if strategy_id and strategy_id in _STRATEGY_BY_ID:
            t = _STRATEGY_BY_ID[strategy_id]
            return dict(t["weights"]), t["id"], t["name"], f"使用指定策略模板「{t['name']}」"

        best_id = "balanced"
        best_score = 0
        best_kw = ""
        for tid, keywords in _STRATEGY_NL.items():
            for kw in keywords:
                if kw.lower() in text.lower() or kw in text:
                    if len(kw) > best_score:
                        best_score = len(kw)
                        best_id = tid
                        best_kw = kw

        t = _STRATEGY_BY_ID[best_id]
        note = f"策略「{t['name']}」" + (f"（命中：{best_kw}）" if best_kw else "（默认）")
        return dict(t["weights"]), t["id"], t["name"], note

    def _match_material(self, text: str, override: Optional[bool]) -> bool:
        if override is not None:
            return bool(override)
        tl = text.lower()
        if any(h in text for h in _NO_MATERIAL_HINTS):
            return False
        if any(h.lower() in tl or h in text for h in _MATERIAL_HINTS):
            return True
        return True  # 默认开启，与 APS 页一致

    def _build_summary(self, intent: ScheduleIntent) -> str:
        solver_names = []
        for sid in intent.solvers:
            spec = SOLVER_REGISTRY.get(sid)
            solver_names.append(spec.name_zh if spec else sid)
        parts = [
            f"算法：{'、'.join(solver_names)}",
            f"目标：{intent.strategy_name}",
            f"物料约束：{'开启' if intent.enforce_material else '关闭'}",
        ]
        if intent.benchmark_file:
            parts.append(f"算例：{intent.benchmark_file}")
        return "；".join(parts)
