import numpy as np
import random


class Task:
    def __init__(self, machine_id, duration, id=None, name=None, machine_options=None, machine_group=None):
        """
        工序类
        :param machine_id: 机器ID
        :param duration: 持续时间
        :param id: 工序在工件中的索引ID
        :param name: 工序名称 (如: "车削", "钻孔")
        """
        self.machine_id = machine_id
        self.duration = duration
        self.id = id
        self.machine_group = machine_group
        self.machine_options = machine_options[:] if machine_options else (
            [machine_id] if machine_id is not None else []
        )
        # 如果没有提供名字，默认叫 "Op-{id}"
        self.name = name if name else f"Op-{id}" if id is not None else "Operation"

    def candidate_machines(self):
        """返回该工序可选机台列表（用于设备组/替代机台建模）。"""
        if self.machine_options:
            return list(dict.fromkeys(int(m) for m in self.machine_options if m is not None))
        if self.machine_id is None:
            return []
        return [int(self.machine_id)]

    def __repr__(self):
        return (
            f"Task(name={self.name}, machine={self.machine_id}, "
            f"options={self.machine_options}, duration={self.duration})"
        )


class Job:
    # [修改] 增加了 priority 参数，默认为 10
    def __init__(self, tasks, id=None, arrival_time=0, due_date=None, due_date_k_factor=2.5, priority=10):
        """
        工件类
        """
        self.tasks = tasks  # List[Task]
        self.id = id
        self.arrival_time = arrival_time
        self.priority = priority  # [新增] 存储优先级

        # 用户填写为显式交期；未填则在 problem_builder.refine_auto_due_dates 中按车间负载修正
        self.due_date_explicit = due_date is not None
        if due_date is not None:
            self.due_date = float(due_date)
        else:
            total_processing_time = sum(task.duration for task in self.tasks)
            self.due_date = self.arrival_time + total_processing_time * due_date_k_factor
            self.due_date_explicit = False

    def __len__(self):
        return len(self.tasks)

    def __repr__(self):
        return f"Job(id={self.id}, priority={self.priority}, tasks={self.tasks})"


class Machine:
    def __init__(self, id):
        self.id = id
        self.mode = 'normal'
        self.cost_rate_multiplier = {
            'normal': 1.0,
            'overtime': 1.5
        }
        self.calendar = []
        self.maintenance = []

    def get_current_cost_rate(self):
        return self.cost_rate_multiplier.get(self.mode, 1.0)

    def __repr__(self):
        return f"Machine(id={self.id})"


class JobShopProblem:
    """
    Job Shop 调度问题核心模型
    """

    def __init__(self, jobs, instance_name="Job Shop Instance", tardiness_penalty_per_unit=100,
                 overtime_cost_per_unit=10, initial_machine_ready=None):
        self.instance_name = instance_name
        self.jobs = jobs
        self.num_jobs = len(jobs)

        # 动态计算机器数量 (遍历所有工序找最大的机器ID)
        all_machine_ids = []
        for job in jobs:
            for task in job.tasks:
                all_machine_ids.extend(task.candidate_machines())
        self.num_machines = max(all_machine_ids) + 1 if all_machine_ids else 0
        self.machines = [Machine(i) for i in range(self.num_machines)]
        self.initial_machine_ready = [0.0] * self.num_machines
        if initial_machine_ready:
            for i in range(min(len(initial_machine_ready), self.num_machines)):
                self.initial_machine_ready[i] = float(initial_machine_ready[i])

        # 成本参数
        self.TARDINESS_PENALTY = tardiness_penalty_per_unit
        self.OVERTIME_COST = overtime_cost_per_unit

    @staticmethod
    def _select_machine_for_task(task, machine_ready_time, preferred_machine=None):
        """
        从候选机台中选择可最早开工的机台；若并列，优先 preferred_machine，再按机台 ID 升序。
        """
        candidates = task.candidate_machines()
        if not candidates:
            raise ValueError(f"Task has no available machine candidates: {task}")

        best_machine = candidates[0]
        best_ready = machine_ready_time[best_machine]
        for mid in candidates[1:]:
            ready = machine_ready_time[mid]
            if ready < best_ready:
                best_ready = ready
                best_machine = mid
            elif ready == best_ready:
                if preferred_machine is not None and mid == preferred_machine and best_machine != preferred_machine:
                    best_machine = mid
                elif mid < best_machine and best_machine != preferred_machine:
                    best_machine = mid
        return best_machine

    def _earliest_feasible_start(self, machine_id: int, earliest: float) -> float:
        """
        考虑机台 maintenance / calendar 停机窗口，返回不早于 earliest 的最早可开工时刻。
        窗口格式: {"start": float, "end": float}
        """
        t = float(earliest)
        if machine_id < 0 or machine_id >= self.num_machines:
            return t
        blocks = []
        machine = self.machines[machine_id]
        for key in ("maintenance", "calendar"):
            for block in getattr(machine, key, []) or []:
                if isinstance(block, dict):
                    blocks.append((float(block.get("start", 0)), float(block.get("end", 0))))
                elif isinstance(block, (list, tuple)) and len(block) >= 2:
                    blocks.append((float(block[0]), float(block[1])))
        if not blocks:
            return t
        blocks.sort(key=lambda x: x[0])
        changed = True
        while changed:
            changed = False
            for start, end in blocks:
                if start <= t < end:
                    t = end
                    changed = True
        return t

    def evaluate(self, operation_order):
        """
        计算 Makespan (最大完工时间)
        :param operation_order: 工件索引的序列 (e.g., [0, 1, 0, 2, ...])
        """
        job_ptr = [0] * self.num_jobs
        machine_ready_time = self.initial_machine_ready[:]
        job_ready_time = [float(getattr(job, "arrival_time", 0) or 0) for job in self.jobs]

        for job_idx in operation_order:
            job = self.jobs[job_idx]
            op_idx = job_ptr[job_idx]

            if op_idx >= len(job):
                continue

            task = job.tasks[op_idx]
            selected_machine = self._select_machine_for_task(
                task, machine_ready_time, preferred_machine=task.machine_id
            )
            start_time = max(machine_ready_time[selected_machine], job_ready_time[job_idx])
            start_time = self._earliest_feasible_start(selected_machine, start_time)
            end_time = start_time + task.duration

            machine_ready_time[selected_machine] = end_time
            job_ready_time[job_idx] = end_time
            job_ptr[job_idx] += 1

        return max(job_ready_time) if job_ready_time else 0

    def get_schedule(self, operation_order):
        """
        生成详细的调度时间表 (用于前端画甘特图)
        """
        job_ptr = [0] * self.num_jobs
        machine_ready_time = self.initial_machine_ready[:]
        job_ready_time = [float(getattr(job, "arrival_time", 0) or 0) for job in self.jobs]
        schedule = []

        for job_idx in operation_order:
            job = self.jobs[job_idx]
            op_idx = job_ptr[job_idx]

            if op_idx >= len(job):
                continue

            task = job.tasks[op_idx]
            selected_machine = self._select_machine_for_task(
                task, machine_ready_time, preferred_machine=task.machine_id
            )
            start_time = max(machine_ready_time[selected_machine], job_ready_time[job_idx])
            start_time = self._earliest_feasible_start(selected_machine, start_time)
            end_time = start_time + task.duration

            schedule.append({
                "job_id": job_idx,
                "priority": job.priority,  # [新增] 将优先级传递给前端
                "operation_id": op_idx,
                "operation_name": task.name,  # <--- 关键：传递工序名称
                "machine_id": selected_machine,
                "machine_options": task.candidate_machines(),
                "machine_group": task.machine_group,
                "start": start_time,
                "end": end_time
            })

            machine_ready_time[selected_machine] = end_time
            job_ready_time[job_idx] = end_time
            job_ptr[job_idx] += 1

        return schedule

    def generate_random_solution(self):
        """生成一个随机的可行解序列"""
        operation_order = []
        for job_id, job in enumerate(self.jobs):
            operation_order += [job_id] * len(job)
        random.shuffle(operation_order)
        return operation_order

    def perturb(self, operation_order):
        """邻域搜索：随机交换两个位置"""
        neighbor = operation_order[:]
        if len(neighbor) < 2:
            return neighbor
        i, j = random.sample(range(len(neighbor)), 2)
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        return neighbor

    def get_move(self, old_solution, new_solution):
        """(用于禁忌搜索) 识别两个解之间的差异 moves"""
        for i in range(len(old_solution)):
            if old_solution[i] != new_solution[i]:
                for j in range(i + 1, len(old_solution)):
                    if (old_solution[i] == new_solution[j] and
                            old_solution[j] == new_solution[i]):
                        return (i, j)
        return None