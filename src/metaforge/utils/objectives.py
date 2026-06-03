"""多目标优化指标说明（供 API / Agent / 前端统一引用）。"""

from __future__ import annotations

from typing import Any, Dict, List

OBJECTIVES_SCHEMA: List[Dict[str, Any]] = [
    {
        "id": "makespan",
        "name_en": "Makespan",
        "name_zh": "完工时间",
        "direction": "minimize",
        "unit": "time",
        "description_zh": "全部工单中最晚完工时刻，反映整体生产周期。",
        "default_weight": 1.0,
    },
    {
        "id": "weighted_tardiness_total",
        "name_en": "Weighted Tardiness",
        "name_zh": "加权交期违约",
        "direction": "minimize",
        "unit": "time",
        "description_zh": "超过交期的时长之和，并按工单优先级加权（急单权重更高）。",
        "default_weight": 0.5,
    },
    {
        "id": "energy_cost",
        "name_en": "Energy Cost",
        "name_zh": "能耗成本",
        "direction": "minimize",
        "unit": "cost",
        "description_zh": "机台功率 × 分时电价 × 加工时长 的估算成本。",
        "default_weight": 0.05,
    },
    {
        "id": "machine_busy_cv",
        "name_en": "Load Balance (CV)",
        "name_zh": "负载均衡系数",
        "direction": "minimize",
        "unit": "ratio",
        "description_zh": "各机台忙碌时间的变异系数，越小表示负载越均衡。",
        "default_weight": 10.0,
    },
]

COMPOSITE_SCORE_FORMULA = (
    "score = w_makespan×makespan + w_tardiness×weighted_tardiness_total "
    "+ w_energy×energy_cost + w_cv×machine_busy_cv （越小越好）"
)

DEFAULT_WEIGHTS: Dict[str, float] = {
    o["id"]: float(o["default_weight"]) for o in OBJECTIVES_SCHEMA
}


def get_objectives_schema() -> Dict[str, Any]:
    return {
        "objectives": OBJECTIVES_SCHEMA,
        "composite_score_formula": COMPOSITE_SCORE_FORMULA,
        "default_weights": DEFAULT_WEIGHTS,
        "notes": {
            "best_score": "甘特图/收敛曲线使用的 makespan（最大完工时间）",
            "score": "多目标加权综合分，用于策略排序与对比",
        },
    }
