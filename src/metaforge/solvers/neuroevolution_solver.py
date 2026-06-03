import torch
import torch.nn as nn
import numpy as np
import random
import time
import copy
from copy import deepcopy
from metaforge.core.base_solver import BaseSolver


# ==========================================
# 通用辅助：局部搜索微调 (Turbo Mode)
# ==========================================
def apply_local_search(problem, initial_sequence, max_steps=200):
    """
    轻量级爬山法：在不大幅破坏优先级结构的前提下，尝试填补空隙。
    """
    if not initial_sequence or len(initial_sequence) < 2:
        return initial_sequence, problem.evaluate(initial_sequence)

    current_seq = initial_sequence[:]
    current_score = problem.evaluate(current_seq)

    for _ in range(max_steps):
        i, j = random.sample(range(len(current_seq)), 2)
        neighbor = current_seq[:]
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]

        neighbor_score = problem.evaluate(neighbor)

        # 只要时间更短，就接受（混合策略精髓）
        if neighbor_score < current_score:
            current_seq = neighbor
            current_score = neighbor_score

    return current_seq, current_score


# ==========================================
# 神经网络定义
# ==========================================
class EvoNetwork(nn.Module):
    def __init__(self, input_size, hidden_sizes, output_size):
        super().__init__()
        layers = []
        sizes = [input_size] + hidden_sizes
        for in_s, out_s in zip(sizes[:-1], sizes[1:]):
            layers.append(nn.Linear(in_s, out_s))
            layers.append(nn.ReLU())
        layers.append(nn.Linear(sizes[-1], output_size))
        self.model = nn.Sequential(*layers)

    def forward(self, x):
        return self.model(x)

    def get_flat_params(self):
        return torch.cat([p.data.view(-1) for p in self.parameters()])

    def set_flat_params(self, flat):
        pointer = 0
        for p in self.parameters():
            numel = p.numel()
            p.data.copy_(flat[pointer:pointer + numel].view_as(p))
            pointer += numel


# ==========================================
# 核心：评估函数 (含优先级加权)
# ==========================================
def evaluate_network_weighted(problem, net, device, priority_vector):
    job_counts = [len(job.tasks) for job in problem.jobs]
    num_jobs = len(job_counts)
    job_ptrs = [0] * num_jobs
    job_ready = [0] * num_jobs
    machine_ready = [0] * problem.num_machines
    sequence = []

    # 状态输入包含优先级信息
    norm_p = torch.tensor(priority_vector, dtype=torch.float32, device=device)

    while any(ptr < job_counts[j] for j, ptr in enumerate(job_ptrs)):
        available = [j for j in range(num_jobs) if job_ptrs[j] < job_counts[j]]

        # 状态向量：[Ptrs, ReadyTimes, Priorities]
        state_parts = [
            torch.tensor(job_ptrs, dtype=torch.float32, device=device),
            torch.tensor(job_ready, dtype=torch.float32, device=device),
            norm_p
        ]
        state = torch.cat(state_parts)

        with torch.no_grad():
            scores = net(state).cpu().numpy()

        # Masking
        masked = np.full(num_jobs, -np.inf)
        for j in available:
            masked[j] = scores[j]

        selected = int(np.argmax(masked))
        sequence.append(selected)

        # Update
        op_idx = job_ptrs[selected]
        task = problem.jobs[selected].tasks[op_idx]
        machine, proc_time = task.machine_id, task.duration
        start_time = max(machine_ready[machine], job_ready[selected])
        end_time = start_time + proc_time

        job_ptrs[selected] += 1
        job_ready[selected] = end_time
        machine_ready[machine] = end_time

    # === 进化目标函数 ===
    makespan = max(job_ready)

    # 优先级惩罚：Priority * FinishTime
    # 进化算法会为了降低这个分，拼命把高优任务往前赶
    weighted_penalty = 0
    for j in range(num_jobs):
        weighted_penalty += job_ready[j] * problem.jobs[j].priority

    # 综合 Fitness (Makespan + 优先级惩罚)
    fitness = makespan + (weighted_penalty * 0.1)

    return sequence, fitness, makespan


# ==========================================
# 算法 3: Neuroevolution Solver (Hybrid)
# ==========================================
class NeuroevolutionSolver(BaseSolver):
    def __init__(self, problem, pop_size=30, generations=50, mutation_rate=0.1, elite_size=2, hidden_sizes=[64, 32]):
        super().__init__(problem)
        self.pop_size = pop_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elite_size = elite_size
        self.hidden_sizes = hidden_sizes
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # 输入维度: Jobs * 3 (Ptr, Ready, Priority)
        self.input_size = len(problem.jobs) * 3
        self.output_size = len(problem.jobs)
        self.model_template = EvoNetwork(self.input_size, hidden_sizes, self.output_size).to(self.device)
        self.param_size = len(self.model_template.get_flat_params())

        # 缓存优先级向量
        raw_p = np.array([j.priority for j in problem.jobs])
        self.priority_vector = raw_p / (np.max(raw_p) + 1e-6)

    def initialize_population(self):
        return [torch.randn(self.param_size) * 0.5 for _ in range(self.pop_size)]

    def mutate(self, weights):
        noise = torch.randn_like(weights) * self.mutation_rate
        return weights + noise

    def crossover(self, parent1, parent2):
        mask = torch.rand_like(parent1) < 0.5
        child = torch.where(mask, parent1, parent2)
        return child

    def run(self, track_history=True, **kwargs):
        start_time = time.time()
        population = self.initialize_population()

        real_best_makespan = float("inf")
        real_best_solution = None
        history = []

        for gen in range(self.generations):
            scored = []
            for flat_params in population:
                net = deepcopy(self.model_template)
                net.set_flat_params(flat_params.to(self.device))

                # 评估：返回序列、综合Fitness(含优先级)、真实Makespan
                seq, fitness, mkspan = evaluate_network_weighted(self.problem, net, self.device, self.priority_vector)
                scored.append((flat_params, fitness, seq, mkspan))

            # 按 Fitness (优先级导向) 排序
            scored.sort(key=lambda x: x[1])

            # 记录当前最优 (为了历史曲线)
            current_best = scored[0]
            if current_best[3] < real_best_makespan:
                real_best_makespan = current_best[3]
                real_best_solution = current_best[2]

            if track_history:
                history.append(real_best_makespan)

            elites = scored[:self.elite_size]
            next_gen = [e[0] for e in elites]

            while len(next_gen) < self.pop_size:
                p1, p2 = random.sample(elites, 2)
                child = self.crossover(p1[0], p2[0])
                child = self.mutate(child)
                next_gen.append(child)

            population = next_gen

        # === 关键步骤：应用混合策略（局部搜索微调） ===
        if real_best_solution is not None:
            # print("Neuroevolution finished. Applying local search...")
            # 对神经网络找出的“符合优先级的解”进行挤压水分
            real_best_solution, real_best_makespan = apply_local_search(self.problem, real_best_solution, max_steps=300)

        runtime = time.time() - start_time
        return {
            "algorithm": "Neuroevolution (Hybrid)",
            "best_score": int(real_best_makespan),
            "best_solution": real_best_solution,
            "runtime_sec": round(runtime, 4),
            "history": history,
            "gantt_data": self.problem.get_schedule(real_best_solution)
        }