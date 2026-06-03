import time
import numpy as np
from metaforge.core.base_solver import BaseSolver
from metaforge.utils.multiobjective_eval import evaluate_sequence_multiobjective


class BaseHeuristic(BaseSolver):
    """
    启发式规则的基类。
    """

    def __init__(self, problem):
        super().__init__(problem)
        self.job_counts = [len(job.tasks) for job in problem.jobs]
        self.num_jobs = len(problem.jobs)
        self.total_ops = sum(self.job_counts)

    def select_next_job(self, available_jobs, current_task_indices):
        """
        子类必须实现此方法
        """
        raise NotImplementedError

    def run(self, track_history=True, weights=None, resource_config=None, **kwargs):
        start_time = time.time()

        # 初始化状态
        job_next_op_idx = [0] * self.num_jobs
        sequence = []

        # 逐步构建序列
        for _ in range(self.total_ops):
            available_jobs = [j for j in range(self.num_jobs) if job_next_op_idx[j] < self.job_counts[j]]
            if not available_jobs:
                break
            selected_job = self.select_next_job(available_jobs, job_next_op_idx)
            sequence.append(selected_job)
            job_next_op_idx[selected_job] += 1

        if weights:
            best_score, _mkspan, _metrics = evaluate_sequence_multiobjective(
                self.problem,
                sequence,
                weights=weights,
                resource_config=resource_config,
            )
            best_score = float(best_score)
        else:
            best_score = int(self.problem.evaluate(sequence))
        end_time = time.time()
        runtime = end_time - start_time

        # === 修改点：不再伪造重复数据，直接返回空列表 ===
        # 前端会识别：如果 history 为空但有 best_score，就画基准线
        history = []

        # 获取甘特图数据
        gantt_data = self.problem.get_schedule(sequence)

        return {
            "algorithm": self.__class__.__name__,
            "best_score": best_score,
            "best_solution": sequence,
            "runtime_sec": round(runtime, 6),
            "history": history,
            "gantt_data": gantt_data
        }


# === 具体算法实现 (已增加优先级支持) ===

class SPTSolver(BaseHeuristic):
    """
    最短加工时间优先 (Shortest Processing Time)
    改进：优先处理高优先级，同优先级下选时间短的。
    """

    def select_next_job(self, available_jobs, current_task_indices):
        candidates = []
        for job_idx in available_jobs:
            op_idx = current_task_indices[job_idx]
            job_obj = self.problem.jobs[job_idx]
            duration = job_obj.tasks[op_idx].duration
            # 保存 (Job索引, 优先级, 时长)
            candidates.append((job_idx, job_obj.priority, duration))

        # 排序逻辑：
        # 1. -x[1]: 优先级取反 (100 -> -100, 10 -> -10)，越小越靠前
        # 2. x[2]: 时长，越小越靠前
        candidates.sort(key=lambda x: (-x[1], x[2]))

        return candidates[0][0]


class LPTSolver(BaseHeuristic):
    """
    最长加工时间优先 (Longest Processing Time)
    改进：优先处理高优先级，同优先级下选时间长的。
    """

    def select_next_job(self, available_jobs, current_task_indices):
        candidates = []
        for job_idx in available_jobs:
            op_idx = current_task_indices[job_idx]
            job_obj = self.problem.jobs[job_idx]
            duration = job_obj.tasks[op_idx].duration
            candidates.append((job_idx, job_obj.priority, duration))

        # 排序逻辑 (reverse=True)：
        # 1. x[1]: 优先级 (100 > 10)，越大越靠前
        # 2. x[2]: 时长，越大越靠前
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)

        return candidates[0][0]


class MWKRSolver(BaseHeuristic):
    """
    剩余总工作量最大优先 (Most Work Remaining)
    改进：优先处理高优先级，同优先级下选剩余量大的。
    """

    def select_next_job(self, available_jobs, current_task_indices):
        candidates = []
        for job_idx in available_jobs:
            op_idx = current_task_indices[job_idx]
            job_obj = self.problem.jobs[job_idx]

            remaining_tasks = job_obj.tasks[op_idx:]
            total_remaining_time = sum(t.duration for t in remaining_tasks)
            candidates.append((job_idx, job_obj.priority, total_remaining_time))

        # 排序逻辑 (reverse=True)：
        # 1. x[1]: 优先级，越大越前
        # 2. x[2]: 剩余时间，越大越前
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)

        return candidates[0][0]


class MOPNRSolver(BaseHeuristic):
    """
    剩余工序数最多优先 (Most Operations Remaining)
    改进：优先处理高优先级，同优先级下选工序多的。
    """

    def select_next_job(self, available_jobs, current_task_indices):
        candidates = []
        for job_idx in available_jobs:
            op_idx = current_task_indices[job_idx]
            job_obj = self.problem.jobs[job_idx]

            remaining_ops = len(job_obj.tasks) - op_idx
            candidates.append((job_idx, job_obj.priority, remaining_ops))

        # 排序逻辑 (reverse=True)：
        # 1. x[1]: 优先级，越大越前
        # 2. x[2]: 剩余工序数，越大越前
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)

        return candidates[0][0]


class EDDSolver(BaseHeuristic):
    """
    最早交货期优先 (Earliest Due Date)
    改进：优先处理高优先级，同优先级下选交期近的。
    """

    def select_next_job(self, available_jobs, current_task_indices):
        candidates = []
        for job_idx in available_jobs:
            job_obj = self.problem.jobs[job_idx]
            due_date = getattr(job_obj, 'due_date', float('inf'))
            candidates.append((job_idx, job_obj.priority, due_date))

        # 排序逻辑：
        # 1. -x[1]: 优先级取反，越急越靠前
        # 2. x[2]: 交期，越早(小)越靠前
        candidates.sort(key=lambda x: (-x[1], x[2]))

        return candidates[0][0]