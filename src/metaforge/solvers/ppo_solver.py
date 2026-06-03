import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
import time
import copy
from torch.distributions import Categorical
from metaforge.core.base_solver import BaseSolver
from metaforge.solvers.heuristic_rules import MWKRSolver


# ==========================================
# 0. 辅助：局部搜索
# ==========================================
def apply_local_search(problem, initial_sequence, max_steps=500):
    if not initial_sequence or len(initial_sequence) < 2:
        return initial_sequence, problem.evaluate(initial_sequence)
    current_seq = initial_sequence[:]
    current_score = problem.evaluate(current_seq)
    for _ in range(max_steps):
        i, j = random.sample(range(len(current_seq)), 2)
        neighbor = current_seq[:]
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        sc = problem.evaluate(neighbor)
        if sc < current_score:
            current_seq = neighbor
            current_score = sc
    return current_seq, current_score


# ==========================================
# 1. 记忆库
# ==========================================
class PPOMemory:
    def __init__(self):
        self.states_j = []
        self.states_m = []
        self.actions = []
        self.probs = []
        self.vals = []
        self.rewards = []
        self.dones = []
        self.masks = []

    def generate_batches(self):
        n = len(self.states_j)
        if n == 0: return [], [], [], [], [], [], [], [], []
        batch_start = np.arange(0, n, 64)
        indices = np.arange(n, dtype=np.int64)
        np.random.shuffle(indices)
        batches = [indices[i:i + 64] for i in batch_start]
        return np.array(self.states_j), np.array(self.states_m), np.array(self.actions), \
            np.array(self.probs), np.array(self.vals), np.array(self.rewards), \
            np.array(self.dones), np.array(self.masks), batches

    def store_memory(self, sj, sm, a, p, v, r, d, m):
        self.states_j.append(sj)
        self.states_m.append(sm)
        self.actions.append(a)
        self.probs.append(p)
        self.vals.append(v)
        self.rewards.append(r)
        self.dones.append(d)
        self.masks.append(m)

    def clear_memory(self):
        self.states_j = []
        self.states_m = []
        self.actions = []
        self.probs = []
        self.vals = []
        self.rewards = []
        self.dones = []
        self.masks = []


# ==========================================
# 2. 网络结构
# ==========================================
class ActorCritic(nn.Module):
    def __init__(self, num_jobs, num_machines, embedding_dim=128):
        super(ActorCritic, self).__init__()
        self.num_jobs = num_jobs
        self.job_embed = nn.Sequential(nn.Linear(3, embedding_dim), nn.LayerNorm(embedding_dim), nn.ReLU())
        self.attn = nn.MultiheadAttention(embed_dim=embedding_dim, num_heads=4, batch_first=True)
        self.machine_embed = nn.Sequential(nn.Linear(num_machines, embedding_dim), nn.LayerNorm(embedding_dim),
                                           nn.ReLU())
        self.fc_shared = nn.Sequential(nn.Linear(embedding_dim * 2, 256), nn.ReLU(), nn.Linear(256, 128), nn.ReLU())
        self.actor = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 1))
        self.critic = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 1))

    def forward(self, state_j, state_m):
        j_emb = self.job_embed(state_j)
        j_feat, _ = self.attn(j_emb, j_emb, j_emb)
        j_feat = j_emb + j_feat
        m_emb = self.machine_embed(state_m)
        m_emb_exp = m_emb.unsqueeze(1).expand(-1, self.num_jobs, -1)
        combined = torch.cat([j_feat, m_emb_exp], dim=2)
        feat = self.fc_shared(combined)
        return self.actor(feat).squeeze(-1), self.critic(torch.max(feat, dim=1)[0])


# ==========================================
# 3. PPO Solver
# ==========================================
class PPOSolver(BaseSolver):
    def __init__(self, problem, episodes=500, gamma=0.99, lr=0.0005, **kwargs):
        super().__init__(problem)
        self.episodes = episodes
        self.gamma = gamma
        self.lr = lr
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.num_jobs = len(problem.jobs)
        self.num_machines = problem.num_machines
        self.job_counts = [len(job) for job in problem.jobs]

        self.policy = ActorCritic(self.num_jobs, self.num_machines).to(self.device)
        self.optimizer = optim.Adam(self.policy.parameters(), lr=lr)
        self.memory = PPOMemory()

        raw_p = np.array([j.priority for j in problem.jobs])
        self.norm_priorities = torch.tensor(raw_p / (np.max(raw_p) + 1e-6), dtype=torch.float32, device=self.device)

        self.job_total_work = []
        for job in problem.jobs:
            self.job_total_work.append(sum(t.duration for t in job.tasks))
        self.work_tensor = torch.tensor(self.job_total_work, dtype=torch.float32, device=self.device)
        if self.work_tensor.max() > 0: self.work_tensor /= self.work_tensor.max()

    def _get_initial_state(self):
        return [0] * self.num_jobs, [0] * self.num_jobs

    def _is_terminal(self, job_ptrs):
        return all(job_ptrs[j] >= self.job_counts[j] for j in range(self.num_jobs))

    def _build_tensors(self, job_ptrs, job_ready, machine_ready):
        max_ops = max(self.job_counts) if max(self.job_counts) > 0 else 1
        j_feats, mask = [], []
        for j in range(self.num_jobs):
            prog = job_ptrs[j] / max_ops
            r_time = job_ready[j] / 2000.0
            prio = self.norm_priorities[j].item()
            j_feats.append([prog, r_time, prio])
            mask.append(1 if job_ptrs[j] < self.job_counts[j] else 0)

        j_t = torch.tensor(j_feats, dtype=torch.float32, device=self.device)
        m_t = torch.tensor(machine_ready, dtype=torch.float32, device=self.device) / 2000.0
        mask_t = torch.tensor(mask, dtype=torch.bool, device=self.device)
        return j_t, m_t, mask_t

    def choose_action(self, sj, sm, mask, deterministic=False):
        sj_in, sm_in, mask_in = sj.unsqueeze(0), sm.unsqueeze(0), mask.unsqueeze(0)
        with torch.no_grad():
            logits, val = self.policy(sj_in, sm_in)

            # Bias Injection
            bias = (self.norm_priorities * 5.0) + (self.work_tensor * 1.5)
            logits = logits + bias.unsqueeze(0)

            logits = logits.masked_fill(~mask_in, float('-inf'))
            probs = torch.softmax(logits, dim=1)

            if deterministic:
                action = torch.argmax(probs, dim=1)
            else:
                dist = Categorical(probs)
                action = dist.sample()

            return action.item(), probs[0, action.item()].item(), val.item()

    def learn(self):
        if len(self.memory.states_j) == 0: return
        for _ in range(3):
            sja, sma, aa, opa, va, ra, da, ma, batches = self.memory.generate_batches()
            vals = va;
            adv = np.zeros(len(ra), dtype=np.float32)
            for t in range(len(ra) - 1):
                delta = ra[t] - vals[t] + (0 if da[t] else self.gamma * vals[t + 1])
                adv[t] = delta

            adv_t = torch.tensor(adv).to(self.device)
            sja_t = torch.tensor(sja, dtype=torch.float32).to(self.device)
            sma_t = torch.tensor(sma, dtype=torch.float32).to(self.device)
            aa_t = torch.tensor(aa).to(self.device)
            ma_t = torch.tensor(ma).to(self.device)
            opa_t = torch.tensor(opa).to(self.device)

            logits, new_vals = self.policy(sja_t, sma_t)
            logits = logits.masked_fill(~ma_t, float('-inf'))
            dist = Categorical(logits=logits)
            new_log_probs = dist.log_prob(aa_t)
            old_log_probs = torch.log(opa_t + 1e-10)

            ratio = (new_log_probs - old_log_probs).exp()
            surr1 = ratio * adv_t
            surr2 = torch.clamp(ratio, 0.8, 1.2) * adv_t

            loss = -torch.min(surr1, surr2).mean() + 0.5 * (
                        new_vals.squeeze() - torch.tensor(vals).to(self.device)).pow(2).mean()

            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.policy.parameters(), 0.5)
            self.optimizer.step()
        self.memory.clear_memory()

    def run(self, track_history=True, **kwargs):
        start_time = time.time()

        # 1. MWKR 保底
        mwkr_solver = MWKRSolver(self.problem)
        res = mwkr_solver.run()
        best_score = res['best_score']
        best_solution = res['best_solution']

        history = []

        # 2. PPO 训练
        train_eps = int(self.episodes * 0.7)
        for ep in range(train_eps):
            ptrs = [0] * self.num_jobs;
            j_ready = [0] * self.num_jobs;
            m_ready = [0] * self.num_machines

            # === 修复点：记录 sequence 确保甘特图有数据 ===
            seq = []

            while not self._is_terminal(ptrs):
                sj, sm, mask = self._build_tensors(ptrs, j_ready, m_ready)
                action, prob, val = self.choose_action(sj, sm, mask)

                seq.append(action)  # 记录步骤

                op_idx = ptrs[action]
                task = self.problem.jobs[action].tasks[op_idx]
                m_id = task.machine_id
                start = max(m_ready[m_id], j_ready[action])
                end = start + task.duration
                gap = start - m_ready[m_id]

                ptrs[action] += 1
                j_ready[action] = end
                m_ready[m_id] = end

                # Reward
                r_prio = self.norm_priorities[action].item() * 8.0
                r_gap = -0.15 * gap
                reward = r_prio + r_gap

                done = self._is_terminal(ptrs)
                self.memory.store_memory(sj.cpu().numpy(), sm.cpu().numpy(), action, prob, val, reward, done,
                                         mask.cpu().numpy())

            self.learn()

            current_score = max(m_ready)

            # 更新全局最优
            if current_score < best_score:
                best_score = current_score
                # === 修复点：正确保存最优解 ===
                best_solution = seq[:]

                # === 改回记录 Best Score ===
            if track_history: history.append(int(best_score))

        # 3. 采样冲刺
        candidates = []
        for _ in range(30):
            ptrs = [0] * self.num_jobs;
            j_ready = [0] * self.num_jobs;
            m_ready = [0] * self.num_machines;
            seq = []
            while not self._is_terminal(ptrs):
                sj, sm, mask = self._build_tensors(ptrs, j_ready, m_ready)
                action, _, _ = self.choose_action(sj, sm, mask, deterministic=False)
                op_idx = ptrs[action]
                task = self.problem.jobs[action].tasks[op_idx]
                m_id = task.machine_id
                end = max(m_ready[m_id], j_ready[action]) + task.duration
                ptrs[action] += 1;
                j_ready[action] = end;
                m_ready[m_id] = end
                seq.append(action)
            candidates.append((max(m_ready), seq))

        candidates.sort(key=lambda x: x[0])

        if candidates[0][0] < best_score:
            best_score = candidates[0][0]
            best_solution = candidates[0][1]
            if track_history: history.append(int(best_score))

        # 4. 微调
        if best_solution:
            best_solution, best_score = apply_local_search(self.problem, best_solution)
            if track_history: history.append(int(best_score))

        return {
            "algorithm": "PPO (Priority+Hybrid)",
            "best_score": int(best_score),
            "best_solution": [int(x) for x in best_solution] if best_solution else [],
            "runtime_sec": float(round(time.time() - start_time, 4)),
            "history": [int(x) for x in history],
            "gantt_data": self.problem.get_schedule(best_solution)
        }