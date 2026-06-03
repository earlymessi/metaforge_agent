"""
求解器注册表：算法元数据 + 工厂方法。

供 metaforge_runner、compare_solvers、/api/solvers/catalog 及后续 Agent/NL 匹配使用。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from metaforge.solvers.ant_colony import AntColonySolver
from metaforge.solvers.dqn_solver import DQNAgentSolver, DQNAgentSolverReplay
from metaforge.solvers.genetic_algorithm import GeneticAlgorithmSolver
from metaforge.solvers.heuristic_rules import EDDSolver, LPTSolver, MOPNRSolver, MWKRSolver, SPTSolver
from metaforge.solvers.neuroevolution_solver import NeuroevolutionSolver
from metaforge.solvers.ppo_solver import PPOSolver
from metaforge.solvers.q_learning import QAgentSolver
from metaforge.solvers.simulated_annealing import SimulatedAnnealingSolver
from metaforge.solvers.tabu_search import TabuSearchSolver


@dataclass
class SolverSpec:
    id: str
    cls: Type
    name_en: str
    name_zh: str
    family: str  # rule | metaheuristic | rl
    description_zh: str
    logic_summary_zh: str
    optimization_mode: str
    # multiobjective_search: 搜索阶段使用 weights
    # rule_construct: 固定规则构造序列，weights 仅用于事后综合评分
    # makespan_search: 搜索阶段以 makespan/原 reward 为主
    supports_weights_in_search: bool
    supports_resource_config: bool
    default_params: Dict[str, Any] = field(default_factory=dict)
    nl_keywords: List[str] = field(default_factory=list)
    speed: str = "medium"  # fast | medium | slow
    quality_tier: str = "good"  # fast_heuristic | good | best_effort | experimental
    recommended_for: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)

    def to_catalog_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name_en": self.name_en,
            "name_zh": self.name_zh,
            "family": self.family,
            "description_zh": self.description_zh,
            "logic_summary_zh": self.logic_summary_zh,
            "optimization_mode": self.optimization_mode,
            "supports_weights_in_search": self.supports_weights_in_search,
            "supports_resource_config": self.supports_resource_config,
            "default_params": self.default_params,
            "nl_keywords": self.nl_keywords,
            "speed": self.speed,
            "quality_tier": self.quality_tier,
            "recommended_for": self.recommended_for,
            "aliases": self.aliases,
        }


def _spec(
    id: str,
    cls: Type,
    name_en: str,
    name_zh: str,
    family: str,
    description_zh: str,
    logic_summary_zh: str,
    optimization_mode: str,
    supports_weights_in_search: bool,
    supports_resource_config: bool = True,
    default_params: Optional[Dict[str, Any]] = None,
    nl_keywords: Optional[List[str]] = None,
    speed: str = "medium",
    quality_tier: str = "good",
    recommended_for: Optional[List[str]] = None,
    aliases: Optional[List[str]] = None,
) -> SolverSpec:
    return SolverSpec(
        id=id,
        cls=cls,
        name_en=name_en,
        name_zh=name_zh,
        family=family,
        description_zh=description_zh,
        logic_summary_zh=logic_summary_zh,
        optimization_mode=optimization_mode,
        supports_weights_in_search=supports_weights_in_search,
        supports_resource_config=supports_resource_config,
        default_params=default_params or {},
        nl_keywords=nl_keywords or [],
        speed=speed,
        quality_tier=quality_tier,
        recommended_for=recommended_for or [],
        aliases=aliases or [],
    )


SOLVER_REGISTRY: Dict[str, SolverSpec] = {}
_ALIAS_MAP: Dict[str, str] = {}


def _register(spec: SolverSpec) -> None:
    SOLVER_REGISTRY[spec.id] = spec
    for alias in spec.aliases:
        _ALIAS_MAP[alias.lower()] = spec.id
    _ALIAS_MAP[spec.id.lower()] = spec.id
    if spec.name_zh:
        _ALIAS_MAP[spec.name_zh.strip().lower()] = spec.id
    if spec.name_en:
        _ALIAS_MAP[spec.name_en.strip().lower()] = spec.id
    for kw in spec.nl_keywords:
        key = (kw or "").strip().lower()
        if key:
            _ALIAS_MAP[key] = spec.id


# --- 规则启发式 ---
_register(_spec(
    "spt", SPTSolver, "SPT", "最短加工时间优先",
    "rule",
    "每步在可排工序中选加工时间最短的工单（同优先级下）。",
    "逐步构造工序序列：可用工单中按优先级→当前工序时长升序选取，单次扫描 O(n)。",
    "rule_construct", False,
    nl_keywords=["最短加工", "SPT", "短工序优先", "快速规则", "时间最短", "启发式"],
    speed="fast", quality_tier="fast_heuristic",
    recommended_for=["实时排程", "初版方案", "大规模算例快速估算"],
))
_register(_spec(
    "lpt", LPTSolver, "LPT", "最长加工时间优先",
    "rule",
    "每步优先选当前工序加工时间最长的工单。",
    "逐步构造序列：优先级相同时选最长工序，常用于负载平衡启发。",
    "rule_construct", False,
    nl_keywords=["最长加工", "LPT", "长工序优先"],
    speed="fast", quality_tier="fast_heuristic",
    recommended_for=["平衡长工序", "快速基准"],
))
_register(_spec(
    "mwkr", MWKRSolver, "MWKR", "剩余工作量最大优先",
    "rule",
    "每步选剩余总加工时间最大的工单。",
    "构造序列时比较各工单尚未完成工序的总时长，优先处理剩余量大的工单。",
    "rule_construct", False,
    nl_keywords=["剩余工作量", "MWKR", "最多剩余加工", "瓶颈工单"],
    speed="fast", quality_tier="fast_heuristic",
    recommended_for=["减少拖尾", "经典调度规则"],
))
_register(_spec(
    "mopnr", MOPNRSolver, "MOPNR", "剩余工序数最多优先",
    "rule",
    "每步选尚未完成工序数量最多的工单。",
    "按剩余工序个数排序构造序列，简单有效的优先规则。",
    "rule_construct", False,
    nl_keywords=["剩余工序", "MOPNR", "工序最多"],
    speed="fast", quality_tier="fast_heuristic",
))
_register(_spec(
    "edd", EDDSolver, "EDD", "最早交期优先",
    "rule",
    "每步选交期最早的工单（同优先级下）。",
    "构造序列时按 due_date 升序选取，适合交期敏感场景的快速规则。",
    "rule_construct", False,
    nl_keywords=["最早交期", "EDD", "交期优先", "按期交付", "交付优先"],
    speed="fast", quality_tier="fast_heuristic",
    recommended_for=["交期紧", "订单交付", "due date"],
))

# --- 元启发式 ---
_register(_spec(
    "ts", TabuSearchSolver, "Tabu Search", "禁忌搜索",
    "metaheuristic",
    "通过邻域交换探索解空间，禁忌表避免循环，可纳入多目标权重。",
    "初始优先级解→迭代 swap 邻域→禁忌表过滤→接受更优综合分；history 记录 makespan 收敛。",
    "multiobjective_search", True,
    default_params={"max_iterations": 200, "tabu_size": 20, "neighbors_sample": 30},
    nl_keywords=["禁忌搜索", "Tabu", "局部搜索", "精细优化", "改进了"],
    speed="medium", quality_tier="good",
    recommended_for=["中等规模", "要质量又要速度", "插单后重排"],
))
_register(_spec(
    "ga", GeneticAlgorithmSolver, "Genetic Algorithm", "遗传算法",
    "metaheuristic",
    "种群进化：选择、交叉、变异，适应度可为多目标综合分。",
    "初始化种群（50%优先级导向）→每代锦标赛选择→OX交叉→swap变异→跟踪最优序列。",
    "multiobjective_search", True,
    default_params={"population_size": 40, "generations": 100, "crossover_rate": 0.8, "mutation_rate": 0.2},
    nl_keywords=["遗传算法", "GA", "全局搜索", "进化", "多目标"],
    speed="slow", quality_tier="best_effort",
    recommended_for=["质量优先", "离线优化", "复杂工单池"],
))
_register(_spec(
    "sa", SimulatedAnnealingSolver, "Simulated Annealing", "模拟退火",
    "metaheuristic",
    "以一定概率接受劣解跳出局部最优，温度逐渐降低。",
    "初始解→随机 swap 邻域→Metropolis 准则接受→降温；可加权多目标评价。",
    "multiobjective_search", True,
    default_params={"initial_temp": 2000, "cooling_rate": 0.98, "max_iterations": 1000},
    nl_keywords=["模拟退火", "SA", "退火", "跳出局部最优"],
    speed="medium", quality_tier="good",
))
_register(_spec(
    "aco", AntColonySolver, "Ant Colony Optimization", "蚁群算法",
    "metaheuristic",
    "蚂蚁按信息素与启发式概率构造解，迭代更新信息素。",
    "多蚂蚁构造工序序列→信息素挥发与增强→跟踪最优；提供 weights 时用多目标评价。",
    "multiobjective_search", True,
    default_params={"num_ants": 15, "iterations": 50, "alpha": 1.0, "beta": 2.0, "evaporation": 0.5},
    nl_keywords=["蚁群", "ACO", "信息素", "群体智能"],
    speed="medium", quality_tier="good",
))

# --- 强化学习 / 实验性 ---
_register(_spec(
    "q", QAgentSolver, "Q-Learning", "Q 学习",
    "rl",
    "表格型 Q-learning 学习工序选择策略，主要优化 makespan。",
    "状态编码→ε-greedy 选动作→Q 表更新；适合小规模算例实验。",
    "makespan_search", False,
    nl_keywords=["Q学习", "强化学习", "Q-Learning"],
    speed="slow", quality_tier="experimental",
    recommended_for=["研究对比", "小算例"],
))
_register(_spec(
    "dqn-naive", DQNAgentSolver, "DQN (Naive)", "DQN 朴素版",
    "rl",
    "深度 Q 网络，无经验回放，主要优化 makespan。",
    "神经网络近似 Q 值→贪心/随机探索→在线更新。",
    "makespan_search", False,
    nl_keywords=["DQN", "深度强化学习", "神经网络"],
    speed="slow", quality_tier="experimental",
))
_register(_spec(
    "dqn-replay", DQNAgentSolverReplay, "DQN (Replay)", "DQN 经验回放",
    "rl",
    "带经验回放的 DQN，训练更稳定，主要优化 makespan。",
    "经验池采样→目标网络→批量梯度更新。",
    "makespan_search", False,
    nl_keywords=["DQN回放", "经验回放", "深度Q网络"],
    speed="slow", quality_tier="experimental",
))
_register(_spec(
    "neuroevo", NeuroevolutionSolver, "Neuroevolution", "神经进化",
    "rl",
    "进化神经网络权重以构造调度策略，带优先级惩罚的适应度。",
    "种群神经网络→评估序列 fitness→选择变异→多代进化。",
    "makespan_search", False,
    nl_keywords=["神经进化", "Neuroevolution", "进化神经网络"],
    speed="slow", quality_tier="experimental",
))
_register(_spec(
    "ppo", PPOSolver, "PPO", "近端策略优化",
    "rl",
    "PPO 策略梯度强化学习，内部可结合 MWKR 基准。",
    "Actor-Critic→PPO clip 更新→rollout 收集；实验性质，耗时较长。",
    "makespan_search", False,
    nl_keywords=["PPO", "策略梯度", "强化学习"],
    speed="slow", quality_tier="experimental",
    aliases=["PPO"],
))


def resolve_solver_id(name: str) -> str:
    key = (name or "").strip().lower()
    if key in _ALIAS_MAP:
        return _ALIAS_MAP[key]
    if key in SOLVER_REGISTRY:
        return key
    raise ValueError(f"Unknown solver algorithm: {name}")


def try_resolve_solver_id(name: str, *, default: Optional[str] = None) -> Optional[str]:
    """解析求解器 id；失败时返回 default（用于 MES 执行态/历史快照中的展示名）。"""
    try:
        return resolve_solver_id(name)
    except ValueError:
        return default


def get_solver_spec(solver_id: str) -> SolverSpec:
    sid = resolve_solver_id(solver_id)
    return SOLVER_REGISTRY[sid]


def list_solver_ids() -> List[str]:
    return list(SOLVER_REGISTRY.keys())


def get_solver_catalog(*, family: Optional[str] = None) -> Dict[str, Any]:
    specs = list(SOLVER_REGISTRY.values())
    if family:
        specs = [s for s in specs if s.family == family]
    families = {
        "rule": "规则启发式（快速构造序列）",
        "metaheuristic": "元启发式（迭代搜索改进）",
        "rl": "强化学习 / 实验算法",
    }
    return {
        "solvers": [s.to_catalog_dict() for s in specs],
        "families": families,
        "total": len(specs),
    }


def instantiate_solver(solver_id: str, problem: Any, solver_params: Optional[Dict[str, Any]] = None) -> Any:
    spec = get_solver_spec(solver_id)
    params = {**spec.default_params, **(solver_params or {})}
    init_sig = inspect.signature(spec.cls.__init__)
    init_names = set(init_sig.parameters.keys()) - {"self", "problem"}
    init_kwargs = {k: v for k, v in params.items() if k in init_names}
    return spec.cls(problem, **init_kwargs)


def build_run_kwargs(solver_id: str, *, solver_params: Optional[Dict[str, Any]] = None, **runtime_kwargs) -> Dict[str, Any]:
    """合并 run() 可接受参数（weights、resource_config 等）。"""
    spec = get_solver_spec(solver_id)
    params = {**spec.default_params, **(solver_params or {})}
    # 实例化参数不应传入 run
    init_sig = inspect.signature(spec.cls.__init__)
    init_names = set(init_sig.parameters.keys()) - {"self", "problem"}
    run_sig = inspect.signature(spec.cls.run)
    run_names = set(run_sig.parameters.keys()) - {"self"}

    merged = {**runtime_kwargs}
    for k, v in params.items():
        if k not in init_names and k in run_names:
            merged[k] = v

    for k, v in runtime_kwargs.items():
        if k in run_names:
            merged[k] = v

    if "track_history" in run_names and "track_history" not in merged:
        merged["track_history"] = True

    return merged
