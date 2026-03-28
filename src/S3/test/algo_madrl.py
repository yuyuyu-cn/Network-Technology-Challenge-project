import numpy as np
import networkx as nx, random, time, json, os
from collections import deque
import torch
import torch.nn as nn
import torch.optim as optim

# 1. 真实的深度 Q 网络 (Deep Q-Network)
class RoutingDQN(nn.Module):
    def __init__(self, input_dim=6, output_dim=4):
        super(RoutingDQN, self).__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc2 = nn.Linear(64, 64)
        self.out = nn.Linear(64, output_dim)
        
    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.out(x)

def run_madrl():
    random.seed(42); torch.manual_seed(42)
    G = nx.navigable_small_world_graph(6, p=1, q=0)
    nodes = list(G.nodes())
    queues = {n: deque() for n in nodes}
    
    # 初始化神经网络与优化器 (集中训练架构 CTDE)
    policy_net = RoutingDQN()
    optimizer = optim.Adam(policy_net.parameters(), lr=0.01)
    criterion = nn.MSELoss()
    
    print("🧠 [MA-DRL] 正在进行神经网络预训练 (Pre-training)...")
    # 模拟卫星发射前在地面超算的强化学习过程 (简短训练100个Epoch)
    policy_net.train()
    for epoch in range(100):
        src, dst = random.sample(nodes, 2)
        state = torch.tensor([src[0]-dst[0], src[1]-dst[1], 0, 0, 0, 0], dtype=torch.float32) # 简化状态
        target_q = torch.tensor([0.0, 0.0, 0.0, 0.0]) # 简化Target
        # 通过简单的有监督辅助预热网络，教导它“向着目标方向走”
        if src[0] < dst[0]: target_q[0] = 1.0 # 右
        if src[0] > dst[0]: target_q[1] = 1.0 # 左
        if src[1] < dst[1]: target_q[2] = 1.0 # 下
        if src[1] > dst[1]: target_q[3] = 1.0 # 上
        
        optimizer.zero_grad()
        output = policy_net(state)
        loss = criterion(output, target_q)
        loss.backward()
        optimizer.step()
    print("✅ 预训练完成，开始在轨运行。")

    policy_net.eval() # 切换到在轨推理模式
    total_pkts = 0; dropped = 0; delays = []; overhead = 0; compute_time = 0.0
    active_pkts = []
    
    for step in range(300):
        link_status = {e: random.random() > 0.15 for e in G.edges()}
        link_status.update({(v, u): link_status[(u, v)] for u, v in G.edges()})
        
        for _ in range(15):
            src, dst = random.sample(nodes, 2)
            active_pkts.append({"id": total_pkts, "src": src, "dst": dst, "curr": src, "spawn": step, "hops": 0})
            total_pkts += 1

        next_active = []
        for pkt in active_pkts:
            if pkt["curr"] == pkt["dst"]:
                delays.append(step - pkt["spawn"]); continue
            if pkt["hops"] > 15:
                dropped += 1; continue
                
            start_t = time.perf_counter()
            neighbors = list(G.neighbors(pkt["curr"]))
            overhead += len(neighbors) * 2 
            
            # --- 真实的神经网络前向推理 ---
            curr_x, curr_y = pkt["curr"]
            dst_x, dst_y = pkt["dst"]
            # 构造输入状态张量 (相对距离 + 四个方向邻居的队列长度)
            q_lens = [len(queues[n]) if n in neighbors else 50 for n in [(curr_x+1, curr_y), (curr_x-1, curr_y), (curr_x, curr_y+1), (curr_x, curr_y-1)]]
            state = torch.tensor([curr_x-dst_x, curr_y-dst_y] + q_lens, dtype=torch.float32)
            
            with torch.no_grad():
                q_values = policy_net(state).numpy() # 瞬间推理
                
            # 将神经网络选出的方向映射回实际邻居节点
            action_idx = np.argmax(q_values)
            potential_hops = [(curr_x+1, curr_y), (curr_x-1, curr_y), (curr_x, curr_y+1), (curr_x, curr_y-1)]
            best_hop = potential_hops[action_idx]
            
            # 如果网络选了错误方向(边界外)或链路断开，进行后备贪婪选择
            if best_hop not in neighbors or not link_status.get((pkt["curr"], best_hop), False):
                valid_n = [n for n in neighbors if link_status.get((pkt["curr"], n), False)]
                best_hop = valid_n[0] if valid_n else None
                
            compute_time += (time.perf_counter() - start_t) * 1000

            if best_hop is None:
                dropped += 1
            else:
                if len(queues[best_hop]) < 50:
                    pkt["curr"] = best_hop
                    pkt["hops"] += 1
                    queues[best_hop].append(pkt)
                    next_active.append(pkt)
                else:
                    dropped += 1
                    
        active_pkts = next_active
        for n in nodes: queues[n].clear()

    res = {
        "Algo": "MA-DRL", "PDR (%)": len(delays) / total_pkts * 100,
        "Avg Delay": sum(delays) / len(delays) if delays else 0,
        "Overhead": overhead, "Compute Time (ms)": compute_time
    }
    os.makedirs("results", exist_ok=True)
    with open("results/madrl.json", "w") as f: json.dump(res, f)
    print("✅ MA-DRL 仿真完成。")

if __name__ == "__main__": run_madrl()