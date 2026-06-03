"""求解器展示名（兼容旧代码；优先从 SolverRegistry 读取）。"""

from metaforge.utils.solver_registry import SOLVER_REGISTRY, _ALIAS_MAP


def _build_pretty_names() -> dict:
    names = {}
    for sid, spec in SOLVER_REGISTRY.items():
        names[sid] = spec.name_en
        if spec.name_zh:
            names[f"{sid}__zh"] = spec.name_zh
        for alias in spec.aliases:
            names[alias] = spec.name_en
    return names


pretty_names = _build_pretty_names()


def get_display_name(solver_id: str, *, prefer_zh: bool = False) -> str:
    sid = _ALIAS_MAP.get((solver_id or "").strip().lower(), (solver_id or "").strip().lower())
    spec = SOLVER_REGISTRY.get(sid)
    if not spec:
        return solver_id
    if prefer_zh and spec.name_zh:
        return spec.name_zh
    return spec.name_en
