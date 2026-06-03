import random
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque
from metaforge.core.base_solver import BaseSolver


# ==========================================
# 0. 辅助：极简局部搜索 (只做最后微调)
# ==========================================
def apply_local_search(problem, initial_sequence, max_steps=100):
    if not initial_sequence or len(initial_sequence) < 2:
        return initial_sequence, problem.evaluate(initial_sequence)

    current_seq = initial_sequence[:]
    current_score = problem.evaluate(current_seq)

    for _ in range(max_steps):
        i, j = random.sample(range(len(current_seq)), 2)
        neighbor = current_seq[:]
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]

        # 只做简单的完工时间评估
        neighbor_score = problem.evaluate(neighbor)

        if neighbor_score < current_score:
            current_seq = neighbor
            current_score = neighbor_score

    return current_seq, current_score


# ==========================================
# 1. 基础网络 (Simple MLP)
# ==========================================
class SimpleQNet(nn.Module):
    def __init__(self, input_dim, output_dim):
        super(SimpleQNet, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, output_dim)
        )

    def forward(self, x):
        return self.net(x)


# ==========================================
# 2. DQN 基类 (包含通用的状态、动作逻辑)
# ==========================================
class BaseDQNSolver(BaseSolver):
    def __init__(self, problem, episodes, epsilon, gamma, lr):
        super().__init__(problem)
        self.episodes = episodes
        self.epsilon = epsilon
        self.gamma = gamma
        self.lr = lr

        self.num_jobs = len(problem.jobs)
        self.num_machines = problem.num_machines
        self.job_counts = [len(job) for job in problem.jobs]

        # 状态: [进度, ReadyTime, MachineReady, Priority]
        self.input_size = self.num_jobs * 3 + self.num_machines
        self.output_size = self.num_jobs

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # 两个算法共用相同的网络结构
        self.qnet = SimpleQNet(self.input_size, self.output_size).to(self.device)
        self.optimizer = optim.Adam(self.qnet.parameters(), lr=self.lr)
        self.loss_fn = nn.MSELoss()

        # 优先级数据预处理
        raw_p = np.array([j.priority for j in problem.jobs])
        self.norm_p = torch.tensor(raw_p / (np.max(raw_p) + 1e-6), dtype=torch.float32, device=self.device)
        self.raw_p = raw_p

    def _get_state(self, ptrs, j_ready, m_ready):
        max_ops = max(self.job_counts) if max(self.job_counts) > 0 else 1
        p_t = torch.tensor(ptrs, dtype=torch.float32, device=self.device) / max_ops
        jr_t = torch.tensor(j_ready, dtype=torch.float32, device=self.device) / 1000.0
        mr_t = torch.tensor(m_ready, dtype=torch.float32, device=self.device) / 1000.0
        return torch.cat([p_t, jr_t, mr_t, self.norm_p])

    def _choose_action(self, state, avail):
        # 优先级引导的 Epsilon-Greedy
        if random.random() < self.epsilon:
            # 即使随机，也倾向于选急单 (Priority Weighted Random)
            weights = [self.raw_p[j] for j in avail]
            if sum(weights) == 0: weights = [1] * len(weights)
            action = random.choices(avail, weights=weights, k=1)[0]
        else:
            with torch.no_grad():
                q_values = self.qnet(state.unsqueeze(0)).cpu().numpy()[0]

            # Masking
            best_a = -1
            max_q = -float('inf')
            for a in avail:
                if q_values[a] > max_q:
                    max_q = q_values[a]
                    best_a = a
            action = best_a
        return action


# ==========================================
# 3. Naive DQN (纯真的单步更新)
#    区别：没有 Buffer，来一个数据练一次，不稳定
# ==========================================
class DQNAgentSolver(BaseDQNSolver):
    def __init__(self, problem, episodes=300, epsilon=0.4, gamma=0.9, lr=0.001):
        super().__init__(problem, episodes, epsilon, gamma, lr)

    def run(self, track_history=True, **kwargs):
        start_time = time.time()
        best_solution = None
        best_score = float("inf")
        history = []

        for ep in range(self.episodes):
            ptrs = [0] * self.num_jobs
            j_ready = [0] * self.num_jobs
            m_ready = [0] * self.num_machines
            seq = []
            prev_mk = 0

            state = self._get_state(ptrs, j_ready, m_ready)

            while not all(ptrs[j] >= self.job_counts[j] for j in range(self.num_jobs)):
                avail = [j for j in range(self.num_jobs) if ptrs[j] < self.job_counts[j]]
                action = self._choose_action(state, avail)
                seq.append(action)

                # Step
                task = self.problem.jobs[action].tasks[ptrs[action]]
                m_id = task.machine_id
                start = max(m_ready[m_id], j_ready[action])
                end = start + task.duration
                gap = start - m_ready[m_id]

                next_ptrs = ptrs[:]
                next_ptrs[action] += 1
                next_jr = j_ready[:]
                next_jr[action] = end
                next_mr = m_ready[:]
                next_mr[m_id] = end

                # Reward
                curr_mk = max(next_mr)
                r = (prev_mk - curr_mk) + self.norm_p[action].item() * 5.0 - 0.1 * gap
                prev_mk = curr_mk

                next_state = self._get_state(next_ptrs, next_jr, next_mr)
                done = all(next_ptrs[j] >= self.job_counts[j] for j in range(self.num_jobs))

                # === Naive 核心区别：单步训练 (Online Update) ===
                # 没有 Buffer，直接用当前这一步数据训练
                target = r
                if not done:
                    with torch.no_grad():
                        # 简单的 Q-Learning 公式
                        target += self.gamma * self.qnet(next_state.unsqueeze(0)).max().item()

                pred = self.qnet(state.unsqueeze(0))[0][action]
                loss = self.loss_fn(pred, torch.tensor(target, device=self.device))

                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                # ==============================================

                state = next_state
                ptrs, j_ready, m_ready = next_ptrs, next_jr, next_mr

            score = max(m_ready)
            if score < best_score:
                best_score = score
                best_solution = seq[:]
            if track_history: history.append(int(best_score))
            self.epsilon = max(0.05, self.epsilon * 0.99)

        # 简单的微调
        if best_solution:
            best_solution, best_score = apply_local_search(self.problem, best_solution)

        return {
            "algorithm": "DQN (Naive)",
            "best_score": int(best_score),
            "best_solution": [int(x) for x in best_solution] if best_solution else [],
            "runtime_sec": float(round(time.time() - start_time, 4)),
            "history": [int(x) for x in history],
            "gantt_data": self.problem.get_schedule(best_solution)
        }


# ==========================================
# 4. Replay DQN (经验回放版)
#    区别：有 Buffer，批量训练，更稳定
# ==========================================
class DQNAgentSolverReplay(BaseDQNSolver):
    def __init__(self, problem, episodes=500, epsilon=0.5, gamma=0.99, lr=0.0005):
        super().__init__(problem, episodes, epsilon, gamma, lr)
        # Replay 特有的组件
        self.buffer = deque(maxlen=2000)
        self.batch_size = 32
        # Target Network (Replay 版标配，增加稳定性)
        self.target_qnet = SimpleQNet(self.input_size, self.output_size).to(self.device)
        self.target_qnet.load_state_dict(self.qnet.state_dict())

    def run(self, track_history=True, **kwargs):
        start_time = time.time()
        best_solution = None
        best_score = float("inf")
        history = []
        step_count = 0

        for ep in range(self.episodes):
            ptrs = [0] * self.num_jobs
            j_ready = [0] * self.num_jobs
            m_ready = [0] * self.num_machines
            seq = []
            prev_mk = 0

            state = self._get_state(ptrs, j_ready, m_ready)

            while not all(ptrs[j] >= self.job_counts[j] for j in range(self.num_jobs)):
                avail = [j for j in range(self.num_jobs) if ptrs[j] < self.job_counts[j]]
                action = self._choose_action(state, avail)
                seq.append(action)

                # Step
                task = self.problem.jobs[action].tasks[ptrs[action]]
                m_id = task.machine_id
                start = max(m_ready[m_id], j_ready[action])
                end = start + task.duration
                gap = start - m_ready[m_id]

                next_ptrs = ptrs[:]
                next_ptrs[action] += 1
                next_jr = j_ready[:]
                next_jr[action] = end
                next_mr = m_ready[:]
                next_mr[m_id] = end

                curr_mk = max(next_mr)
                r = (prev_mk - curr_mk) + self.norm_p[action].item() * 5.0 - 0.1 * gap
                prev_mk = curr_mk

                next_state = self._get_state(next_ptrs, next_jr, next_mr)
                done = all(next_ptrs[j] >= self.job_counts[j] for j in range(self.num_jobs))

                # === Replay 核心区别：存 Buffer + 批量训练 ===
                self.buffer.append((state, action, r, next_state, done))

                if len(self.buffer) > self.batch_size:
                    batch = random.sample(self.buffer, self.batch_size)
                    bs, ba, br, bns, bd = zip(*batch)

                    bs_t = torch.stack(bs)
                    ba_t = torch.tensor(ba, device=self.device).long().unsqueeze(1)
                    br_t = torch.tensor(br, device=self.device).float()
                    bns_t = torch.stack(bns)
                    bd_t = torch.tensor(bd, device=self.device).float()

                    # 当前 Q
                    q_curr = self.qnet(bs_t).gather(1, ba_t).squeeze()

                    # Target Q (Double DQN 简化版，用 Target Net 估值)
                    with torch.no_grad():
                        q_next = self.target_qnet(bns_t).max(1)[0]
                        target = br_t + self.gamma * q_next * (1 - bd_t)

                    loss = self.loss_fn(q_curr, target)
                    self.optimizer.zero_grad()
                    loss.backward()
                    self.optimizer.step()
                # ============================================

                state = next_state
                ptrs, j_ready, m_ready = next_ptrs, next_jr, next_mr
                step_count += 1

            if ep % 20 == 0:
                self.target_qnet.load_state_dict(self.qnet.state_dict())

            score = max(m_ready)
            if score < best_score:
                best_score = score
                best_solution = seq[:]
            if track_history: history.append(int(best_score))
            self.epsilon = max(0.05, self.epsilon * 0.99)

        if best_solution:
            best_solution, best_score = apply_local_search(self.problem, best_solution)

        return {
            "algorithm": "DQN (Replay)",
            "best_score": int(best_score),
            "best_solution": [int(x) for x in best_solution] if best_solution else [],
            "runtime_sec": float(round(time.time() - start_time, 4)),
            "history": [int(x) for x in history],
            "gantt_data": self.problem.get_schedule(best_solution)
        }