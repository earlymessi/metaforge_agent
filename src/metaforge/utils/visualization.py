import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib import animation
import seaborn as sns
import pandas as pd
import matplotlib.patches as mpatches

def plot_gantt_chart(schedule, num_machines, num_jobs, title="Job-Shop Schedule", figsize=(12, 5), save_as=None):
    colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple',
              'tab:brown', 'tab:pink', 'tab:gray', 'tab:olive', 'tab:cyan']

    fig, ax = plt.subplots(figsize=figsize)

    for op in schedule:
        machine = op["machine"]
        job = op["job"]
        op_idx = op["operation"]
        start = op["start"]
        end = op["end"]
        color = colors[job % len(colors)]

        ax.barh(machine, end - start, left=start, color=color, edgecolor='black')
        ax.text(start + (end - start) / 2, machine, f"J{job}-O{op_idx}",
                va='center', ha='center', color='white', fontsize=8, fontweight='bold')

    ax.set_yticks(range(num_machines))
    ax.set_yticklabels([f"Machine {i}" for i in range(num_machines)])
    ax.set_xlabel("Time")
    ax.set_title(title)
    ax.grid(True, axis='x')

    legend_handles = [Patch(color=colors[j % len(colors)], label=f"Job {j}") for j in range(num_jobs)]
    ax.legend(handles=legend_handles, loc="upper right")

    plt.tight_layout()

    if save_as:
        plt.savefig(save_as, dpi=300)

    plt.show()

def plot_multiple_gantt(schedules_dict, num_machines, num_jobs, figsize=(16, 5)):
    """
    Plot final Gantt charts from multiple solvers side by side.

    Args:
        schedules_dict (dict): {solver_name: schedule}, where schedule is a list of ops with keys: job, operation, machine, start, end
        num_machines (int): Total number of machines
        num_jobs (int): Total number of jobs
        figsize (tuple): Size of the figure
    """
    colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple',
              'tab:brown', 'tab:pink', 'tab:gray', 'tab:olive', 'tab:cyan']

    solver_names = list(schedules_dict.keys())
    n = len(solver_names)

    fig, axs = plt.subplots(1, n, figsize=figsize, sharey=True)

    if n == 1:
        axs = [axs]

    for idx, solver_name in enumerate(solver_names):
        schedule = schedules_dict[solver_name]
        ax = axs[idx]

        for op in schedule:
            machine = op["machine"]
            job = op["job"]
            op_idx = op["operation"]
            start = op["start"]
            end = op["end"]
            color = colors[job % len(colors)]

            ax.barh(machine, end - start, left=start, color=color, edgecolor='black')
            ax.text(start + (end - start) / 2, machine, f"J{job}-O{op_idx}",
                    va='center', ha='center', color='white', fontsize=7, fontweight='bold')

        ax.set_title(solver_name)
        ax.set_xlabel("Time")
        ax.set_yticks(range(num_machines))
        ax.set_yticklabels([f"M{i}" for i in range(num_machines)])
        ax.grid(True, axis='x')

    # Add job legend to last axis
    legend_handles = [Patch(color=colors[j % len(colors)], label=f"Job {j}") for j in range(num_jobs)]
    axs[-1].legend(handles=legend_handles, loc="upper right")

    fig.suptitle("Final Gantt Charts by Solver", fontsize=14)
    plt.tight_layout()
    plt.show()

def animate_gantt_evolution(schedule_frames, num_machines, num_jobs, interval=400, save_path=None):
    """
    Create a Gantt chart animation from a sequence of schedule frames.

    Args:
        schedule_frames (List[List[Dict]]): List of schedules (one per iteration)
        num_machines (int): Number of machines
        num_jobs (int): Number of jobs
        interval (int): Delay between frames in milliseconds
        save_path (str, optional): If provided, saves animation as .gif
    """
    colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple',
              'tab:brown', 'tab:pink', 'tab:gray', 'tab:olive', 'tab:cyan']

    fig, ax = plt.subplots(figsize=(12, 5))

    def update(frame_index):
        ax.clear()
        schedule = schedule_frames[frame_index]

        for op in schedule:
            machine = op["machine"]
            job = op["job"]
            op_idx = op["operation"]
            start = op["start"]
            end = op["end"]
            color = colors[job % len(colors)]

            ax.barh(machine, end - start, left=start, color=color, edgecolor='black')
            ax.text(start + (end - start) / 2, machine, f"J{job}-O{op_idx}",
                    va='center', ha='center', color='white', fontsize=7)

        ax.set_yticks(range(num_machines))
        ax.set_yticklabels([f"M{i}" for i in range(num_machines)])
        ax.set_title(f"Gantt Evolution - Iteration {frame_index + 1}")
        ax.set_xlabel("Time")
        ax.grid(True, axis='x')

    anim = animation.FuncAnimation(fig, update, frames=len(schedule_frames), interval=interval, repeat=False)

    if save_path:
        anim.save(save_path, writer='pillow', fps=1000 // interval)
    else:
        plt.close(fig)  # prevent duplicate static output in Jupyter
        return anim

def plot_results_from_csv(csv_path, show=True, save_path=None):
    df = pd.read_csv(csv_path)

    plt.figure(figsize=(12, 6))
    # sns.barplot(data=df, x="Solver", y="BestMakespan", hue="Benchmark")
    sns.barplot(data=df, x="solver", y="best_score", hue="benchmark")
    plt.title("Best Makespan per Solver across Benchmarks")
    plt.xticks(rotation=45)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        print(f"📊 Plot saved to {save_path}")
    if show:
        plt.show()


def plot_runtime_from_csv(csv_path, show=True, save_path=None):
    df = pd.read_csv(csv_path)

    plt.figure(figsize=(12, 6))
    # sns.barplot(data=df, x="Solver", y="RuntimeSec", hue="Benchmark")
    sns.barplot(data=df, x="solver", y="runtime_sec", hue="benchmark")
    plt.title("Runtime (seconds) per Solver across Benchmarks")
    plt.xticks(rotation=45)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        print(f"📊 Runtime plot saved to {save_path}")
    if show:
        plt.show()


def plot_enhanced_dynamic_gantt(schedules_dict, problem, dynamic_events=None, initial_num_jobs=None, figsize=(20, 6)):
    """
    绘制带有箭头注解和动态避让功能的高级动态甘特图。

    此版本使用带箭头的注解来标识延误，并实现了标签的动态避让，
    解决了多个延误在同一机器上时标签重叠的问题。图例位于图表右上角。
    """
    if not schedules_dict or all(not v for v in schedules_dict.values()):
        print("Warning: No valid schedule data provided to plot.")
        return

    colors = plt.cm.get_cmap('tab20', 20)
    solver_names = list(schedules_dict.keys())
    n = len(solver_names)
    fig, axs = plt.subplots(n, 1, figsize=(figsize[0], figsize[1] * n), sharex=True, squeeze=False)
    axs = axs.flatten()

    final_num_jobs = initial_num_jobs
    if dynamic_events and initial_num_jobs is not None:
        final_num_jobs += sum(1 for e in dynamic_events if e['type'] == 'new_job_arrival')

    for idx, solver_name in enumerate(solver_names):
        schedule = schedules_dict.get(solver_name)
        ax = axs[idx]

        if not schedule:
            ax.text(0.5, 0.5, 'No Schedule Data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(solver_name)
            continue

        # --- 1. 绘制工序条形图 ---
        for op in schedule:
            job, start, end = op["job"], op["start"], op["end"]
            color = colors(job % 20)
            bar_style = {'color': color, 'edgecolor': 'black', 'alpha': 0.8}
            if op.get('is_outsourced'):
                machine = -1
                bar_style.update({'color': 'grey', 'edgecolor': 'black', 'hatch': 'xx'})
                ax.barh(machine, end - start, left=start, **bar_style)
                ax.text(start + (end - start) / 2, machine, f"Job {job} Outsourced", va='center', ha='center',
                        color='white', fontsize=7, fontweight='bold')
                continue
            machine, op_idx = op["machine"], op["operation"]
            if op.get('is_overtime'):
                bar_style.update({'hatch': '++'})
            elif initial_num_jobs is not None and job >= initial_num_jobs:
                bar_style.update({'hatch': '///'})
            ax.barh(machine, end - start, left=start, **bar_style)
            ax.text(start + (end - start) / 2, machine, f"J{job}-O{op_idx}", va='center', ha='center', color='white',
                    fontsize=7, fontweight='bold')

        # --- 2. 绘制交付日期和延误 ---
        job_completion_times = {}
        for op in schedule:
            job_completion_times[op['job']] = max(job_completion_times.get(op['job'], 0), op['end'])

        jobs_map = {job.id: job for job in problem.initial_jobs}
        if dynamic_events:
            for event in dynamic_events:
                if event['type'] == 'new_job_arrival':
                    jobs_map[event['job'].id] = event['job']

        y_max_limit = ax.get_ylim()[1]
        for job_id, job_obj in jobs_map.items():
            if hasattr(job_obj, 'due_date'):
                due_date = job_obj.due_date
                ax.axvline(x=due_date, color='r', linestyle='--', linewidth=1.0, alpha=0.8)
                ax.text(due_date, y_max_limit, f" J{job_id} Due",
                        color='red', rotation=90, verticalalignment='top', fontsize=9)

        tardy_label_y_offsets = {}
        sorted_tardy_jobs = sorted(
            [(job_id, comp_time) for job_id, comp_time in job_completion_times.items() if
             job_id in jobs_map and comp_time > jobs_map[job_id].due_date],
            key=lambda item: jobs_map.get(item[0], {}).due_date
        )

        for job_id, completion_time in sorted_tardy_jobs:
            job_obj = jobs_map[job_id]
            due_date = job_obj.due_date
            last_op_machine = -2
            for op in reversed(schedule):
                if op['job'] == job_id and not op.get('is_outsourced'):
                    last_op_machine = op['machine']
                    break

            if last_op_machine != -2:
                ax.barh(last_op_machine, completion_time - due_date, left=due_date, color='red',
                        edgecolor='black', alpha=0.3, zorder=10)

                arrow_target_x = due_date + (completion_time - due_date) / 2
                arrow_target_y = last_op_machine
                if last_op_machine not in tardy_label_y_offsets:
                    tardy_label_y_offsets[last_op_machine] = 0.4
                else:
                    tardy_label_y_offsets[last_op_machine] += 0.38
                label_y_pos = last_op_machine + tardy_label_y_offsets[last_op_machine]

                ax.annotate(
                    f"J{job_id} Tardy",
                    xy=(arrow_target_x, arrow_target_y),
                    xytext=(due_date, label_y_pos),
                    fontsize=8,
                    fontweight='bold',
                    va='center',
                    ha='right',
                    bbox=dict(boxstyle="round,pad=0.2", fc="red", alpha=0.9),
                    arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.2", color="white")
                )

        # --- 3. 绘制动态事件 ---
        if dynamic_events:
            machine_task_counters = [0] * problem.num_machines
            sorted_schedule = sorted([op for op in schedule if not op.get('is_outsourced')], key=lambda x: x['end'])
            processed_events = set()
            for op in sorted_schedule:
                machine_id = op['machine']
                machine_task_counters[machine_id] += 1
                current_task_count = machine_task_counters[machine_id]
                for i, event in enumerate(dynamic_events):
                    if i in processed_events: continue
                    if event['type'] == 'machine_breakdown_on_nth_task':
                        trigger = event['trigger']
                        if trigger['machine'] == machine_id and trigger['task_count'] == current_task_count:
                            breakdown_start = op['end']
                            duration = event['duration']
                            ax.barh(machine_id, duration, left=breakdown_start, color='#696969', hatch='xxx',
                                    edgecolor='black')
                            ax.text(breakdown_start + duration / 2, machine_id, "Down", va='center', ha='center',
                                    color='white', fontsize=7)
                            processed_events.add(i)

        # --- 4. 设置坐标轴和标题 ---
        ax.set_title(solver_name)
        ax.set_ylabel("Machines")
        ax.set_yticks(range(-1, problem.num_machines))
        ax.set_yticklabels(["Outsourcing"] + [f"M{i}" for i in range(problem.num_machines)])
        ax.grid(True, axis='x', linestyle=':', alpha=0.6)

    # --- 5. 设置图例和最终布局 ---
    legend_handles = []
    if initial_num_jobs is not None:
        for j in range(initial_num_jobs):
            legend_handles.append(Patch(color=colors(j % 20), label=f"Job {j} (Original)"))
        if final_num_jobs > initial_num_jobs:
            for j in range(initial_num_jobs, final_num_jobs):
                legend_handles.append(
                    Patch(facecolor=colors(j % 20), edgecolor='black', hatch='///', label=f"Job {j} (New)"))
    legend_handles.extend([
        mpatches.Patch(facecolor='#A9A9A9', hatch='++', edgecolor='black', label='Overtime Task'),
        mpatches.Patch(facecolor='grey', hatch='xx', edgecolor='black', label='Outsourced Job'),
        mpatches.Patch(color='red', alpha=0.3, label='Tardiness'),
        mpatches.Patch(facecolor='#696969', hatch='xxx', edgecolor='black', label='Breakdown'),
        plt.Line2D([0], [0], color='r', linestyle='--', label='Due Date')
    ])

    # 图例右上角垂直排列
    fig.legend(handles=legend_handles, loc='upper right', bbox_to_anchor=(1.0, 0.98), ncol=1, fontsize='small')
    axs[-1].set_xlabel("Time")
    fig.suptitle("Enhanced Dynamic Gantt Chart Analysis", fontsize=16)

    # 调整布局为图例留出空间
    plt.tight_layout(rect=[0, 0, 0.85, 0.96])
    plt.show()

def plot_comprehensive_comparison(results, problem, pretty_names, dynamic_events=None, initial_num_jobs=None):
    """
    “主”绘图函数，调用增强版的Gantt图函数来生成最终的可视化结果。
    """
    print("\n" + "=" * 50)
    print("📊 Generating Comprehensive Analysis Plots...")
    print("=" * 50)
    print("--> Plotting Enhanced Dynamic Gantt Charts...")

    schedules_to_plot = {}
    for name, res in results.items():
        if res and res.get("all_schedules") and res["all_schedules"]:
            pretty_name = pretty_names.get(name, name)
            schedules_to_plot[pretty_name] = res["all_schedules"][-1]

    if schedules_to_plot:
        plot_enhanced_dynamic_gantt(
            schedules_dict=schedules_to_plot,
            problem=problem,
            dynamic_events=dynamic_events,
            initial_num_jobs=initial_num_jobs
        )
    else:
        print("    (Skipped: No valid schedules found to plot Gantt charts)")

    print("\n✅ All plots have been generated.")