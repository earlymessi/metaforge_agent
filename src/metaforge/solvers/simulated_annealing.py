import math
import random
import time
import copy
from metaforge.core.base_solver import BaseSolver
from metaforge.utils.multiobjective_eval import evaluate_sequence_multiobjective


class SimulatedAnnealingSolver(BaseSolver):
    def __init__(self, problem, initial_temp=2000, cooling_rate=0.98, max_iterations=1000):
        super().__init__(problem)
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        self.max_iterations = max_iterations
        self.job_counts = [len(job.tasks) for job in problem.jobs]

    # === 关键：加权评估函数 ===
    def _evaluate_weighted(self, sequence, *, weights=None, resource_config=None):
        # 多目标（若提供 weights）优先；否则保持旧的“优先级惩罚”口径以兼容历史效果
        if weights:
            score, mkspan, _metrics = evaluate_sequence_multiobjective(
                self.problem,
                sequence,
                weights=weights,
                resource_config=resource_config,
            )
            return score, mkspan

        job_ptr = [0] * self.problem.num_jobs
        job_ready = [0] * self.problem.num_jobs
        machine_ready = [0] * self.problem.num_machines

        for job_idx in sequence:
            if job_ptr[job_idx] >= self.job_counts[job_idx]: continue

            task = self.problem.jobs[job_idx].tasks[job_ptr[job_idx]]
            start = max(machine_ready[task.machine_id], job_ready[job_idx])
            end = start + task.duration

            job_ready[job_idx] = end
            machine_ready[task.machine_id] = end
            job_ptr[job_idx] += 1

        makespan = max(machine_ready)

        # === 惩罚项计算 ===
        # 惩罚 = Sum(完工时间 * 优先级 * 系数)
        penalty = 0
        for j in range(self.problem.num_jobs):
            # 优先级越高(>10)，越晚完工，惩罚越重
            # 系数 5.0 可以调节：越大越重视优先级，越小越重视完工时间
            penalty += job_ready[j] * self.problem.jobs[j].priority * 5.0

        return makespan + penalty, makespan  # 返回 (综合分, 真实时间)

    def _generate_priority_initial_solution(self):
        # 生成一个符合优先级的初始解
        seq = []
        job_ptrs = [0] * len(self.job_counts)
        total_ops = sum(self.job_counts)

        for _ in range(total_ops):
            available = [j for j in range(len(self.job_counts)) if job_ptrs[j] < self.job_counts[j]]
            # 概率选择：优先级高的被选中的概率极大
            weights = [self.problem.jobs[j].priority for j in available]
            selected = random.choices(available, weights=weights, k=1)[0]

            seq.append(selected)
            job_ptrs[selected] += 1
        return seq

    def get_neighbor(self, solution):
        # 邻域动作：交换
        neighbor = solution[:]
        i, j = random.sample(range(len(neighbor)), 2)
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        return neighbor

    def run(self, track_history=True, weights=None, resource_config=None, **kwargs):
        start_time = time.time()

        # 1. 好的起点
        current_solution = self._generate_priority_initial_solution()
        current_weighted, current_makespan = self._evaluate_weighted(
            current_solution, weights=weights, resource_config=resource_config
        )

        best_solution = current_solution[:]
        best_weighted = current_weighted
        best_makespan = current_makespan

        temp = self.initial_temp
        history = []

        for _ in range(self.max_iterations):
            neighbor = self.get_neighbor(current_solution)
            neighbor_weighted, neighbor_makespan = self._evaluate_weighted(
                neighbor, weights=weights, resource_config=resource_config
            )

            # 使用加权分计算 Delta
            delta = neighbor_weighted - current_weighted

            # Metropolis 准则
            if delta < 0 or random.random() < math.exp(-delta / max(temp, 1e-5)):
                current_solution = neighbor
                current_weighted = neighbor_weighted

                # 更新全局最优 (看加权分)
                if current_weighted < best_weighted:
                    best_weighted = current_weighted
                    best_solution = current_solution[:]
                    best_makespan = neighbor_makespan  # 记录此时的真实时间

            if track_history: history.append(best_makespan)
            temp *= self.cooling_rate

        runtime = time.time() - start_time
        return {
            "algorithm": "Simulated Annealing (Priority)",
            "best_score": int(best_makespan),
            "best_solution": best_solution,
            "runtime_sec": round(runtime, 4),
            "history": history,
            "gantt_data": self.problem.get_schedule(best_solution)
        }