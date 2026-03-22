import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import json
import math
import networkx as nx
import glob
import os

# --- 全局配置 ---
MAX_LINK_RANGE = 5000 * 1000  
MIN_ELEVATION_DEG = 10.0      
SPEED_OF_LIGHT = 3e8             

# ★★★ 扩展业务配置 (模拟内容分布) ★★★
# 我们定义三种文件，分布在不同的节点上
CONTENT_LOCATIONS = {
    "UAV_01": ["map.tif", "sos_cmd.txt"], # 前线无人机缓存了地图和指令
    "UAV_02": ["sos_cmd.txt"],            # 另一架无人机只有指令
    "SAT_63188": ["video.ts", "map.tif", "sos_cmd.txt"], # 源站卫星拥有所有文件
    "SAT_63189": ["video.ts", "sos_cmd.txt"]             # 备用卫星
}

# 业务虚拟 IP 映射 (用于路由匹配)
SERVICE_IPS = {
    "map.tif": "10.99.1.1/32",      # 地图服务虚拟IP
    "video.ts": "10.99.2.1/32",     # 视频服务虚拟IP
    "sos_cmd.txt": "10.99.3.1/32"   # 紧急指令虚拟IP
}

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        elif isinstance(obj, np.floating): return float(obj)
        elif isinstance(obj, np.ndarray): return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

# ---------------------------------------------------------
# 模块 0: 数据加载与融合 (修改点 1: 读取单个 UAV 文件)
# ---------------------------------------------------------
def load_and_merge_traces(sat_dir='sat_trace', uav_file='uav_trace_full.csv'):
    print(">>> Loading Trace Data...")
    
    # 1. 读取所有卫星数据 (保持不变)
    sat_files = glob.glob(os.path.join(sat_dir, "*.csv"))
    sat_dfs = []
    for f in sat_files:
        print(f"  - Reading {f}")
        df = pd.read_csv(f)
        sat_dfs.append(df)
    
    df_sat = pd.concat(sat_dfs) if sat_dfs else pd.DataFrame()
    
    # 2. 读取单个 UAV/地面站数据 (修改为直接读取文件)
    print(f"  - Reading {uav_file}")
    if os.path.exists(uav_file):
        df_uav = pd.read_csv(uav_file)
    else:
        print(f"[Error] UAV trace file not found: {uav_file}")
        df_uav = pd.DataFrame()

    # 3. 时间对齐
    all_timestamps = sorted(df_uav['time_ms'].unique()) if not df_uav.empty else []
    if all_timestamps:
        print(f">>> Total Time Steps: {len(all_timestamps)} (from {min(all_timestamps)} to {max(all_timestamps)} ms)")
    
    return df_sat, df_uav, all_timestamps

def get_nodes_at_timestamp(df_sat, df_uav, target_time_ms):
    uav_current = df_uav[df_uav['time_ms'] == target_time_ms]
    sat_time_key = (target_time_ms // 1000) * 1000
    sat_current = df_sat[df_sat['time_ms'] == sat_time_key]
    
    cols = ['node_id', 'type', 'ecef_x', 'ecef_y', 'ecef_z', 'ip']
    
    if sat_current.empty and uav_current.empty:
        return pd.DataFrame(columns=cols)
        
    nodes = pd.concat([sat_current[cols], uav_current[cols]], ignore_index=True)
    return nodes

# ---------------------------------------------------------
# 模块 1 & 2: 物理层计算 (保持不变)
# ---------------------------------------------------------
def calculate_delay(dist_m): return (dist_m / SPEED_OF_LIGHT) * 1000
def calculate_jitter(delay_ms): return delay_ms * 0.1
def calculate_bandwidth(type_a, type_b):
    types = {type_a, type_b}
    if 'GS' in types and 'UAV' in types: return 54
    if 'UAV' in types and 'SAT' in types: return 20
    if 'SAT' in types and 'GS' in types: return 20
    if 'SAT' in types: return 100
    return 10
def calculate_bdp_queue(bw_mbps, delay_ms):
    queue = int((bw_mbps * 1e6) * (delay_ms * 2 * 1e-3) / 12000)
    return max(10, queue)

def calculate_elevation(pos_a, pos_b):
    vec_a = np.array(pos_a)
    vec_ab = np.array(pos_b) - np.array(pos_a)
    dist_a = np.linalg.norm(vec_a)
    dist_ab = np.linalg.norm(vec_ab)
    if dist_a == 0 or dist_ab == 0: return 90.0
    cos_theta = np.dot(vec_a, vec_ab) / (dist_a * dist_ab)
    cos_theta = max(min(cos_theta, 1.0), -1.0)
    theta_rad = np.arccos(cos_theta)
    return 90 - math.degrees(theta_rad)

def compute_topology(nodes_df, time_ms):
    links = []
    if len(nodes_df) < 2: return links
    
    coords = nodes_df[['ecef_x', 'ecef_y', 'ecef_z']].values
    ids = nodes_df['node_id'].values
    types = nodes_df['type'].values
    
    tree = cKDTree(coords)
    dists, indices = tree.query(coords, k=20, distance_upper_bound=MAX_LINK_RANGE)
    
    processed_pairs = set()

    # ★★★ 强制断连配置 ★★★
    # 确保这里的 ID 和你 CSV 里的一模一样
    # 如果不确定，可以写 print(ids) 看一下到底有哪些 ID
    FORCE_DOWN_SRC = 'GS_01'
    FORCE_DOWN_DST = 'SAT_63188'
    DOWN_TIME_MS = 0 # 0ms 开始断

    for i in range(len(ids)):
        for j_idx, neighbor_idx in enumerate(indices[i]):
            if dists[i][j_idx] == float('inf') or i == neighbor_idx: continue
            
            n1_id, n2_id = ids[i], ids[neighbor_idx]
            pair_key = tuple(sorted([n1_id, n2_id]))
            if pair_key in processed_pairs: continue
            
            type_a, type_b = types[i], types[neighbor_idx]
            
            is_sat_a = (type_a == 'SAT')
            is_sat_b = (type_b == 'SAT')
            
            if is_sat_a != is_sat_b: 
                sat_idx = i if is_sat_a else neighbor_idx
                gnd_idx = neighbor_idx if is_sat_a else i
                elev = calculate_elevation(coords[gnd_idx], coords[sat_idx])
                if elev < MIN_ELEVATION_DEG: continue

            dist_m = dists[i][j_idx]
            delay = calculate_delay(dist_m)
            bw = calculate_bandwidth(type_a, type_b)
            
            # ★★★ 注入断连逻辑 ★★★
            status = 'UP'
            # 检查是否命中了我们要断开的链路，并且时间已经到了
            if time_ms >= DOWN_TIME_MS:
                if (n1_id == FORCE_DOWN_SRC and n2_id == FORCE_DOWN_DST) or \
                   (n1_id == FORCE_DOWN_DST and n2_id == FORCE_DOWN_SRC):
                    status = 'DOWN'
                    delay = 99999.0 # 极大延迟
                    # 可选：如果你希望断了的线根本不在 CSV 里出现，就直接 continue
                    # continue 
            
            links.append({
                'time_ms': time_ms,
                'src': n1_id,
                'dst': n2_id,
                'direction': 'BIDIR',
                'distance_km': round(dist_m / 1000, 3),
                'delay_ms': round(delay, 2),
                'jitter_ms': round(calculate_jitter(delay), 3),
                'loss_pct': 0.0,
                'bw_mbps': bw,
                'max_queue_pkt': calculate_bdp_queue(bw, delay),
                'type': f"{type_a}-{type_b}",
                'status': status  # 这里写入状态
            })
            processed_pairs.add(pair_key)
    return links

# ---------------------------------------------------------
# 模块 3: 路由策略 (保持不变)
# ---------------------------------------------------------
def build_graph(links):
    G = nx.Graph()
    for l in links:
        G.add_edge(l['src'], l['dst'], weight=l['delay_ms'])
    return G

def find_route(G, src_id, content, mode, node_ip_map):
    candidates = []
    if mode == 'Content-Aware':
        for node, files in CONTENT_LOCATIONS.items():
            if content in files and node in G.nodes:
                candidates.append(node)
    
    if not candidates or mode == 'Greedy':
        sat_candidates = [n for n in G.nodes if str(n).startswith('SAT_')]
        if sat_candidates:
            candidates = sat_candidates
    
    if not candidates: return None, None, None

    best_target, best_path, min_cost = None, None, float('inf')

    for target in candidates:
        try:
            cost = nx.shortest_path_length(G, src_id, target, weight='weight')
            if cost < min_cost:
                min_cost = cost
                best_path = nx.shortest_path(G, src_id, target, weight='weight')
                best_target = target
        except: continue
        
    if best_path and len(best_path) > 1:
        nh_id = best_path[1]
        nh_ip = node_ip_map.get(nh_id, "0.0.0.0")
        return nh_id, nh_ip, best_target
        
    return None, None, None

# ---------------------------------------------------------
# 路由规则生成辅助函数 (新增)
# ---------------------------------------------------------
def generate_routing_rules(active_links, time_ms, node_ip_map, active_nodes):
    """
    根据当前存活链路，生成多业务并发的路由规则
    """
    rules = []
    if not active_links:
        return rules
        
    G = build_graph(active_links)

    # ==== 场景 1: 地面站 GS_01 请求边缘缓存文件 (map.tif) ====
    # 预期: 聪明算法找 UAV_01，笨算法找 SAT_63188
    if 'GS_01' in active_nodes:
        # 1A. Content-Aware (智能算法)
        nh_smart, nh_ip_smart, target_smart = find_route(G, 'GS_01', 'map.tif', 'Content-Aware', node_ip_map)
        if nh_smart:
            rules.append({
                "time_ms": int(time_ms),
                "node": "GS_01",
                "dst_cidr": SERVICE_IPS['map.tif'], 
                "action": "replace",
                "next_hop": nh_smart,
                "next_hop_ip": nh_ip_smart,
                "algo": "Content-Aware-CGR",
                "debug_info": f"[Smart] Fetch map.tif from {target_smart}"
            })
            
        # 1B. Greedy (基准笨算法)
        nh_greedy, nh_ip_greedy, target_greedy = find_route(G, 'GS_01', 'map.tif', 'Greedy', node_ip_map)
        # 只有两个算法选的路不一样时，才输出 Baseline，用于画对比图
        if nh_greedy and nh_greedy != nh_smart:
            rules.append({
                "time_ms": int(time_ms),
                "node": "GS_01",
                "dst_cidr": "10.88.88.88/32", # 为对比组单独分配一个不同的虚拟IP
                "action": "replace",
                "next_hop": nh_greedy,
                "next_hop_ip": nh_ip_greedy,
                "algo": "Greedy-Baseline",
                "debug_info": f"[Dumb] Forced fetch map.tif from {target_greedy}"
            })

    # ==== 场景 2: 地面站 GS_01 请求核心大文件 (video.ts) ====
    # 预期: UAV 没有这个文件，算法被迫去找天上的卫星
    if 'GS_01' in active_nodes:
        nh_vid, nh_ip_vid, target_vid = find_route(G, 'GS_01', 'video.ts', 'Content-Aware', node_ip_map)
        if nh_vid:
            rules.append({
                "time_ms": int(time_ms),
                "node": "GS_01",
                "dst_cidr": SERVICE_IPS['video.ts'], 
                "action": "replace",
                "next_hop": nh_vid,
                "next_hop_ip": nh_ip_vid,
                "algo": "Content-Aware-CGR",
                "debug_info": f"[Smart] Stream video.ts from {target_vid}"
            })

    # ==== 场景 3: 无人机 UAV_01 作为中继转发紧急指令 ====
    # 预期: UAV_01 如果需要向外转发 sos_cmd，它需要在图里找路
    if 'UAV_01' in active_nodes:
        nh_sos, nh_ip_sos, target_sos = find_route(G, 'UAV_01', 'sos_cmd.txt', 'Content-Aware', node_ip_map)
        if nh_sos:
             rules.append({
                "time_ms": int(time_ms),
                "node": "UAV_01",  # 此时是 UAV 在配路由表
                "dst_cidr": SERVICE_IPS['sos_cmd.txt'], 
                "action": "replace",
                "next_hop": nh_sos,
                "next_hop_ip": nh_ip_sos,
                "algo": "Content-Aware-CGR",
                "debug_info": f"[Relay] Forward SOS to {target_sos}"
            })

    return rules

# ---------------------------------------------------------
# 主流程 (修改点 2: 注入 Down 链路)
# ---------------------------------------------------------
def main():
    output_link_dir = 'output/links'
    output_rule_dir = 'output/rules'
    os.makedirs(output_link_dir, exist_ok=True)
    os.makedirs(output_rule_dir, exist_ok=True)

    # 1. 加载数据 (指定单个 UAV 文件)
    df_sat, df_uav, timelines = load_and_merge_traces(uav_file='uav_trace_full.csv')
    
    if not timelines:
        print("[Error] No timelines found. Exiting.")
        return

    print(">>> Building IP Map...")
    node_ip_map = {}
    for _, row in df_sat[['node_id', 'ip']].drop_duplicates().iterrows():
        node_ip_map[row['node_id']] = row['ip']
    for _, row in df_uav[['node_id', 'ip']].drop_duplicates().iterrows():
        node_ip_map[row['node_id']] = row['ip']
    print(f"   Mapped {len(node_ip_map)} nodes.")

    CHUNK_SIZE_MS = 60000 
    chunk_links = []
    chunk_rules = []
    current_chunk_idx = 0
    
    # ★★★ 修改点 2: 定义要被强制 Down 掉的链路 ★★★
    TARGET_DOWN_SRC = 'GS_01'
    TARGET_DOWN_DST = 'SAT_63188' # 假设这是当前的主通信卫星
    DOWN_TIME_MS = 0 # 触发时间：0毫秒

    print(f">>> Start Processing {len(timelines)} time steps...")

    for i, t in enumerate(timelines): 
        t_val = int(t)
        current_nodes_df = get_nodes_at_timestamp(df_sat, df_uav, t_val)
        
        # 获取当前存活节点的 ID 列表
        active_node_ids = current_nodes_df['node_id'].values if not current_nodes_df.empty else []
        
        # A. 计算物理拓扑
        links = compute_topology(current_nodes_df, t_val)
        
        # ★★★ 注入故障逻辑 ★★★
        if t_val >= DOWN_TIME_MS:
            for l in links:
                if (l['src'] == TARGET_DOWN_SRC and l['dst'] == TARGET_DOWN_DST) or \
                   (l['src'] == TARGET_DOWN_DST and l['dst'] == TARGET_DOWN_SRC):
                    l['status'] = 'DOWN'
                    l['delay_ms'] = 99999.0 # 极大延迟，阻断路由
                    
        chunk_links.extend(links)
        
        # B. 计算路由策略 (调用抽离出来的函数)
        # 提取状态为 UP 的链路传给路由引擎
        active_links = [l for l in links if l['status'] == 'UP']
        new_rules = generate_routing_rules(active_links, t_val, node_ip_map, active_node_ids)
        chunk_rules.extend(new_rules)
        
        if i % 100 == 0:
            print(f"   [Progress] Step {i}/{len(timelines)} (Time {t_val}ms)")

        # C. 分片保存
        is_last_step = (i == len(timelines) - 1)
        next_t = timelines[i+1] if not is_last_step else -1
        
        if is_last_step or (int(next_t / CHUNK_SIZE_MS) > int(t_val / CHUNK_SIZE_MS)):
            start_ms = current_chunk_idx * CHUNK_SIZE_MS
            end_ms = t_val 
            link_filename = f"topology_links_{start_ms}_{end_ms}.csv"
            rule_filename = f"routing_rules_{start_ms}_{end_ms}.json"
            
            if chunk_links:
                df_links = pd.DataFrame(chunk_links)
                cols = ['time_ms', 'src', 'dst', 'direction', 'distance_km', 'delay_ms', 
                        'jitter_ms', 'loss_pct', 'bw_mbps', 'max_queue_pkt', 'type', 'status']
                for c in cols:
                    if c not in df_links.columns: df_links[c] = None
                df_links[cols].to_csv(os.path.join(output_link_dir, link_filename), index=False)
            
            rule_data = {"meta": {"version": "v1.2", "chunk_id": current_chunk_idx}, "rules": chunk_rules}
            with open(os.path.join(output_rule_dir, rule_filename), 'w') as f:
                json.dump(rule_data, f, indent=2, cls=NumpyEncoder)
            
            print(f"   >>> [Saved Chunk {current_chunk_idx}] {link_filename}")
            
            chunk_links = []
            chunk_rules = []
            current_chunk_idx += 1

    print(">>> All Done.")

if __name__ == "__main__":
    main()