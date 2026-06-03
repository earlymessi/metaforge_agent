"""统一求解器输出结构，便于 compare_solvers / API / Agent 消费。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SolveResult:
    solver_id: str
    name: str
    makespan: float
    composite_score: float
    sequence: Optional[List[int]] = None
    gantt_data: List[Dict[str, Any]] = field(default_factory=list)
    history: List[float] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    runtime_sec: float = 0.0
    optimization_mode: str = "makespan_only"
    algorithm: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_api_dict(self) -> Dict[str, Any]:
        """转为与现有前端兼容的 JSON 结构。"""
        d = asdict(self)
        # 前端历史字段
        d["id"] = self.solver_id
        d["best_score"] = self.makespan
        d["score"] = self.composite_score
        d["best_solution"] = self.sequence
        return d


def normalize_solver_output(
    raw: Any,
    *,
    solver_id: str,
    display_name: str,
    optimization_mode: str,
    metrics: Optional[Dict[str, Any]] = None,
    composite_score: Optional[float] = None,
) -> SolveResult:
    """将各算法 run() 的 dict 输出规范为 SolveResult。"""
    if not isinstance(raw, dict):
        return SolveResult(
            solver_id=solver_id,
            name=f"{display_name} (Invalid Output)",
            makespan=0.0,
            composite_score=0.0,
            optimization_mode=optimization_mode,
            meta={"error": "non_dict_output"},
        )

    makespan = float(raw.get("best_score", raw.get("makespan", 0)) or 0)
    sequence = raw.get("best_solution")
    if sequence is not None:
        sequence = [int(x) for x in sequence]

    m = dict(metrics or {})
    if "makespan" not in m and makespan:
        m.setdefault("makespan", makespan)

    score = float(composite_score if composite_score is not None else raw.get("score", makespan))

    return SolveResult(
        solver_id=solver_id,
        name=display_name,
        makespan=makespan,
        composite_score=score,
        sequence=sequence,
        gantt_data=list(raw.get("gantt_data") or []),
        history=[float(x) for x in (raw.get("history") or [])],
        metrics=m,
        runtime_sec=float(raw.get("runtime_sec", 0) or 0),
        optimization_mode=optimization_mode,
        algorithm=raw.get("algorithm"),
        meta={k: v for k, v in raw.items() if k not in {
            "best_score", "best_solution", "gantt_data", "history", "runtime_sec", "algorithm", "score", "makespan"
        }},
    )
