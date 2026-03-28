import networkx as nx, random, time, json, os
from collections import deque

def run_hypatia():
    random.seed(42) # 保证实验环境绝对一致
    G = nx.navigable_small_world_graph(6, p=1, q=0)
    nodes = list(G.nodes())
    queues = {n: deque() for n in nodes}
    
    total_pkts = 0
    dropped = 0
    delays = []
    overhead = 0
    compute_time = 0.0
    
    active_pkts = []
    
    for step in range(300): # 300个时隙
        # 1. 模拟链路随机断开 (15% 概率)
        link_status = {e: random.random() > 0.15 for e in G.edges()}
        link_status.update({(v, u): link_status[(u, v)] for u, v in G.edges()})
        
        # 2. 注入流量
        for _ in range(15):
            src, dst = random.sample(nodes, 2)
            active_pkts.append({"id": total_pkts, "src": src, "dst": dst, "curr": src, "spawn": step, "hops": 0})
            total_pkts += 1

        next_active = []
        
        # 3. 路由计算 (Hypatia 全局快照最短路)
        for pkt in active_pkts:
            if pkt["curr"] == pkt["dst"]:
                delays.append(step - pkt["spawn"])
                continue
            if pkt["hops"] > 15:
                dropped += 1
                continue
                
            start_t = time.perf_counter()
            overhead += len(nodes) * len(G.edges()) # 模拟 OSPF 全局洪泛开销
            
            try:
                # 严格按照全局最短路走
                path = nx.shortest_path(G, pkt["curr"], pkt["dst"])
                next_hop = path[1] if len(path) > 1 else pkt["dst"]
            except:
                next_hop = None
            compute_time += (time.perf_counter() - start_t) * 1000

            # 4. 转发与丢包判定
            if next_hop is None or not link_status.get((pkt["curr"], next_hop), False):
                dropped += 1 # 链路断开，直接丢弃
            else:
                if len(queues[next_hop]) < 50: # 队列限制
                    pkt["curr"] = next_hop
                    pkt["hops"] += 1
                    queues[next_hop].append(pkt)
                    next_active.append(pkt)
                else:
                    dropped += 1
                    
        active_pkts = next_active
        for n in nodes: queues[n].clear()

    # 导出数据
    res = {
        "Algo": "Hypatia",
        "PDR (%)": len(delays) / total_pkts * 100,
        "Avg Delay": sum(delays) / len(delays) if delays else 0,
        "Overhead": overhead,
        "Compute Time (ms)": compute_time
    }
    os.makedirs("results", exist_ok=True)
    with open("results/hypatia.json", "w") as f: json.dump(res, f)
    print("✅ Hypatia 仿真完成并导出。")

if __name__ == "__main__":
    run_hypatia()