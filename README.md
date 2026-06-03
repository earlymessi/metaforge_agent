# 🔧 MetaForge

MetaForge is a modular Python toolkit for solving **Job Shop Scheduling Problems (JSSP)** using classic **metaheuristics** and modern **reinforcement learning** methods.

🚀 From Tabu Search and Genetic Algorithms to Deep Q-Networks (DQN) and Neuroevolution — MetaForge brings together the best of optimization and AI in one clean, extensible framework.

---

## 🏭 MES 排产系统（本仓库交付形态）

本仓库除算法库外，还提供 **FastAPI + MongoDB + Vue3** 的车间排产 Web 应用：

- **运行手册**：见 [`star.md`](star.md)（MongoDB 启动、后端、前端构建）
- **新前端**：构建后访问 **`http://127.0.0.1:8008/new-ui/`**（唯一端口，见 `scripts/restart_backend.ps1`）（根路径 `/` 亦可）
- **改进路线图**：见 [`docs/改进计划.md`](docs/改进计划.md)
- **多智能体**：见 [`docs/智能体功能清单.md`](docs/智能体功能清单.md)（六大 Agent 主参考）、[`docs/多智能体开发进度.md`](docs/多智能体开发进度.md)、[`docs/README.md`](docs/README.md)

快速启动（Windows PowerShell）：

```powershell
Start-Service MongoDB
pip install -e .
cd frontend; npm install; npm run build; cd ..
cd tests; python main.py
```

---

## 🎯 Key Features

- ✅ Solve classic benchmark problems (OR-Library, JSON)
- 🧠 Built-in solvers:
  - Tabu Search (TS)
  - Simulated Annealing (SA)
  - Genetic Algorithm (GA)
  - Ant Colony Optimization (ACO)
  - Q-Learning
  - DQN (with and without replay buffer)
  - Neuroevolution
- 📊 Beautiful convergence and Gantt chart visualizations
- 🤖 Reinforcement Learning support out-of-the-box
- 🧪 Designed for research, education, and real-world production scheduling

---

## 📦 Installation

From PyPI:

```bash
pip install metaforge
```

From GitHub (latest):

```bash
pip install git+https://github.com/Mageed-Ghaleb/MetaForge.git
```

---

## 📁 Quick Start

```python
from metaforge.problems.benchmark_loader import load_job_shop_instance
from metaforge.metaforge_runner import run_solver

# Load a benchmark from URL
url = "https://raw.githubusercontent.com/Mageed-Ghaleb/MetaForge/main/data/benchmarks/ft06.txt"
problem = load_job_shop_instance(url)

# Run a solver
result = run_solver("ts", problem)

# View makespan
print("Best Makespan:", result["makespan"])
```

---

## 📊 Visualizations

```python
from metaforge.utils.visualization import plot_gantt_chart
schedule = result["schedules"][-1]
plot_gantt_chart(schedule, num_machines=problem.num_machines, num_jobs=len(problem.jobs))
```

---

## 📓 Notebooks

| Name | Description | Launch |
|------|-------------|--------|
| MetaForge_Quick_Start.ipynb | Light demo: install, run, visualize | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Mageed-Ghaleb/MetaForge/blob/main/notebooks/MetaForge_Quick_Start.ipynb) |
| MetaForge_Complete_Testing.ipynb | Full testing suite across all solvers | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Mageed-Ghaleb/MetaForge/blob/main/notebooks/MetaForge_Complete_Testing.ipynb) |

---

## 📚 Documentation

- 📖 [Usage Guide](https://github.com/Mageed-Ghaleb/MetaForge/blob/main/docs/usage.md)
- 🧠 [Solvers Overview](https://github.com/Mageed-Ghaleb/MetaForge/blob/main/docs/solvers.md)
- 🧠 [Solvers In Details](https://github.com/Mageed-Ghaleb/MetaForge/tree/main/docs/solvers)
- 📂 [Benchmark Format](https://github.com/Mageed-Ghaleb/MetaForge/blob/main/docs/datasets.md)

---

## 🧠 Why MetaForge?

Most libraries focus on one type of solver. MetaForge unifies traditional algorithms and deep reinforcement learning into one clean package. Whether you’re teaching, publishing, or scheduling in a factory — MetaForge is your launchpad. 🚀

---

## 🔧 Benchmarks Supported

- FT06, FT10, FT20 (OR-Library)
- LA01–LA05
- JSON format coming soon

---

## 📈 Contributing

We're just getting started! Feel free to:

- Suggest solvers or enhancements
- Fork and extend
- Submit PRs — code, docs, notebooks, anything

---

## 📄 License

MIT License — free for academic and commercial use.

---

## 👨‍💻 Author

**Mageed Ghaleb**  
📧 mageed.ghaleb@gmail.com  
🔗 [LinkedIn](https://www.linkedin.com/in/mageed-ghaleb/)  
🔗 [GitHub](https://github.com/mageed-ghaleb)

---

> Built with ❤️ for solvers, schedules, and scientific curiosity.

---

## 🔎 Keywords (for discoverability)

MetaForge is designed for:

- Job Shop Scheduling Problems (JSSP)
- Metaheuristics (Tabu Search, Genetic Algorithm, ACO, SA)
- Reinforcement Learning in Scheduling (Q-Learning, DQN)
- Production Scheduling Optimization
- Flexible Flowshops & Real-world Scheduling
- Benchmark Comparisons and Solver Visualization
