import networkx as nx, random, time, json, os
from collections import deque

def run_dtn_cgr():
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
            if step - pkt["spawn"] > 100: 
                dropped += 1; continue
                
            start_t = time.perf_counter()
            overhead += len(nodes) * 2 
            
            try:
                path = nx.shortest_path(G, pkt["curr"], pkt["dst"])
                next_hop = path[1] if len(path) > 1 else pkt["dst"]
            except:
                next_hop = None
                
            compute_time += (time.perf_counter() - start_t) * 1000

            if next_hop is None or not link_status.get((pkt["curr"], next_hop), False):
                next_active.append(pkt) # DTN 核心：留在原地，永不丢弃
            else:
                if len(queues[next_hop]) < 500: # 极大硬盘
                    pkt["curr"] = next_hop
                    pkt["hops"] += 1
                    queues[next_hop].append(pkt)
                    next_active.append(pkt)
                else:
                    dropped += 1
                    
        active_pkts = next_active
        for n in nodes: queues[n].clear()

    res = {
        "Algo": "DTN-CGR", "PDR (%)": len(delays) / total_pkts * 100,
        "Avg Delay": sum(delays) / len(delays) if delays else 0,
        "Overhead": overhead, "Compute Time (ms)": compute_time
    }
    os.makedirs("results", exist_ok=True)
    with open("results/dtn.json", "w") as f: json.dump(res, f)
    print("✅ DTN-CGR 仿真完成。")

if __name__ == "__main__": run_dtn_cgr()