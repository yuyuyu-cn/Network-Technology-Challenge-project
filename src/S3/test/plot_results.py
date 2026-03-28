import json, os, matplotlib.pyplot as plt, numpy as np

def generate_comparison_plots():
    data_list = []
    folder = "results"
    
    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            with open(os.path.join(folder, filename), "r") as f:
                data_list.append(json.load(f))
                
    order = {"Hypatia": 0, "LSR": 1, "MA-DRL": 2, "FTRL": 3, "DTN-CGR": 4}
    data_list.sort(key=lambda x: order.get(x["Algo"], 99))

    algorithms = [d["Algo"] for d in data_list]
    metrics = ["PDR (%)", "Avg Delay", "Overhead", "Compute Time (ms)"]

    values = {m: [] for m in metrics}
    for d in data_list:
        for m in metrics: values[m].append(d[m])

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Performance Comparison of 5 Satellite Routing Algorithms', fontsize=18, fontweight='bold', y=0.96)

    colors = ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F']

    for i, ax in enumerate(axs.flat):
        metric = metrics[i]
        x_pos = np.arange(len(algorithms))
        
        bars = ax.bar(x_pos, values[metric], color=colors[:len(algorithms)], edgecolor='#333333', linewidth=1.2, width=0.6, alpha=0.85)
        
        ax.set_title(metric, fontsize=14, fontweight='bold', pad=10)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(algorithms, fontsize=11, rotation=15)
        
        if metric == "Overhead":
            ax.set_yscale('log')
            ax.set_ylabel("Messages (Log Scale)", fontsize=11)
        else:
            ax.set_ylabel("Value", fontsize=11)

        for bar in bars:
            yval = bar.get_height()
            offset = yval * 0.05 if metric != "Overhead" else yval * 0.1
            label = f"{int(yval)}" if yval > 1000 else f"{yval:.2f}"
            ax.text(bar.get_x() + bar.get_width()/2, yval + offset, label, ha='center', va='bottom', fontsize=10, fontweight='bold')

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    plt.tight_layout(rect=[0, 0.03, 1, 0.92])
    plt.savefig("routing_comparison_plot.png", dpi=300)
    print("✅ 性能对比图已生成并保存为 'routing_comparison_plot.png'")
    plt.show()

if __name__ == "__main__": generate_comparison_plots()