import random
from pathlib import Path


def generate_jssp_instance_file(num_jobs, num_machines, duration_range=(1, 10), output_path=None):
    """
    生成一个 JSSP 实例并将其保存为 .txt 文件。
    """
    if output_path is None:
        raise ValueError("必须提供输出路径!")

    lines = []
    # 第一行是规模：工件数 机器数
    lines.append(f"{num_jobs} {num_machines}")

    machine_list = list(range(num_machines))

    for _ in range(num_jobs):
        job_line_parts = []
        # 为每个工件生成随机的机器顺序
        random.shuffle(machine_list)

        for machine_id in machine_list:
            duration = random.randint(*duration_range)
            # 格式：机器ID 加工时间
            job_line_parts.append(str(machine_id))
            job_line_parts.append(str(duration))

        lines.append(" ".join(job_line_parts))

    # 将内容写入文件
    with open(output_path, 'w') as f:
        f.write("\n".join(lines))
    # print(f"已生成文件: {output_path}")


# --- 主程序 ---
if __name__ == "__main__":
    # 定义生成参数
    NUM_FILES_TO_GENERATE = 100  # 我们要生成100个训练文件
    NUM_JOBS = 6
    NUM_MACHINES = 6

    # 创建一个目录来存放这些数据
    output_dir = Path("./training_data_6x6")
    output_dir.mkdir(exist_ok=True)

    print(f"正在生成 {NUM_FILES_TO_GENERATE} 个训练数据文件到 '{output_dir}' 目录...")

    for i in range(NUM_FILES_TO_GENERATE):
        file_path = output_dir / f"instance_{i + 1:03d}.txt"
        generate_jssp_instance_file(NUM_JOBS, NUM_MACHINES, output_path=file_path)

    print("✅ 数据文件生成完成！")