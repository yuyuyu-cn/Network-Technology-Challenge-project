import networkx as nx, random, time, json, os, math
from collections import deque
import itertools  # 引入迭代工具来解决路径爆炸问题

def run_ftrl():
    random.seed(42) 
    G = nx.navigable_small_world_graph(6, p=1, q=0)
    nodes = list(G.nodes())
    queues = {n: deque() for n in nodes}
    
    total_pkts = 0; dropped = 0; delays = []; overhead = 0; compute_time = 0.0
    active_pkts = []
    
    # FTRL 核心数据结构
    ftrl_paths = {}
    cum_loss = {} # G_i: 累积损失 (Cumulative Loss)
    learning_rate = 0.5 # eta: 学习率
    
    for step in range(300):
        link_status = {e: random.random() > 0.15 for e in G.edges()}
        link_status.update({(v, u): link_status[(u, v)] for u, v in G.edges()})
        
        for _ in range(15):
            src, dst = random.sample(nodes, 2)
            if (src, dst) not in ftrl_paths:
                # 【性能修复核心】：绝不能用 list() 强转！只按需取前两条路径
                path_generator = nx.shortest_simple_paths(G, src, dst)
                first_two_paths = list(itertools.islice(path_generator, 2))
                
                p1 = first_two_paths[0]
                p2 = first_two_paths[1] if len(first_two_paths) > 1 else p1
                
                ftrl_paths[(src, dst)] = (p1, p2)
                cum_loss[(src, dst)] = [0.0, 0.0] # 初始累积损失为0
                
            active_pkts.append({"id": total_pkts, "src": src, "dst": dst, "curr": src, "spawn": step, "hops": 0, "route": []})
            total_pkts += 1

        next_active = []
        for pkt in active_pkts:
            if pkt["curr"] == pkt["dst"]:
                delays.append(step - pkt["spawn"]); continue
            if pkt["hops"] > 15:
                dropped += 1; continue
                
            start_t = time.perf_counter()
            overhead += 5 
            
            src, dst = pkt["src"], pkt["dst"]
            if not pkt["route"]:
                # --- 真实的 FTRL 数学更新过程 ---
                p1, p2 = ftrl_paths[(src, dst)]
                
                # 1. 观测当前时隙两者的 Loss (此处定义为路径总拥塞度)
                loss_1 = sum(len(queues[n]) for n in p1) / 50.0 
                loss_2 = sum(len(queues[n]) for n in p2) / 50.0
                
                # 2. 累加历史梯度 (Cumulative Gradient)
                cum_loss[(src, dst)][0] += loss_1
                cum_loss[(src, dst)][1] += loss_2
                G1, G2 = cum_loss[(src, dst)]
                
                # 3. 求解 FTRL 最优化公式: w_i = exp(-eta * G_i) / Z (指数权重更新)
                exp_1 = math.exp(-learning_rate * G1)
                exp_2 = math.exp(-learning_rate * G2)
                Z = exp_1 + exp_2 # 归一化因子
                w1 = exp_1 / Z
                w2 = exp_2 / Z
                
                # 根据算出的概率严格进行源路由多路径分配
                pkt["route"] = p1 if random.random() < w1 else p2
            
            try:
                idx = pkt["route"].index(pkt["curr"])
                next_hop = pkt["route"][idx+1]
            except:
                next_hop = None
                
            compute_time += (time.perf_counter() - start_t) * 1000

            if next_hop is None or not link_status.get((pkt["curr"], next_hop), False):
                dropped += 1
            else:
                if len(queues[next_hop]) < 50:
                    pkt["curr"] = next_hop
                    pkt["hops"] += 1
                    queues[next_hop].append(pkt)
                    next_active.append(pkt)
                else:
                    dropped += 1
                    
        active_pkts = next_active
        for n in nodes: queues[n].clear()

    res = {
        "Algo": "FTRL", "PDR (%)": len(delays) / total_pkts * 100,
        "Avg Delay": sum(delays) / len(delays) if delays else 0,
        "Overhead": overhead, "Compute Time (ms)": compute_time
    }
    os.makedirs("results", exist_ok=True)
    with open("results/ftrl.json", "w") as f: json.dump(res, f)
    print("FTRL 仿真完成。")  # 移除了 Emoji 防止部分控制台报错

if __name__ == "__main__": run_ftrl()