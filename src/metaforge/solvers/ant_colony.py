import random
import time
import numpy as np
from metaforge.core.base_solver import BaseSolver
from metaforge.utils.multiobjective_eval import evaluate_sequence_multiobjective


class AntColonySolver(BaseSolver):
    def __init__(self, problem, num_ants=15, iterations=50, alpha=1.0, beta=2.0, evaporation=0.5, Q=100):
        super().__init__(problem)
        self.num_ants = num_ants
        self.iterations = iterations
        self.alpha = alpha
        self.beta = beta
        self.evaporation = evaporation
        self.Q = Q
        self.job_counts = [len(job.tasks) for job in problem.jobs]
        self.total_ops = sum(self.job_counts)

        # 信息素矩阵 (节点i到节点j)
        # 简化版：这里 pheromone[i][j] 代表上一个选了 Job i, 下一个选 Job j 的倾向
        self.pheromone = np.ones((len(problem.jobs), len(problem.jobs)))

    def _evaluate_weighted(self, sequence):
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
        penalty = sum(job_ready[j] * self.problem.jobs[j].priority * 5.0 for j in range(self.problem.num_jobs))
        return makespan + penalty, makespan

    def construct_solution(self):
        sequence = []
        job_ptr = [0] * len(self.job_counts)
        last_job = -1  # Start node

        for _ in range(self.total_ops):
            available = [j for j in range(len(self.job_counts)) if job_ptr[j] < self.job_counts[j]]

            probs = []
            for job_idx in available:
                # 1. Pheromone
                tau = self.pheromone[last_job][job_idx] if last_job != -1 else 1.0

                # 2. Heuristic (Eta) - 关键修改
                # 传统 ACO: eta = 1 / duration
                # 优先级 ACO: eta = Priority * (1 / duration)
                # 优先级越高，eta 越大，被选概率越大
                task = self.problem.jobs[job_idx].tasks[job_ptr[job_idx]]
                prio = self.problem.jobs[job_idx].priority
                eta = (prio ** 2) * (1.0 / (task.duration + 1.0))

                probs.append((tau ** self.alpha) * (eta ** self.beta))

            total = sum(probs)
            if total == 0:
                probs = [1 / len(probs)] * len(probs)
            else:
                probs = [p / total for p in probs]

            # 轮盘赌选择
            selected = random.choices(available, weights=probs, k=1)[0]
            sequence.append(selected)
            job_ptr[selected] += 1
            last_job = selected

        return sequence

    def run(self, track_history=True, weights=None, resource_config=None, **kwargs):
        start_time = time.time()
        best_solution = None
        best_weighted = float('inf')
        best_makespan = float('inf')
        history = []
        use_multiobjective = bool(weights)

        for _ in range(self.iterations):
            ants_solutions = []

            # 1. 蚂蚁构造解
            for _ in range(self.num_ants):
                sol = self.construct_solution()
                if use_multiobjective:
                    w_score, mkspan, _ = evaluate_sequence_multiobjective(
                        self.problem,
                        sol,
                        weights=weights,
                        resource_config=resource_config,
                    )
                    w_score = float(w_score)
                    mkspan = float(mkspan)
                else:
                    w_score, mkspan = self._evaluate_weighted(sol)
                ants_solutions.append((sol, w_score, mkspan))

                if w_score < best_weighted:
                    best_weighted = w_score
                    best_solution = sol[:]
                    best_makespan = mkspan

            if track_history: history.append(best_makespan)

            # 2. 信息素蒸发
            self.pheromone *= (1 - self.evaporation)

            # 3. 信息素更新 (精英蚂蚁)
            # 只有本轮表现好的蚂蚁才能留下信息素
            ants_solutions.sort(key=lambda x: x[1])  # 按加权分排序
            elite_ants = ants_solutions[:3]  # 取前3名

            for sol, w_score, _ in elite_ants:
                deposit = self.Q / w_score  # 分数越低(越好)，留下的越多
                last_j = -1
                for curr_j in sol:
                    if last_j != -1:
                        self.pheromone[last_j][curr_j] += deposit
                    last_j = curr_j

        runtime = time.time() - start_time
        return {
            "algorithm": "ACO (Priority)",
            "best_score": int(best_makespan),
            "best_solution": best_solution,
            "runtime_sec": round(runtime, 4),
            "history": history,
            "gantt_data": self.problem.get_schedule(best_solution)
        }