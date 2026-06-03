import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque

from metaforge.core.base_solver import BaseSolver
from metaforge.solvers.dqn_solver import ReplayBuffer

import random
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque, namedtuple
from metaforge.core.base_solver import BaseSolver


# === 辅助类定义 ===

class QNetwork_Basic(nn.Module):
    def __init__(self, input_size, output_size):
        super(QNetwork_Basic, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, 64),
            nn.ReLU(),
            nn.Linear(64, output_size)
        )

    def forward(self, x):
        return self.net(x)


class QNetwork(nn.Module):
    def __init__(self, input_size, output_size):
        super(QNetwork, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, output_size)
        )

    def forward(self, x):
        return self.net(x)


class ReplayBuffer:
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)
        self.transition = namedtuple("Transition", ["state", "action", "reward", "next_state", "done"])

    def add(self, *args):
        self.buffer.append(self.transition(*args))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        return zip(*batch)

    def __len__(self):
        return len(self.buffer)

    def clear(self):
        self.buffer.clear()


# === 算法 1: Naive DQN (基础版) ===

class DQNAgentSolver(BaseSolver):
    def __init__(self, problem, episodes=400, epsilon=0.1, gamma=0.95, lr=1e-3):
        super().__init__(problem)
        self.episodes = episodes
        self.epsilon = epsilon
        self.gamma = gamma
        self.lr = lr

        self.num_jobs = len(problem.jobs)
        self.job_counts = [len(job) for job in problem.jobs]

        self.input_size = self.num_jobs * 2
        self.output_size = self.num_jobs

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.qnet = QNetwork_Basic(self.input_size, self.output_size).to(self.device)
        self.optimizer = optim.Adam(self.qnet.parameters(), lr=self.lr)
        self.loss_fn = nn.MSELoss()

    def _get_initial_state(self):
        return [0] * self.num_jobs, [0] * self.num_jobs

    def _is_terminal(self, job_ptrs):
        return all(job_ptrs[j] >= self.job_counts[j] for j in range(self.num_jobs))

    def _get_available_jobs(self, job_ptrs):
        return [j for j in range(self.num_jobs) if job_ptrs[j] < self.job_counts[j]]

    def _build_state_vector(self, job_ptrs, job_ready):
        return torch.tensor(job_ptrs + job_ready, dtype=torch.float32, device=self.device)

    def run(self, track_history=True, **kwargs):
        """标准化运行接口"""
        start_time = time.time()  # 开始计时

        best_solution = None
        best_score = float("inf")
        history = [] if track_history else None

        for ep in range(self.episodes):
            job_ptrs, job_ready = self._get_initial_state()
            machine_ready = [0] * self.problem.num_machines
            sequence = []

            while not self._is_terminal(job_ptrs):
                available = self._get_available_jobs(job_ptrs)
                state_tensor = self._build_state_vector(job_ptrs, job_ready).unsqueeze(0)
                q_values = self.qnet(state_tensor).detach().cpu().numpy()[0]

                if random.random() < self.epsilon:
                    action = random.choice(available)
                else:
                    mask = np.full(self.num_jobs, -np.inf)
                    for j in available:
                        mask[j] = q_values[j]
                    action = int(np.argmax(mask))

                sequence.append(action)

                # Simulate
                op_idx = job_ptrs[action]
                task = self.problem.jobs[action].tasks[op_idx]
                machine, proc_time = task.machine_id, task.duration
                start_time_op = max(machine_ready[machine], job_ready[action])
                end_time_op = start_time_op + proc_time

                job_ptrs[action] += 1
                job_ready[action] = end_time_op
                machine_ready[machine] = end_time_op

                # Q-Update
                next_state_tensor = self._build_state_vector(job_ptrs, job_ready).unsqueeze(0)
                with torch.no_grad():
                    next_q = self.qnet(next_state_tensor)
                    max_future_q = torch.max(next_q[0][available]).item() if available else 0

                target_q = q_values[:]
                reward = -1 if not self._is_terminal(job_ptrs) else -self.problem.evaluate(sequence)
                target_q[action] = reward + self.gamma * max_future_q

                pred_q = self.qnet(state_tensor)[0]
                target_tensor = torch.tensor(target_q, dtype=torch.float32, device=self.device)

                loss = self.loss_fn(pred_q, target_tensor)
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()

            final_score = self.problem.evaluate(sequence)
            if final_score < best_score:
                best_score = final_score
                best_solution = sequence[:]

            if track_history:
                history.append(best_score)

        end_time = time.time()  # 结束计时
        runtime = end_time - start_time

        # === 生成甘特图数据 ===
        gantt_data = []
        if best_solution is not None:
            gantt_data = self.problem.get_schedule(best_solution)

        return {
            "algorithm": "DQN (Naive)",
            "best_score": int(best_score) if best_score != float('inf') else 0,
            "best_solution": best_solution,
            "runtime_sec": round(runtime, 4),
            "history": history,
            "gantt_data": gantt_data
        }


# === 算法 2: DQN with Replay (经验回放版) ===

class DQNAgentSolverReplay(BaseSolver):
    def __init__(self, problem, episodes=400, epsilon=1.0, epsilon_min=0.05,
                 epsilon_decay=0.995, gamma=0.95, lr=1e-3,
                 buffer_capacity=10000, batch_size=64, target_update_freq=10):
        super().__init__(problem)
        self.episodes = episodes
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.gamma = gamma
        self.lr = lr
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq

        self.job_counts = [len(job) for job in problem.jobs]
        self.num_jobs = len(self.job_counts)
        self.input_size = self.num_jobs * 2
        self.output_size = self.num_jobs

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.qnet = QNetwork(self.input_size, self.output_size).to(self.device)
        self.target_qnet = QNetwork(self.input_size, self.output_size).to(self.device)
        self.target_qnet.load_state_dict(self.qnet.state_dict())
        self.target_qnet.eval()

        self.optimizer = optim.Adam(self.qnet.parameters(), lr=self.lr)
        self.loss_fn = nn.MSELoss()
        self.buffer = ReplayBuffer(capacity=buffer_capacity)

    def _build_state_tensor(self, job_ptrs, job_ready):
        return torch.tensor(job_ptrs + job_ready, dtype=torch.float32, device=self.device)

    def _get_available_jobs(self, job_ptrs):
        return [j for j in range(self.num_jobs) if job_ptrs[j] < self.job_counts[j]]

    def _is_terminal(self, job_ptrs):
        return all(job_ptrs[j] >= self.job_counts[j] for j in range(self.num_jobs))

    def _shaped_reward(self, current_makespan, previous_makespan):
        if previous_makespan is None:
            return 0
        return previous_makespan - current_makespan

    def train_step(self):
        if len(self.buffer) < self.batch_size:
            return

        states, actions, rewards, next_states, dones = self.buffer.sample(self.batch_size)

        states = torch.stack(states)
        actions = torch.tensor(actions, dtype=torch.int64, device=self.device)
        rewards = torch.tensor(rewards, dtype=torch.float32, device=self.device)
        next_states = torch.stack(next_states)
        dones = torch.tensor(dones, dtype=torch.float32, device=self.device)

        q_values = self.qnet(states)
        target_q_values = self.target_qnet(next_states).detach()

        q_selected = q_values.gather(1, actions.view(-1, 1)).squeeze(1)
        max_target_q = target_q_values.max(dim=1)[0]
        targets = rewards + self.gamma * max_target_q * (1 - dones)

        loss = self.loss_fn(q_selected, targets)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

    def run(self, track_history=True, **kwargs):
        """标准化运行接口"""
        start_time = time.time()  # 1. 开始计时

        best_solution = None
        best_score = float("inf")
        history = [] if track_history else None

        for ep in range(self.episodes):
            # 可以在控制台打印进度，不用传回前端
            # print(f"DQNAgentSolver (replay) - Episode {ep + 1}/{self.episodes}")

            job_ptrs = [0] * self.num_jobs
            job_ready = [0] * self.num_jobs
            machine_ready = [0] * self.problem.num_machines
            state = self._build_state_tensor(job_ptrs, job_ready)
            sequence = []
            prev_makespan = None

            while not self._is_terminal(job_ptrs):
                available = self._get_available_jobs(job_ptrs)

                with torch.no_grad():
                    q_vals = self.qnet(state.unsqueeze(0)).cpu().numpy()[0]
                    masked_q = np.full(self.num_jobs, -np.inf)
                    for j in available:
                        masked_q[j] = q_vals[j]

                if random.random() < self.epsilon:
                    action = random.choice(available)
                else:
                    action = int(np.argmax(masked_q))

                op_idx = job_ptrs[action]
                task = self.problem.jobs[action].tasks[op_idx]
                machine, proc_time = task.machine_id, task.duration
                start_time_op = max(machine_ready[machine], job_ready[action])
                end_time_op = start_time_op + proc_time

                # Apply action
                job_ptrs[action] += 1
                job_ready[action] = end_time_op
                machine_ready[machine] = end_time_op
                next_state = self._build_state_tensor(job_ptrs, job_ready)

                sequence.append(action)
                current_makespan = self.problem.evaluate(sequence)

                reward = self._shaped_reward(current_makespan, prev_makespan)
                prev_makespan = current_makespan
                done = self._is_terminal(job_ptrs)

                self.buffer.add(state, action, reward, next_state, done)
                state = next_state

                self.train_step()

            # Target network update
            if ep % self.target_update_freq == 0:
                self.target_qnet.load_state_dict(self.qnet.state_dict())

            score = self.problem.evaluate(sequence)
            if score < best_score:
                best_score = score
                best_solution = sequence[:]

            if track_history:
                history.append(best_score)

            # Decay epsilon
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        end_time = time.time()  # 2. 结束计时
        runtime = end_time - start_time

        # === 3. 生成甘特图数据 ===
        gantt_data = []
        if best_solution is not None:
            gantt_data = self.problem.get_schedule(best_solution)

        # === 4. 返回标准字典 ===
        return {
            "algorithm": "DQN (Replay)",
            "best_score": int(best_score) if best_score != float('inf') else 0,
            "best_solution": best_solution,
            "runtime_sec": round(runtime, 4),
            "history": history,
            "gantt_data": gantt_data
        }