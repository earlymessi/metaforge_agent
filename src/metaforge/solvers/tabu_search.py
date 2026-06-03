import random
import time
from collections import deque
from metaforge.core.base_solver import BaseSolver
from metaforge.utils.multiobjective_eval import evaluate_sequence_multiobjective


class TabuSearchSolver(BaseSolver):
    def __init__(self, problem, max_iterations=200, tabu_size=20, neighbors_sample=30):
        super().__init__(problem)
        self.max_iterations = max_iterations
        self.tabu_size = tabu_size
        self.neighbors_sample = neighbors_sample
        self.job_counts = [len(job.tasks) for job in problem.jobs]

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
            if job_ptr[job_idx] >= self.job_counts[job_idx]:
                continue
            task = self.problem.jobs[job_idx].tasks[job_ptr[job_idx]]
            start = max(machine_ready[task.machine_id], job_ready[job_idx])
            end = start + task.duration
            job_ready[job_idx] = end
            machine_ready[task.machine_id] = end
            job_ptr[job_idx] += 1

        makespan = max(machine_ready) if machine_ready else 0
        penalty = 0
        for j in range(self.problem.num_jobs):
            penalty += job_ready[j] * self.problem.jobs[j].priority * 5.0

        return makespan + penalty, makespan

    def _generate_priority_initial_solution(self):
        seq = []
        job_ptrs = [0] * len(self.job_counts)
        total_ops = sum(self.job_counts)
        for _ in range(total_ops):
            available = [j for j in range(len(self.job_counts)) if job_ptrs[j] < self.job_counts[j]]
            weights = [self.problem.jobs[j].priority for j in available]
            selected = random.choices(available, weights=weights, k=1)[0]
            seq.append(selected)
            job_ptrs[selected] += 1
        return seq

    def run(self, track_history=True, weights=None, resource_config=None, **kwargs):
        start_time = time.time()

        # 初始解
        curr_solution = self._generate_priority_initial_solution()
        curr_weighted, curr_makespan = self._evaluate_weighted(
            curr_solution, weights=weights, resource_config=resource_config
        )

        best_solution = curr_solution[:]
        best_weighted = curr_weighted
        best_makespan = curr_makespan

        # 禁忌表存储 (swap_i, swap_j)
        tabu_list = deque(maxlen=self.tabu_size)
        history = []

        for _ in range(self.max_iterations):
            # 生成邻域
            best_neighbor = None
            best_neighbor_weighted = float('inf')
            best_move = None

            # 随机采样 N 个邻居
            for _ in range(self.neighbors_sample):
                i, j = random.sample(range(len(curr_solution)), 2)

                # 构造邻居
                neighbor = curr_solution[:]
                neighbor[i], neighbor[j] = neighbor[j], neighbor[i]

                weighted, mkspan = self._evaluate_weighted(
                    neighbor, weights=weights, resource_config=resource_config
                )

                # 禁忌判断 (Aspiration Criteria: 如果比全局最好还好，就无视禁忌)
                move = tuple(sorted((i, j)))
                is_tabu = move in tabu_list

                if (not is_tabu) or (weighted < best_weighted):
                    if weighted < best_neighbor_weighted:
                        best_neighbor = neighbor
                        best_neighbor_weighted = weighted
                        best_neighbor_makespan = mkspan
                        best_move = move

            if best_neighbor is not None:
                curr_solution = best_neighbor
                tabu_list.append(best_move)

                if best_neighbor_weighted < best_weighted:
                    best_solution = best_neighbor[:]
                    best_weighted = best_neighbor_weighted
                    best_makespan = best_neighbor_makespan

            if track_history: history.append(best_makespan)

        runtime = time.time() - start_time
        return {
            "algorithm": "Tabu Search (Priority)",
            "best_score": int(best_makespan),
            "best_solution": best_solution,
            "runtime_sec": round(runtime, 4),
            "history": history,
            "gantt_data": self.problem.get_schedule(best_solution)
        }