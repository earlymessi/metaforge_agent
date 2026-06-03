import random
import time
from metaforge.core.base_solver import BaseSolver
from metaforge.utils.multiobjective_eval import evaluate_sequence_multiobjective


class GeneticAlgorithmSolver(BaseSolver):
    def __init__(self, problem, population_size=40, generations=100, crossover_rate=0.8, mutation_rate=0.2):
        super().__init__(problem)
        self.population_size = population_size
        self.generations = generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
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

    def _generate_priority_solution(self):
        # 带随机性的优先级生成，保证种群多样性
        seq = []
        job_ptrs = [0] * len(self.job_counts)
        total_ops = sum(self.job_counts)
        for _ in range(total_ops):
            available = [j for j in range(len(self.job_counts)) if job_ptrs[j] < self.job_counts[j]]
            # 权重 = 优先级，带一点点随机性
            weights = [self.problem.jobs[j].priority ** 2 for j in available]  # 平方放大差距
            selected = random.choices(available, weights=weights, k=1)[0]
            seq.append(selected)
            job_ptrs[selected] += 1
        return seq

    def initialize_population(self):
        # 50% 纯随机，50% 优先级导向
        pop = []
        base = []
        for j_idx, cnt in enumerate(self.job_counts):
            base += [j_idx] * cnt

        for _ in range(self.population_size // 2):
            pop.append(self._generate_priority_solution())

        for _ in range(self.population_size - len(pop)):
            p = base[:]
            random.shuffle(p)
            pop.append(p)
        return pop

    def crossover(self, p1, p2):
        # 顺序交叉 OX
        size = len(p1)
        start, end = sorted(random.sample(range(size), 2))
        child = [None] * size
        child[start:end] = p1[start:end]
        p2_idx = 0
        for i in range(size):
            if child[i] is None:
                while p2[p2_idx] in child[start:end] and child.count(p2[p2_idx]) >= p1.count(p2[p2_idx]):
                    p2_idx += 1
                child[i] = p2[p2_idx]
                p2_idx += 1
        return child

    def mutate(self, individual):
        i, j = random.sample(range(len(individual)), 2)
        individual[i], individual[j] = individual[j], individual[i]
        return individual

    def run(self, track_history=True, weights=None, resource_config=None, **kwargs):
        start_time = time.time()
        population = self.initialize_population()

        best_solution = None
        best_weighted = float('inf')
        best_makespan = float('inf')
        history = []

        for gen in range(self.generations):
            # 评估
            evaluated = []
            for ind in population:
                w_score, mkspan = self._evaluate_weighted(
                    ind, weights=weights, resource_config=resource_config
                )
                evaluated.append((ind, w_score, mkspan))

                if w_score < best_weighted:
                    best_weighted = w_score
                    best_solution = ind[:]
                    best_makespan = mkspan

            if track_history: history.append(best_makespan)

            # 锦标赛选择 (基于加权分)
            selected = []
            for _ in range(self.population_size):
                a, b = random.sample(evaluated, 2)
                winner = a[0] if a[1] < b[1] else b[0]
                selected.append(winner)

            # 繁衍
            children = []
            for i in range(0, self.population_size, 2):
                p1, p2 = selected[i], selected[i + 1]
                if random.random() < self.crossover_rate:
                    c1 = self.crossover(p1, p2)
                    c2 = self.crossover(p2, p1)
                else:
                    c1, c2 = p1[:], p2[:]

                if random.random() < self.mutation_rate: c1 = self.mutate(c1)
                if random.random() < self.mutation_rate: c2 = self.mutate(c2)
                children.extend([c1, c2])

            population = children[:self.population_size]

        runtime = time.time() - start_time
        return {
            "algorithm": "GA (Priority)",
            "best_score": int(best_makespan),
            "best_solution": best_solution,
            "runtime_sec": round(runtime, 4),
            "history": history,
            "gantt_data": self.problem.get_schedule(best_solution)
        }