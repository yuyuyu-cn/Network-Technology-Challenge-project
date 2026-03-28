import networkx as nx, random, time, json, os
from collections import deque

def get_dist(n1, n2): return abs(n1[0]-n2[0]) + abs(n1[1]-n2[1])

def run_lsr():
    random.seed(42) 
    G = nx.navigable_small_world_graph(6, p=1, q=0)
    nodes = list(G.nodes())
    queues = {n: deque() for n in nodes}
    
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
            overhead += len(neighbors) # 开销极低，仅向邻居询问状态
            
            best_hop = None
            best_score = float('inf')
            
            # LSR 核心逻辑：只看邻居，贪婪计算
            for n in neighbors:
                if link_status.get((pkt["curr"], n), False):
                    # 分数 = 距离终点的距离 + 0.5 * 邻居拥堵程度
                    score = get_dist(n, pkt["dst"]) + 0.5 * len(queues[n])
                    if score < best_score:
                        best_score = score
                        best_hop = n
                        
            compute_time += (time.perf_counter() - start_t) * 1000

            if best_hop is None or get_dist(best_hop, pkt["dst"]) >= get_dist(pkt["curr"], pkt["dst"]):
                dropped += 1 # 找不到更近的路，或陷入死胡同
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
        "Algo": "LSR", "PDR (%)": len(delays) / total_pkts * 100,
        "Avg Delay": sum(delays) / len(delays) if delays else 0,
        "Overhead": overhead, "Compute Time (ms)": compute_time
    }
    os.makedirs("results", exist_ok=True)
    with open("results/lsr.json", "w") as f: json.dump(res, f)
    print("✅ LSR 仿真完成并导出。")

if __name__ == "__main__": run_lsr()