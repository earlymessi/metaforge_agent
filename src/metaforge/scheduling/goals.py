"""排程业务目标推断与多算法结果选优。

自然语言目标判别主路径：``orchestrator/llm/prompts.scheduling_*``（LLM 输出 schedule_goal / strategy_id / full_compare）。
本模块 ``GOAL_DEFINITIONS`` 供 prompt 引用；``infer_schedule_goal`` 等仅在离线 fallback 与后处理门控中使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

GOAL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "goal_id": "makespan",
        "name_zh": "最短完工时间",
        "recommend_metric": "makespan",
        "strategy_id": "makespan",
        "keywords": [
            "最短",
            "完工时间",
            "加工时间最短",
            "周期短",
            "makespan",
            "最短时间",
            "时间最短",
            "最短完工",
        ],
    },
    {
        "goal_id": "throughput",
        "name_zh": "产能/吞吐优先",
        "recommend_metric": "makespan",
        "strategy_id": "throughput",
        "keywords": ["产能", "吞吐", "产量", "产出"],
    },
    {
        "goal_id": "weighted_tardiness_total",
        "name_zh": "最少拖期/交期违约",
        "recommend_metric": "weighted_tardiness_total",
        "strategy_id": "delivery",
        "keywords": [
            "拖期",
            "延期",
            "交期",
            "交付",
            "按期",
            "违约",
            "逾期",
            "tardiness",
            "急单",
            "交付优先",
        ],
    },
    {
        "goal_id": "energy_cost",
        "name_zh": "最低能耗成本",
        "recommend_metric": "score",
        "strategy_id": "cost",
        "keywords": ["能耗", "成本", "省电", "电费", "能源"],
    },
    {
        "goal_id": "machine_busy_cv",
        "name_zh": "负载最均衡",
        "recommend_metric": "score",
        "strategy_id": "balance_load",
        "keywords": ["负载均衡", "均衡", "平衡负载", "机器负载", "负荷均衡"],
    },
]

METRIC_LABELS_ZH: Dict[str, str] = {
    "makespan": "完工时间（makespan）",
    "weighted_tardiness_total": "加权拖期",
    "energy_cost": "能耗成本",
    "machine_busy_cv": "负载均衡系数",
    "composite": "综合评分",
    "score": "综合评分",
}

_METRIC_TIE_EPS = 1e-4

# 用户明确点名要用的算法族（非业务目标描述）
_NAMED_ALGORITHM_HINTS = (
    "遗传",
    "禁忌",
    "模拟退火",
    "蚁群",
    "蚁群算法",
    "spt",
    "edd",
    "lpt",
    "mwkr",
    "q学习",
    "dqn",
    "ppo",
    "用算法",
    "指定算法",
)


def user_named_specific_algorithm(message: str) -> bool:
    text = (message or "").lower()
    raw = message or ""
    return any(h.lower() in text or h in raw for h in _NAMED_ALGORITHM_HINTS)


_FULL_COMPARE_HINTS = (
    "对比",
    "比较",
    "都跑",
    "所有算法",
    "全部算法",
    "哪个最好",
    "最优方案",
)


@dataclass
class ScheduleGoalInference:
    goal_id: str
    goal_name_zh: str
    recommend_metric: str
    strategy_id: str
    strategy_name: str
    matched_keyword: str = ""
    confidence: float = 0.0

    @property
    def is_clear(self) -> bool:
        return self.confidence >= 0.5 and self.goal_id != "composite"


def goal_definitions_for_prompt() -> List[Dict[str, str]]:
    """供 scheduling prompt 引用的目标目录（不含关键词权重逻辑）。"""
    return [
        {
            "goal_id": str(g["goal_id"]),
            "name_zh": str(g["name_zh"]),
            "strategy_id": str(g["strategy_id"]),
            "recommend_metric": str(g["recommend_metric"]),
        }
        for g in GOAL_DEFINITIONS
    ]


def infer_schedule_goal(message: str) -> ScheduleGoalInference:
    """离线 fallback：按关键词长度竞争推断业务目标（LLM 不可用或后处理补充）。"""
    from metaforge.agent.scheduling_agent import _STRATEGY_BY_ID

    text = (message or "").strip()
    if not text:
        return _default_goal()

    best_def: Optional[Dict[str, Any]] = None
    best_kw = ""
    best_score = 0

    for gdef in GOAL_DEFINITIONS:
        for kw in gdef["keywords"]:
            if kw.lower() in text.lower() or kw in text:
                score = len(kw)
                if score > best_score:
                    best_score = score
                    best_def = gdef
                    best_kw = kw

    if not best_def:
        return _default_goal()

    sid = str(best_def["strategy_id"])
    tpl = _STRATEGY_BY_ID.get(sid) or _STRATEGY_BY_ID["balanced"]
    conf = min(0.95, 0.65 + best_score * 0.05)
    return ScheduleGoalInference(
        goal_id=str(best_def["goal_id"]),
        goal_name_zh=str(best_def["name_zh"]),
        recommend_metric=str(best_def["recommend_metric"]),
        strategy_id=sid,
        strategy_name=str(tpl["name"]),
        matched_keyword=best_kw,
        confidence=conf,
    )


_AMBIGUOUS_GOAL_PHRASES = (
    "满意度",
    "满意",
    "用户体验",
    "体验最好",
    "效果最好",
    "最理想",
    "尽可能好",
    "越好越好",
    "品质最高",
)


_CLARIFICATION_OPTION_MARKERS: List[Tuple[Tuple[str, ...], str]] = [
    (("①", "1", "一", "选项1", "选1", "第一个"), "weighted_tardiness_total"),
    (("②", "2", "二", "选项2", "选2", "第二个"), "makespan"),
    (("③", "3", "三", "选项3", "选3", "第三个"), "energy_cost"),
    (("④", "4", "四", "选项4", "选4", "第四个"), "machine_busy_cv"),
]


def clarification_reply_wants_full_compare(message: str) -> bool:
    """澄清续答是否应触发全量算法对比（菜单选项或显式对比用语）。"""
    text = (message or "").strip()
    if not text:
        return False
    if any(h in text for h in _FULL_COMPARE_HINTS):
        return True
    return any(any(m in text for m in markers) for markers, _ in _CLARIFICATION_OPTION_MARKERS)


def _inference_from_goal_id(goal_id: str, *, matched_keyword: str = "") -> ScheduleGoalInference:
    from metaforge.agent.scheduling_agent import _STRATEGY_BY_ID

    gdef = next((g for g in GOAL_DEFINITIONS if g["goal_id"] == goal_id), None)
    if not gdef:
        return _default_goal()
    sid = str(gdef["strategy_id"])
    tpl = _STRATEGY_BY_ID.get(sid) or _STRATEGY_BY_ID["balanced"]
    return ScheduleGoalInference(
        goal_id=str(gdef["goal_id"]),
        goal_name_zh=str(gdef["name_zh"]),
        recommend_metric=str(gdef["recommend_metric"]),
        strategy_id=sid,
        strategy_name=str(tpl["name"]),
        matched_keyword=matched_keyword,
        confidence=0.92,
    )


def parse_clarification_reply(reply: str) -> Optional[ScheduleGoalInference]:
    """解析用户对澄清问题的续答（①②③ 或 自然语言目标），不拼接含「满意度」的原问。"""
    text = (reply or "").strip()
    if not text:
        return None
    for markers, goal_id in _CLARIFICATION_OPTION_MARKERS:
        if any(m in text for m in markers):
            hit = next((m for m in markers if m in text), markers[0])
            return _inference_from_goal_id(goal_id, matched_keyword=hit)
    inf = infer_schedule_goal(text)
    if inf.is_clear:
        return inf
    return None


def detect_unmapped_goal_phrase(message: str) -> Optional[str]:
    """无法映射到 makespan/拖期/能耗/负载 等业务目标的表述。"""
    text = (message or "").strip()
    for phrase in _AMBIGUOUS_GOAL_PHRASES:
        if phrase in text:
            return phrase
    return None


def is_under_specified_scheduling_goal(
    message: str, inference: Optional[ScheduleGoalInference] = None
) -> bool:
    """有排程意图但未给出可执行的业务目标（且非明确点名算法）。"""
    if detect_unmapped_goal_phrase(message):
        return True
    inf = inference or infer_schedule_goal(message)
    if inf.is_clear:
        return False
    text = (message or "").strip()
    if not any(k in text for k in ("排程", "排产", "排一下", "调度", "甘特")):
        return False
    if user_named_specific_algorithm(text):
        return False
    if any(k in text for k in ("最好", "最高", "最优", "尽量", "尽可能")):
        return True
    return len(text) <= 20 and "排" in text


def _default_goal() -> ScheduleGoalInference:
    from metaforge.agent.scheduling_agent import _STRATEGY_BY_ID

    tpl = _STRATEGY_BY_ID["balanced"]
    return ScheduleGoalInference(
        goal_id="composite",
        goal_name_zh="综合最优",
        recommend_metric="score",
        strategy_id="balanced",
        strategy_name=str(tpl["name"]),
        matched_keyword="",
        confidence=0.0,
    )


def should_run_full_compare(
    inference: ScheduleGoalInference,
    message: str,
    *,
    explicit_solvers: bool = False,
    is_fast: bool = False,
) -> bool:
    """用户未指定单一算法，且表达了可识别的业务目标（或要求全量对比）。"""
    if explicit_solvers or is_fast or user_named_specific_algorithm(message):
        return False
    text = (message or "").strip()
    if any(h in text for h in _FULL_COMPARE_HINTS):
        return True
    return inference.is_clear


def metric_value_from_entry(entry: Dict[str, Any], metric: str) -> float:
    if entry.get("error"):
        return float("inf")
    metrics = entry.get("metrics") or {}
    if metric in ("composite", "score"):
        sc = entry.get("score")
        if sc is not None:
            return float(sc)
        return float(metrics.get("composite_score") or float("inf"))
    if metric == "makespan":
        v = metrics.get("makespan")
        if v is not None:
            return float(v)
        return float(entry.get("best_score") or entry.get("makespan") or float("inf"))
    v = metrics.get(metric)
    if v is not None:
        return float(v)
    return float("inf")


def pick_best_schedule(
    schedule_results: Dict[str, Any],
    *,
    recommend_metric: str = "makespan",
    tiebreak_metric: str = "score",
) -> Tuple[Optional[str], Dict[str, Any], float]:
    """按业务目标指标从多算法结果中选取最优；主指标持平时用综合评分（与报表一致）。"""
    ranked: List[Tuple[float, float, str, Dict[str, Any]]] = []

    for sid, entry in (schedule_results or {}).items():
        if not isinstance(entry, dict) or entry.get("error"):
            continue
        val = metric_value_from_entry(entry, recommend_metric)
        tb = metric_value_from_entry(entry, tiebreak_metric)
        ranked.append((val, tb, sid, entry))

    if not ranked:
        if schedule_results:
            best_sid = next(iter(schedule_results.keys()))
            best_entry = (
                schedule_results[best_sid]
                if isinstance(schedule_results[best_sid], dict)
                else {}
            )
            return (
                best_sid,
                best_entry,
                metric_value_from_entry(best_entry, recommend_metric),
            )
        return None, {}, float("inf")

    ranked.sort(key=lambda x: (x[0], x[1]))
    best_val, _, best_sid, best_entry = ranked[0]
    if len(ranked) > 1 and recommend_metric != tiebreak_metric:
        tied = [r for r in ranked if abs(r[0] - best_val) <= _METRIC_TIE_EPS]
        if len(tied) > 1:
            tied.sort(key=lambda x: (x[1], x[2]))
            _, _, best_sid, best_entry = tied[0]
            best_val = metric_value_from_entry(best_entry, recommend_metric)

    return best_sid, best_entry, best_val


def goal_summary_note(inference: ScheduleGoalInference, *, n_solvers: int) -> str:
    metric_zh = METRIC_LABELS_ZH.get(inference.recommend_metric, inference.recommend_metric)
    kw = f"（命中：{inference.matched_keyword}）" if inference.matched_keyword else ""
    return (
        f"业务目标：{inference.goal_name_zh}{kw}；"
        f"策略「{inference.strategy_name}」用于多目标加权；"
        f"已在 {n_solvers} 种非 RL 算法中对比，按{metric_zh}选取最优（与报表排名一致）"
    )
