import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
from metaforge.core.base_solver import BaseSolver
from metaforge.solvers.dqn_solver import QNetwork, ReplayBuffer


class DQNAgentSolverReplayDynamic(BaseSolver):
    """
    【最终完整版 - 已安装逻辑门控】
    奖励函数采用持续性惩罚，并引入逻辑门控限制“无脑”加班。
    修复了所有已知的 TypeError 和 UnboundLocalError。
    """

    def __init__(self, problem, dynamic_events=None, episodes=300,
                 max_jobs=15,
                 epsilon=1.0, epsilon_min=0.1,
                 epsilon_decay=0.999, gamma=0.99, lr=1e-4,
                 buffer_capacity=10000, batch_size=64, target_update_freq=100,
                 reward_on_time=15.0,
                 tardiness_penalty=100.0,
                 overtime_penalty_per_unit=2.0,
                 cost_weight=10.0):

        super().__init__(problem)
        if not hasattr(self.problem, 'initial_jobs'):
            self.problem.initial_jobs = [job for job in self.problem.jobs]
        self.original_dynamic_events = [e.copy() for e in dynamic_events] if dynamic_events else []

        self.MAX_JOBS = max_jobs
        self.MAX_MACHINES = self.problem.num_machines

        self.episodes = episodes
        self.epsilon_init = epsilon
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.gamma = gamma
        self.lr = lr
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq

        self.REWARD_ON_TIME = reward_on_time
        self.TARDINESS_PENALTY = tardiness_penalty
        self.OVERTIME_PENALTY_PER_UNIT = overtime_penalty_per_unit
        self.COST_WEIGHT = cost_weight
        self.OUTSOURCING_COST = getattr(self.problem, 'OUTSOURCING_COST', 300)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.loss_fn = nn.MSELoss()

        self._initialize_problem_parameters()
        self._initialize_networks()
        self.buffer = ReplayBuffer(capacity=buffer_capacity)

    def _initialize_problem_parameters(self):
        self.job_counts = [len(job.tasks) for job in self.problem.jobs]
        self.num_jobs = len(self.job_counts)
        self.total_ops = sum(self.job_counts)
        self.input_size = self.MAX_JOBS * 3 + self.MAX_MACHINES
        self.output_size = self.MAX_JOBS + self.MAX_MACHINES + 1

    def _initialize_networks(self):
        print(f"🧠 初始化固定尺寸网络：输入 {self.input_size}, 输出 {self.output_size}")
        self.qnet = QNetwork(self.input_size, self.output_size).to(self.device)
        self.target_qnet = QNetwork(self.input_size, self.output_size).to(self.device)
        self.target_qnet.load_state_dict(self.qnet.state_dict())
        self.target_qnet.eval()
        self.optimizer = optim.Adam(self.qnet.parameters(), lr=self.lr)

    def _build_state_tensor(self, job_ptrs, job_ready, machine_status):
        current_num_jobs = len(job_ptrs)
        job_tardiness = []
        for j in range(current_num_jobs):
            if job_ptrs[j] < self.job_counts[j]:
                remaining_time_est = sum(
                    self.problem.jobs[j].tasks[i].duration for i in range(job_ptrs[j], self.job_counts[j]))
                est_completion_time = max(self.current_time, job_ready[j]) + remaining_time_est
                tardiness = max(0, est_completion_time - self.problem.jobs[j].due_date)
                job_tardiness.append(tardiness)
            else:
                job_tardiness.append(0)
        padded_ptrs = job_ptrs + [0] * (self.MAX_JOBS - current_num_jobs)
        padded_ready = job_ready + [0] * (self.MAX_JOBS - current_num_jobs)
        padded_tardiness = job_tardiness + [0] * (self.MAX_JOBS - current_num_jobs)
        padded_machine_status = machine_status + [0] * (self.MAX_MACHINES - len(machine_status))
        return torch.tensor(padded_ptrs + padded_ready + padded_tardiness + padded_machine_status, dtype=torch.float32,
                            device=self.device)

    # === 【核心修改】这里是全新的“逻辑门控”函数 ===
    def _get_available_actions(self, job_ptrs, job_ready, machine_status, machine_modes):
        """
        【逻辑门控版】
        获取当前合法的动作。只有在系统“延期压力”足够大时，才将加班选项加入。
        """
        available_actions = []
        current_num_jobs = len(job_ptrs)

        # 1. 获取可调度的工序
        for j in range(current_num_jobs):
            if job_ptrs[j] < self.job_counts[j]:
                op_idx = job_ptrs[j]
                machine_req = self.problem.jobs[j].tasks[op_idx].machine_id
                if machine_status[machine_req] == 1:
                    available_actions.append(j)

        # 2. 计算系统整体的“延期压力”
        total_urgency = 0
        num_pending_jobs = 0
        for j in range(current_num_jobs):
            if job_ptrs[j] < self.job_counts[j]:
                num_pending_jobs += 1
                remaining_time_est = sum(
                    self.problem.jobs[j].tasks[i].duration for i in range(job_ptrs[j], self.job_counts[j]))
                est_completion_time = max(self.current_time, job_ready[j]) + remaining_time_est
                due_date = self.problem.jobs[j].due_date

                if due_date > 0:
                    # 紧急度定义为：(预估完成时间 - 交付日期) / 交付日期
                    urgency = (est_completion_time - due_date) / due_date
                    total_urgency += max(0, urgency)  # 只累加正的紧急度（有延期风险的）

        avg_urgency = (total_urgency / num_pending_jobs) if num_pending_jobs > 0 else 0

        # 3. 设置门控，只有在压力大时才允许加班
        OVERTIME_PRESSURE_THRESHOLD = 0.05  # 阈值：当平均紧急度超过10%时
        if avg_urgency > OVERTIME_PRESSURE_THRESHOLD:
            for m in range(self.problem.num_machines):
                if machine_modes[m] == 'normal':
                    available_actions.append(current_num_jobs + m)

        # 4. 获取外包动作
        if not self._is_terminal(job_ptrs):
            outsourcing_action_index = current_num_jobs + self.problem.num_machines
            available_actions.append(outsourcing_action_index)

        return available_actions

    def _is_terminal(self, job_ptrs):
        if not job_ptrs: return True
        return all(job_ptrs[j] >= self.job_counts[j] for j in range(len(job_ptrs)))

    def _handle_time_based_events(self, job_ptrs, job_ready):
        for event in list(self.dynamic_events):
            if event['type'] == 'new_job_arrival' and event.get('time') is not None and event[
                'time'] <= self.current_time:
                if len(self.problem.jobs) >= self.MAX_JOBS:
                    self.dynamic_events.remove(event)
                    continue
                self.problem.jobs.append(event['job'])
                self.job_counts.append(len(event['job'].tasks))
                self.num_jobs = len(self.problem.jobs)
                job_ptrs.append(0)
                job_ready.append(event['time'])
                self.dynamic_events.remove(event)

    def _handle_machine_usage_events(self, machine_id, current_end_time, machine_ready, machine_task_counters):
        machine_task_counters[machine_id] += 1
        current_task_count = machine_task_counters[machine_id]
        for event in list(self.dynamic_events):
            if event['type'] == 'machine_breakdown_on_nth_task':
                trigger = event['trigger']
                if trigger['machine'] == machine_id and trigger['task_count'] == current_task_count:
                    duration = event['duration']
                    machine_ready[machine_id] = max(machine_ready[machine_id], current_end_time + duration)
                    self.dynamic_events.remove(event)

    def train_step(self):
        if len(self.buffer) < self.batch_size: return
        states, actions, rewards, next_states, dones = self.buffer.sample(self.batch_size)
        states = torch.stack(states)
        next_states = torch.stack(next_states)
        actions = torch.tensor(actions, dtype=torch.int64, device=self.device).view(-1, 1)
        rewards = torch.tensor(rewards, dtype=torch.float32, device=self.device)
        dones = torch.tensor(dones, dtype=torch.float32, device=self.device)
        q_selected = self.qnet(states).gather(1, actions).squeeze(1)
        with torch.no_grad():
            max_target_q = self.target_qnet(next_states).max(dim=1)[0]
        targets = rewards + self.gamma * max_target_q * (1 - dones)
        loss = self.loss_fn(q_selected, targets)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

    def run(self, track_history=True, track_schedule=False):
        best_solution_schedule, best_score, history = None, float("inf"), []

        for ep in range(self.episodes):
            print(f"DQNAgentSolver (持续性惩罚) - Episode {ep + 1}/{self.episodes}")
            self.problem.jobs = [job for job in self.problem.initial_jobs]
            self.dynamic_events = [e.copy() for e in self.original_dynamic_events]
            self._initialize_problem_parameters()
            self.epsilon = max(self.epsilon_min, self.epsilon_init * (self.epsilon_decay ** ep))
            self.job_ptrs = [0] * self.num_jobs
            job_ready = [0] * self.num_jobs
            machine_ready = [0] * self.problem.num_machines
            machine_task_counters = [0] * self.problem.num_machines
            machine_modes = ['normal'] * self.problem.num_machines
            self.current_time = 0
            live_schedule = []

            while not self._is_terminal(self.job_ptrs):
                self._handle_time_based_events(self.job_ptrs, job_ready)
                current_num_jobs = len(self.job_ptrs)
                machine_status = [1 if machine_ready[m] <= self.current_time else 0 for m in
                                  range(self.problem.num_machines)]
                state = self._build_state_tensor(self.job_ptrs, job_ready, machine_status)

                # === 【核心修改】确保这里的函数调用是正确的，与上面的定义匹配 ===
                available_actions = self._get_available_actions(self.job_ptrs, job_ready, machine_status, machine_modes)

                if not any(a < current_num_jobs for a in available_actions) and not self._is_terminal(self.job_ptrs):
                    ready_times = [t for t in machine_ready if t > self.current_time]
                    if not ready_times: break
                    self.current_time = min(ready_times)
                    continue
                if not available_actions: break

                if random.random() < self.epsilon:
                    action_logic = random.choice(available_actions)
                else:
                    with torch.no_grad():
                        q_vals = self.qnet(state.unsqueeze(0)).cpu().numpy()[0]
                    masked_q = np.full(self.output_size, -np.inf)
                    for a in available_actions:
                        if a < current_num_jobs:
                            masked_q[a] = q_vals[a]
                        elif current_num_jobs <= a < current_num_jobs + self.problem.num_machines:
                            machine_idx = a - current_num_jobs
                            masked_q[self.MAX_JOBS + machine_idx] = q_vals[self.MAX_JOBS + machine_idx]
                        else:
                            masked_q[-1] = q_vals[-1]
                    action_mapped = int(np.argmax(masked_q))
                    if action_mapped < self.MAX_JOBS:
                        action_logic = action_mapped
                    elif self.MAX_JOBS <= action_mapped < self.MAX_JOBS + self.MAX_MACHINES:
                        action_logic = current_num_jobs + (action_mapped - self.MAX_JOBS)
                    else:
                        action_logic = current_num_jobs + self.problem.num_machines

                reward = 0

                action_for_buffer = -1
                if action_logic < current_num_jobs:
                    action_for_buffer = action_logic
                elif current_num_jobs <= action_logic < current_num_jobs + self.problem.num_machines:
                    machine_idx = action_logic - current_num_jobs
                    action_for_buffer = self.MAX_JOBS + machine_idx
                else:
                    action_for_buffer = self.MAX_JOBS + self.MAX_MACHINES

                if 0 <= action_logic < current_num_jobs:
                    job_id = action_logic
                    op_idx = self.job_ptrs[job_id]
                    task = self.problem.jobs[job_id].tasks[op_idx]
                    machine, proc_time = task.machine_id, task.duration

                    start_time = max(machine_ready[machine], job_ready[job_id])
                    self.current_time = max(self.current_time, start_time)
                    end_time = self.current_time + proc_time

                    reward -= proc_time
                    if machine_modes[machine] == 'overtime':
                        overtime_penalty = proc_time * self.OVERTIME_PENALTY_PER_UNIT * self.COST_WEIGHT
                        reward -= overtime_penalty

                    machine_ready[machine], job_ready[job_id] = end_time, end_time
                    self.job_ptrs[job_id] += 1

                    task_info = {"job": job_id, "operation": op_idx, "machine": machine, "start": start_time,
                                 "end": end_time, "is_overtime": machine_modes[machine] == 'overtime',
                                 "is_outsourced": False}
                    live_schedule.append(task_info)

                    if self.job_ptrs[job_id] >= self.job_counts[job_id]:
                        due_date = self.problem.jobs[job_id].due_date
                        tardiness = max(0, end_time - due_date)
                        if tardiness > 0:
                            tardiness_penalty = tardiness * self.TARDINESS_PENALTY * self.COST_WEIGHT
                            reward -= tardiness_penalty
                        else:
                            reward += self.REWARD_ON_TIME

                    self._handle_machine_usage_events(machine, end_time, machine_ready, machine_task_counters)

                elif current_num_jobs <= action_logic < current_num_jobs + self.problem.num_machines:
                    machine_id_to_overtime = action_logic - current_num_jobs
                    if machine_modes[machine_id_to_overtime] == 'normal':
                        machine_modes[machine_id_to_overtime] = 'overtime'
                        reward -= 1.0
                    else:
                        reward -= 5.0

                elif action_logic == current_num_jobs + self.problem.num_machines:
                    job_tardiness_list = [max(0, max(self.current_time, job_ready[j]) + sum(
                        self.problem.jobs[j].tasks[i].duration for i in range(self.job_ptrs[j], self.job_counts[j])) -
                                              self.problem.jobs[j].due_date) if self.job_ptrs[j] < self.job_counts[
                        j] else -1 for j in range(current_num_jobs)]
                    if any(t > 0 for t in job_tardiness_list):
                        job_to_outsource = int(np.argmax(job_tardiness_list))
                        task_info = {"job": job_to_outsource, "operation": -1, "machine": -1,
                                     "start": self.current_time, "end": self.current_time + 20, "is_overtime": False,
                                     "is_outsourced": True}
                        live_schedule.append(task_info)
                        job_ready[job_to_outsource] = max(job_ready[job_to_outsource], self.current_time + 20)
                        self.job_ptrs[job_to_outsource] = self.job_counts[job_to_outsource]
                        reward -= self.OUTSOURCING_COST * self.COST_WEIGHT
                    else:
                        reward -= 10

                next_machine_status = [1 if machine_ready[m] <= self.current_time else 0 for m in
                                       range(self.problem.num_machines)]
                next_state = self._build_state_tensor(self.job_ptrs, job_ready, next_machine_status)
                done = self._is_terminal(self.job_ptrs)

                self.buffer.add(state, action_for_buffer, reward, next_state, done)

                self.train_step()

            if ep % self.target_update_freq == 0:
                self.target_qnet.load_state_dict(self.qnet.state_dict())

            score = max(machine_ready) if machine_ready else 0

            print(f"--- Episode {ep + 1} 结束 ---")
            print(f"  - 本回合 Score (Makespan): {score:.2f}")
            print(f"  - 本回合 Schedule 中的工序数量: {len(live_schedule)}")
            print(f"  - 当前 Best Score: {best_score:.2f}")

            if score > 0 and score < best_score:
                print(f"  ✨ 新的最优解被发现！Score 从 {best_score:.2f} 提升到 {score:.2f}.")
                best_score = score
                best_solution_schedule = live_schedule[:]
                print(f"  - best_solution_schedule 已被更新，现在包含 {len(best_solution_schedule)} 个工序。")
            elif best_solution_schedule is None and score > 0:
                print(f"  ✨ 找到第一个有效解！Score: {score:.2f}.")
                best_score = score
                best_solution_schedule = live_schedule[:]
            else:
                print(f"  - 未找到更优解，Best Score 保持为 {best_score:.2f}.")

            if track_history:
                history.append(best_score)

        print("\n--- 所有回合结束，准备返回最终结果 ---")
        if best_solution_schedule:
            print(f"  ✅ 最终将返回一个有效的调度方案，包含 {len(best_solution_schedule)} 个工序。")
        else:
            print(f"  ❌ 最终的 best_solution_schedule 是 None 或空列表！")

        return {
            "solution": best_solution_schedule,
            "makespan": best_score,
            "history": history,
            "all_schedules": [best_solution_schedule] if best_solution_schedule else []
        }