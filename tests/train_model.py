import copy
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.patches as mpatches  # 【NEW】为图例导入
from matplotlib.patches import Patch  # 【NEW】为图例导入

# 确保 metaforge 和 jobshop 在 Python 路径中
from metaforge.problems.benchmark_loader import load_job_shop_instance
from metaforge.problems.jobshop import  Job, Task, JobShopProblem
# 从您的 dqn_solver.py 文件导入 (请确保您使用的是 v7.4 或更高版本)
from metaforge.solvers.dqn_dyn import DQNAgentSolverReplayDynamic

# --- 配置区 ---
MODEL_SAVE_PATH = Path("./best_stochastic_dqn_model.pth")
HISTORY_PLOT_PATH = Path("./dqn_stochastic_training_history.png")
EVAL_GANTT_CHART_PATH = Path("./dqn_evaluation_gantt_chart.png")


# --- 绘图函数区 ---

def plot_training_convergence(history, save_path):
    """根据训练历史绘制收敛曲线，并保存到文件。"""
    if not history or len(history) < 2: return
    print(f"\n📈 正在生成训练过程收敛图...")
    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(12, 6))
    plt.plot(history, marker='o', linestyle='-', color='tab:blue', label="DQN 训练过程", alpha=0.8,
             markevery=max(len(history) // 25, 1))
    min_makespan = min(h for h in history if h != float('inf'))
    min_episode = history.index(min_makespan)
    plt.scatter(min_episode, min_makespan, color='red', s=60, zorder=5, label=f'历史最低点: {min_makespan:.2f}')
    plt.title("DQN 训练收敛曲线 (随机动态环境)", fontsize=16)
    plt.xlabel("训练回合 (Episode)", fontsize=12)
    plt.ylabel("最佳 Makespan", fontsize=12)
    plt.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    print(f"✅ 训练曲线图已成功保存至: {save_path}")
    plt.close()


# === 【核心】直接复用您强大的绘图函数 ===
def plot_enhanced_dynamic_gantt(schedule, problem, initial_num_jobs, save_path, figsize=(20, 8)):
    """
    【适配版】绘制功能完备的Gantt图，并适配新版求解器的输出。
    """
    if not schedule:
        print("⚠️ 警告: 调度方案为空，无法绘制Gantt图。")
        return

    print(f"\n📊 正在为评估结果生成增强版甘特图...")

    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    colors = plt.cm.get_cmap('tab20', 20)
    fig, ax = plt.subplots(1, 1, figsize=figsize)

    # --- 1. 绘制工序条形图 ---
    all_job_ids = {op['job'] for op in schedule}
    final_num_jobs = len(all_job_ids)

    for op in schedule:
        job, start, end = op["job"], op["start"], op["end"]
        machine, op_idx = op["machine"], op["operation"]

        color = colors(job % 20)
        bar_style = {'color': color, 'edgecolor': 'black', 'alpha': 0.8}

        # 标记新到达的工件 (hatch)
        if job >= initial_num_jobs:
            bar_style.update({'hatch': '///'})

        ax.barh(machine, end - start, left=start, **bar_style)
        ax.text(start + (end - start) / 2, machine, f"J{job}-O{op_idx}",
                va='center', ha='center', color='white', fontsize=8, fontweight='bold')

    # --- 2. 绘制交付日期和延误 ---
    job_completion_times = {job_id: max(op['end'] for op in schedule if op['job'] == job_id) for job_id in all_job_ids}

    # 构建一个包含所有工件（初始+动态）的映射，用于查找 due_date
    jobs_map = {job.id: job for job in problem.jobs}

    # 2.1 绘制交付日期虚线和标签
    for job_id, job_obj in jobs_map.items():
        if hasattr(job_obj, 'due_date'):
            due_date = job_obj.due_date
            ax.axvline(x=due_date, color='r', linestyle='--', linewidth=1.2, alpha=0.9)
            y_pos = ax.get_ylim()[1]
            ax.text(due_date, y_pos, f" J{job_id} Due", color='red', rotation=90, va='top', fontsize=9)

    # 2.2 绘制延误条块
    for job_id, completion_time in job_completion_times.items():
        if job_id in jobs_map:
            due_date = jobs_map[job_id].due_date
            if completion_time > due_date:
                last_op_machine = [op['machine'] for op in reversed(schedule) if op['job'] == job_id][0]
                ax.barh(last_op_machine, completion_time - due_date, left=due_date, color='red', edgecolor='black',
                        alpha=0.7)
                ax.text(due_date + (completion_time - due_date) / 2, last_op_machine, f"J{job_id} Tardy",
                        va='center', ha='center', color='white', fontsize=8, fontweight='bold')

    # --- 3. 设置坐标轴和标题 ---
    makespan = max(op['end'] for op in schedule) if schedule else 0
    ax.set_title(f'DQN 评估调度方案甘特图 (完工时间: {makespan:.2f})', fontsize=16)
    ax.set_ylabel("机器", fontsize=12)
    ax.set_xlabel("时间", fontsize=12)
    ax.set_yticks(range(problem.num_machines))
    ax.set_yticklabels([f"M{i}" for i in range(problem.num_machines)])
    ax.grid(True, axis='x', linestyle=':', alpha=0.6)

    # --- 4. 设置图例 ---
    legend_handles = []
    # 为初始工件创建图例
    for j in range(initial_num_jobs):
        if j in all_job_ids:
            legend_handles.append(Patch(color=colors(j % 20), label=f"工件 {j} (初始)"))
    # 为新工件创建图例
    for j in range(initial_num_jobs, max(all_job_ids) + 1):
        if j in all_job_ids:
            legend_handles.append(
                Patch(facecolor=colors(j % 20), edgecolor='black', hatch='///', label=f"工件 {j} (新)"))

    legend_handles.extend([
        Patch(color='red', alpha=0.7, label='延误 (Tardiness)'),
        plt.Line2D([0], [0], color='r', linestyle='--', label='交付日期 (Due Date)')
    ])
    fig.legend(handles=legend_handles, loc='upper right', bbox_to_anchor=(1.0, 0.98), ncol=1, fontsize='small')

    plt.tight_layout(rect=[0, 0, 0.88, 0.96])  # 调整布局为图例留出空间
    plt.savefig(save_path, dpi=300)
    print(f"✅ 增强版甘特图已成功保存至: {save_path}")



# --- 主函数区 ---

def main():
    # ... (加载文件和设置初始工件部分与 v2 相同) ...
    try:
        project_root_dir = Path(__file__).resolve().parent.parent
        file_path = project_root_dir / "data" / "benchmarks" / "ft06.txt"
        problem_template = load_job_shop_instance(str(file_path), format="orlib")
        initial_jobs_from_file = problem_template.jobs
    except (FileNotFoundError, IndexError):  # 捕获可能的路径错误
        print("警告: Benchmark 文件 'ft06.txt' 未找到或路径配置错误。将使用内置问题。")
        task1 = Job([Task(0, 10), Task(1, 15)], id=0);
        task2 = Job([Task(1, 20), Task(0, 10)], id=1)
        initial_jobs_from_file = [task1, task2]

    for job in initial_jobs_from_file:
        job.arrival_time = 0
        total_processing_time = sum(task.duration for task in job.tasks)
        job.due_date = job.arrival_time + total_processing_time * 5.0
        job.job_type = job.id % 3

    initial_num_jobs = len(initial_jobs_from_file)

    # --- 2. 定义随机动态环境的统计参数 ---
    stochastic_params = {'job_arrival_rate': 0.005, 'mtbf': 100, 'mttr': 15}
    problem = JobShopProblem(jobs=copy.deepcopy(initial_jobs_from_file))

    print("\n--- 问题设置 (训练) ---\n" + f"初始工件数: {len(problem.jobs)}\n" +
          f"机器数量: {problem.num_machines}\n" + f"动态环境参数: {stochastic_params}\n" + "------------------------\n")

    # --- 3. 实例化求解器并开始训练 ---
    print("🚀 开始训练 DQN 智能体...")
    solver = DQNAgentSolverReplayDynamic(problem, **stochastic_params, episodes=1000, lr=1e-4)
    results = solver.run(track_history=True)

    # --- 4. 保存模型和训练历史 ---
    print("\n--- 训练完成 ---\n" + f"训练中找到的最佳 Makespan: {results.get('makespan', float('inf')):.2f}")
    solver.save_model(MODEL_SAVE_PATH)
    if results.get('history'):
        plot_training_convergence(history=results.get('history'), save_path=HISTORY_PLOT_PATH)

    # --- 5. 加载已训练的模型并进行评估 ---
    print("\n🔍 开始评估已保存的最佳模型...")
    eval_problem = JobShopProblem(jobs=copy.deepcopy(initial_jobs_from_file))
    eval_agent = DQNAgentSolverReplayDynamic(eval_problem, **stochastic_params)
    eval_agent.load_model(MODEL_SAVE_PATH)
    eval_results = eval_agent.run(evaluation_mode=True)

    # --- 6. 【核心适配】调用新的绘图函数 ---
    print("\n--- 评估结果 ---")
    eval_makespan = eval_results.get('makespan', float('inf'))
    eval_schedule = eval_results.get('solution')

    if eval_schedule:
        print(f"评估运行的最终 Makespan: {eval_makespan:.2f}")
        # 在调用绘图函数之前，确保 problem 对象包含了评估过程中动态到达的所有工件
        # `eval_agent.problem` 就是我们需要的包含了所有工件的 problem 对象
        plot_enhanced_dynamic_gantt(
            schedule=eval_schedule,
            problem=eval_agent.problem,  # <-- 传递包含了所有工件的 problem 对象
            initial_num_jobs=initial_num_jobs,
            save_path=EVAL_GANTT_CHART_PATH
        )
    else:
        print("评估运行时未能找到有效的调度方案。")

    print(f"\n✅ 脚本执行完毕。")


if __name__ == "__main__":
    main()