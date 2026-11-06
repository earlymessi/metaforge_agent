"""FAB research methods = FAB preprocess + reused MetaForge solvers.

Not registered into the generic APS solver catalog.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# (area, preprocess, solver_id, title_suffix, when_to_use, recommended, family)
# family: rule | metaheuristic | rl | construct
_METHOD_SPECS = [
    # --- photolithography: dedication bind then reuse solvers ---
    ("photolithography", "dedication_bind", "spt", "SPT", "规则基线；默认快速对照。", True, "rule"),
    ("photolithography", "dedication_bind", "edd", "EDD", "交期敏感时与 SPT 对照。", False, "rule"),
    ("photolithography", "dedication_bind", "mwkr", "MWKR", "剩余工作量大优先，经典派工规则。", False, "rule"),
    ("photolithography", "dedication_bind", "ts", "禁忌搜索 TS", "JD/论文常见元启发式；粘机后局部搜索改进。", True, "metaheuristic"),
    ("photolithography", "dedication_bind", "ga", "遗传算法 GA", "离线质量优先；种群搜索序列。", False, "metaheuristic"),
    ("photolithography", "dedication_bind", "sa", "模拟退火 SA", "与 TS/GA 对照的邻域搜索。", False, "metaheuristic"),
    ("photolithography", "dedication_bind", "aco", "蚁群 ACO", "信息素构造序列（仓库已有实现）。", False, "metaheuristic"),
    ("photolithography", "dedication_bind", "q", "Q-Learning", "小规模 RL 实验；一期可跑、结果供对照。", False, "rl"),
    ("photolithography", "dedication_bind", "dqn-replay", "DQN(Replay)", "深度 RL 基线（慢）；面试展示学习路线。", False, "rl"),
    # --- etch timelink ---
    ("etch_timelink", "timelink_slack", "spt", "松弛优先+SPT", "默认：先抬升紧迫 lot 优先级再 SPT。", True, "rule"),
    ("etch_timelink", "timelink_edd", "edd", "窗感知+EDD", "交期与时间窗合成优先级。", False, "rule"),
    ("etch_timelink", "timelink_slack", "ts", "松弛优先+TS", "保窗预处理 + 禁忌搜索改进。", True, "metaheuristic"),
    ("etch_timelink", "timelink_slack", "ga", "松弛优先+GA", "保窗预处理 + 遗传搜索。", False, "metaheuristic"),
    ("etch_timelink", "timelink_slack", "sa", "松弛优先+SA", "保窗预处理 + 模拟退火。", False, "metaheuristic"),
    ("etch_timelink", "timelink_slack", "dqn-replay", "松弛优先+DQN", "RL 实验路径（慢）。", False, "rl"),
    # --- diffusion batch: construct only (encoding differs from JSSP) ---
    ("diffusion_furnace", "batch_construct", None, "同族组批构造", "批处理必须改编码；不直接套 JSSP-GA。", True, "construct"),
]


def _card_from_spec(spec: tuple) -> Dict[str, Any]:
    area, preprocess, solver_id, title_suffix, when, recommended, family = spec
    if preprocess == "batch_construct":
        mid = "batch_construct"
        title = f"扩散炉 · {title_suffix}"
        summary = "按 family 组批（容量内）并同步起止；复用评价器 batch_*，不改 JobShopProblem.evaluate。"
        reuses = "metaforge.fab.research.batch_construct"
    else:
        mid = f"{preprocess}_{solver_id.replace('-', '_')}"
        # keep readable ids: dedication_bind_ts, timelink_slack_dqn_replay
        mid = f"{preprocess}_{str(solver_id).replace('-', '_')}"
        prefix = {
            "dedication_bind": "粘机绑定",
            "timelink_slack": "时间窗松弛",
            "timelink_edd": "时间窗EDD",
        }.get(preprocess, preprocess)
        title = f"{prefix} + {title_suffix}"
        summary = (
            f"FAB 预处理 `{preprocess}` 后，复用仓库求解器 `{solver_id}` "
            f"（与 APS 同一套 metaforge.solvers / registry）。"
        )
        reuses = f"solver_registry:{solver_id}"

    return {
        "id": mid,
        "area": area,
        "family": family,
        "preprocess": preprocess,
        "solver_id": solver_id,
        "title": title,
        "summary": summary,
        "when_to_use": when,
        "recommended": recommended,
        "reuses": reuses,
        "params_schema": {},
    }


METHOD_CARDS: List[Dict[str, Any]] = [_card_from_spec(s) for s in _METHOD_SPECS]

# stable lookup for legacy ids used in early tests
_LEGACY_ALIASES = {
    "dedication_bind_spt": "dedication_bind_spt",
    "dedication_bind_edd": "dedication_bind_edd",
    "timelink_slack_spt": "timelink_slack_spt",
    "timelink_edd": "timelink_edd_edd",  # maps to generated id
}


def list_methods(area: Optional[str] = None) -> List[Dict[str, Any]]:
    cards = list(METHOD_CARDS)
    if area:
        cards = [m for m in cards if m["area"] == area]
    # recommended first within family order
    family_order = {"rule": 0, "construct": 0, "metaheuristic": 1, "rl": 2}
    cards.sort(key=lambda m: (family_order.get(m["family"], 9), 0 if m.get("recommended") else 1, m["id"]))
    return cards


def get_method(method_id: str) -> Optional[Dict[str, Any]]:
    sid = str(method_id or "").strip()
    # legacy timelink_edd → timelink_edd_edd
    if sid == "timelink_edd":
        sid = "timelink_edd_edd"
    for m in METHOD_CARDS:
        if m["id"] == sid:
            return m
    # also accept dedication_bind-ts style
    alt = sid.replace("-", "_")
    for m in METHOD_CARDS:
        if m["id"] == alt:
            return m
    return None
