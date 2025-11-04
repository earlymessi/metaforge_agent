import copy
import random
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt  # 确保导入 matplotlib

# 确保 metaforge 和 jobshop 在 Python 路径中
from metaforge.problems.benchmark_loader import load_job_shop_instance
from metaforge.problems.jobshop import Job, Task, JobShopProblem
from metaforge.solvers.dqn_dyn import DQNAgentSolverReplayDynamic
from train_model import plot_enhanced_dynamic_gantt

# --- 配置区 ---
# 指定要加载的、已经训练好的模型文件路径
MODEL_LOAD_PATH = Path("./best_stochastic_dqn_model.pth")
# 指定测试结果甘特图的保存路径
TEST_GANTT_CHART_PATH = Path("./dqn_test_result_gantt_chart.png")
# 【核心】设置一个固定的随机种子，以保证测试的可复现性
RANDOM_SEED = 42


def main():
    # --- 1. 检查模型文件是否存在 ---
    if not MODEL_LOAD_PATH.is_file():
        print(f"💥 错误: 模型文件 '{MODEL_LOAD_PATH}' 未找到。")
        print("   请先运行 'main_train_v3.py' 来训练并保存一个模型。")
        return

    # --- 2. 设置随机种子 ---
    # 这将确保每次运行测试脚本时，生成的“随机”动态事件都是一样的
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    # 如果使用GPU，也为PyTorch设置种子
    # torch.manual_seed(RANDOM_SEED)

    print(f"🌱 随机种子已设置为 {RANDOM_SEED}，以确保测试的可复现性。")

    # --- 3. 加载一个全新的问题实例作为测试基础 ---
    print(f"\n--- 准备测试环境，加载新问题... ---")
    try:
        project_root_dir = Path(__file__).resolve().parent.parent
        # 您可以在这里切换不同的 benchmark 文件进行测试
        file_path = project_root_dir / "data" / "benchmarks" / "ft06.txt"
        problem_template = load_job_shop_instance(str(file_path), format="orlib")
        initial_jobs_from_file = problem_template.jobs
        print(f"✅ 从 '{file_path.name}' 加载了 {len(initial_jobs_from_file)} 个初始工件。")
    except (FileNotFoundError, IndexError) as e:
        print(f"💥 错误: 无法加载 benchmark 文件 '{file_path}'。错误: {e}")
        return

    initial_num_jobs = len(initial_jobs_from_file)

    # 为初始工件设置属性
    for job in initial_jobs_from_file:
        job.arrival_time = 0
        total_processing_time = sum(task.duration for task in job.tasks)
        # 使用与训练时相同的宽松系数，以公平评估
        job.due_date = job.arrival_time + total_processing_time * 4.5
        job.job_type = job.id % 3

    # --- 4. 定义用于测试的动态环境统计参数 ---
    # 这些参数应该与训练时使用的参数保持一致，以模拟模型所适应的环境
    stochastic_params = {
        'job_arrival_rate': 0.025,
        'mtbf': 100,
        'mttr': 15
    }

    # --- 5. 实例化最终的测试问题对象 ---
    test_problem = JobShopProblem(jobs=copy.deepcopy(initial_jobs_from_file))

    print("\n--- 问题设置 (测试) ---")
    print(f"测试基准: {file_path.name}")
    print(f"初始工件数: {initial_num_jobs}")
    print(f"动态环境参数 (用于生成固定场景): {stochastic_params}")
    print("-----------------------\n")

    # --- 6. 实例化求解器并加载预训练模型 ---
    print(f"🚀 加载预训练模型 '{MODEL_LOAD_PATH}'...")
    solver = DQNAgentSolverReplayDynamic(
        test_problem,
        # 传入与训练时相同的统计学参数
        **stochastic_params
    )
    solver.load_model(MODEL_LOAD_PATH)

    # --- 7. 以评估模式运行求解器 ---
    print("   模型已加载。开始在生成的固定动态场景下进行评估...")
    results = solver.run(evaluation_mode=True)

    # --- 8. 打印测试结果并调用绘图函数 ---
    print("\n--- 测试完成 ---")
    makespan = results.get('makespan')
    schedule = results.get('solution')

    if makespan is not None and schedule:
        print(f"✅ 测试完成！")
        print(f"   最终 Makespan: {makespan:.2f}")

        # solver.problem.jobs 中现在包含了所有在测试中动态生成的工件
        final_num_jobs = len(solver.problem.jobs)
        print(f"   初始工件数: {initial_num_jobs}")
        print(f"   动态插入工件数: {final_num_jobs - initial_num_jobs}")

        # 调用高级绘图函数，它会创建图形并将其保存到文件
        plot_enhanced_dynamic_gantt(
            schedule=schedule,
            problem=solver.problem,  # 传递包含了所有工件的 problem 对象
            initial_num_jobs=initial_num_jobs,
            save_path=TEST_GANTT_CHART_PATH
        )

        # >>> 新增改动 <<<
        # 在保存后，调用 plt.show() 将其弹窗显示
        print(f"   甘特图已保存至 '{TEST_GANTT_CHART_PATH}'，现在弹窗显示...")
        plt.show()

    else:
        print("❌ 测试未能得到有效的结果，无法生成甘特图。")

    print(f"\n✅ 测试脚本执行完毕。")


if __name__ == "__main__":
    main()