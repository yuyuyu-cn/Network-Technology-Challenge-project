import os
import sys
import time
import subprocess
import importlib

# ==========================================
# 终端颜色输出配置
# ==========================================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_info(msg): print(f"{Colors.BLUE}[INFO]{Colors.ENDC} {msg}")
def print_success(msg): print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} {msg}")
def print_error(msg): print(f"\n{Colors.RED}{Colors.BOLD}❌ [ERROR] {msg}{Colors.ENDC}")

# ==========================================
# 1. 环境依赖自检
# ==========================================
def check_dependencies():
    print_info("正在检查 Python 依赖库...")
    required_packages = {'networkx': 'networkx', 'matplotlib': 'matplotlib', 'numpy': 'numpy', 'torch': 'torch'}
    missing = []
    for module_name, pip_name in required_packages.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(pip_name)
            
    if missing:
        print_error("缺少必要的 Python 库！")
        print(f"请运行: pip install {' '.join(missing)}\n")
        sys.exit(1)
    print_success("所有核心依赖包检查通过！")

# ==========================================
# 2. 检查脚本文件完整性
# ==========================================
scripts_to_run = [
    ("algo_hypatia.py", "Hypatia (全局最短路快照)"),
    ("algo_lsr.py", "LSR (局部状态路由)"),
    ("algo_madrl.py", "MA-DRL (多智能体深度强化学习)"),
    ("algo_ftrl.py", "FTRL (双路径在线优化)"),
    ("algo_dtn_cgr.py", "DTN-CGR (接触图容忍路由)"),
]
plot_script = "plot_results.py"

def check_files():
    print_info("正在检查脚本文件完整性...")
    missing_files = [f for f, _ in scripts_to_run + [(plot_script, "画图脚本")] if not os.path.exists(f)]
    if missing_files:
        print_error("找不到以下脚本文件：")
        for f in missing_files: print(f"  - {f}")
        sys.exit(1)
    print_success("所有算法文件准备就绪！")

# ==========================================
# 3. 执行脚本并捕获错误 (注入 UTF-8 环境变量环境)
# ==========================================
def run_script(script_name, description):
    print(f"\n{Colors.HEADER}{Colors.BOLD}>>> 正在运行: {description} ({script_name}){Colors.ENDC}")
    start_time = time.time()
    
    # 【核心修复点】：强制告诉 Python 的子进程，不管是输入还是输出，全部用 UTF-8 编码！
    # 这样就算脚本里有 ✅、🧠、🚀 这种 Emoji，也不会报 GBK 错误了。
    my_env = os.environ.copy()
    my_env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=my_env  # 注入强效抗乱码环境
        )
        
        elapsed = time.time() - start_time
        print(result.stdout.strip())
        print_success(f"{script_name} 运行完毕，耗时 {elapsed:.2f} 秒。")
        
    except subprocess.CalledProcessError as e:
        print_error(f"脚本 '{script_name}' 运行崩溃！")
        print(f"{Colors.RED}-------------------- 错误详情 --------------------{Colors.ENDC}")
        if e.stdout: print(f"{Colors.YELLOW}--- 标准输出 ---{Colors.ENDC}\n{e.stdout}")
        print(f"{Colors.RED}--- 报错日志 (Traceback) ---{Colors.ENDC}\n{e.stderr}")
        print(f"{Colors.RED}--------------------------------------------------{Colors.ENDC}")
        sys.exit(1)

# ==========================================
# 主流程
# ==========================================
def main():
    print(f"\n{Colors.BOLD}===================================================={Colors.ENDC}")
    print(f"{Colors.BOLD}🚀 卫星网络路由算法对比自动化仿真平台{Colors.ENDC}")
    print(f"{Colors.BOLD}===================================================={Colors.ENDC}\n")
    
    check_dependencies()
    check_files()
    if not os.path.exists("results"): os.makedirs("results")
        
    for script_file, desc in scripts_to_run:
        run_script(script_file, desc)
        
    run_script(plot_script, "汇总数据与生成对比图表")
    print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 恭喜！所有实验均成功完成！请查看弹出的对比图表。{Colors.ENDC}\n")

if __name__ == "__main__":
    main()