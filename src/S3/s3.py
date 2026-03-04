import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import json
import math
import networkx as nx  

class NumpyEncoder(json.JSONEncoder):
    """ Special json encoder for numpy types """
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

# 常量配置
MAX_LINK_RANGE = 5000 * 1000 
MIN_ELEVATION_DEG = 10.0      
SPEED_OF_LIGHT = 3e8          

CONTENT_LOCATIONS = {
    "UAV_05": ["map.tif"], # 指定这架无人机有缓存
    "SAT_25": ["video.ts"] # 指定这颗卫星有视频
}

# 简单的哈希映射：把 ID 映射成 IP
# 例如 GS_01 -> 10.0.1.1
def get_ip_by_id(node_id):
    try:
        prefix, num = node_id.split('_')
        n = int(num)
        if prefix == 'GS': return f"10.0.1.{n+1}"
        if prefix == 'UAV': return f"10.0.2.{n+1}"
        if prefix == 'SAT': return f"10.0.3.{n+1}"
    except:
        return "127.0.0.1"
    return "127.0.0.1"

# 1: 辅助函数
def calculate_delay(dist_m):
    return (dist_m / SPEED_OF_LIGHT) * 1000

def calculate_jitter(delay_ms):
    return delay_ms * 0.1

def calculate_bandwidth(node_type_a, node_type_b):
    types = {node_type_a, node_type_b}
    if 'GS' in types and 'UAV' in types: return 54
    elif 'UAV' in types and 'SAT' in types: return 20
    elif 'SAT' in types and 'GS' in types: return 20
    elif 'SAT' in types: return 100
    return 10

def calculate_bdp_queue(bw_mbps, delay_ms):                              
    bdp_bits = (bw_mbps * 1e6) * (delay_ms * 2 * 1e-3)
    queue_pkts = int(bdp_bits / 12000)
    return max(10, queue_pkts)

def calculate_elevation(pos_a, pos_b):
    dz = abs(pos_a[2] - pos_b[2])
    dx = pos_a[0] - pos_b[0]
    dy = pos_a[1] - pos_b[1]
    horizontal_dist = math.sqrt(dx**2 + dy**2)
    if horizontal_dist == 0: return 90.0
    angle_rad = math.atan(dz / horizontal_dist)
    return math.degrees(angle_rad)

# 2: 拓扑计算
def compute_topology_at_time(df_t, time_ms):
    links = []
    coords = df_t[['ecef_x', 'ecef_y', 'ecef_z']].values
    ids = df_t['node_id'].values
    types = df_t['type'].values
    tree = cKDTree(coords)
    dists, indices = tree.query(coords, k=10, distance_upper_bound=MAX_LINK_RANGE)
    processed_pairs = set()

    for i in range(len(ids)):
        for j_idx, neighbor_idx in enumerate(indices[i]):
            if dists[i][j_idx] == float('inf') or i == neighbor_idx: continue
            pair_key = tuple(sorted([ids[i], ids[neighbor_idx]]))
            if pair_key in processed_pairs: continue
            
            type_a, type_b = types[i], types[neighbor_idx]
            is_cross_layer = ('SAT' in [type_a, type_b]) and ('SAT' != type_a or 'SAT' != type_b)
            if is_cross_layer:
                low_idx = i if df_t.iloc[i]['ecef_z'] < df_t.iloc[neighbor_idx]['ecef_z'] else neighbor_idx
                high_idx = neighbor_idx if low_idx == i else i
                elev = calculate_elevation(coords[low_idx], coords[high_idx])
                if elev < MIN_ELEVATION_DEG: continue

            dist_m = dists[i][j_idx]
            delay = calculate_delay(dist_m)
            jitter = calculate_jitter(delay)
            bw = calculate_bandwidth(type_a, type_b)
            queue = calculate_bdp_queue(bw, delay)
            
            links.append({
                'time_ms': time_ms,
                'src': ids[i],
                'dst': ids[neighbor_idx],
                'direction': 'BIDIR',
                'distance_km': round(dist_m / 1000, 3),
                'delay_ms': round(delay, 2),
                'jitter_ms': round(jitter, 3),
                'loss_pct': 0.0,
                'bw_mbps': bw,
                'max_queue_pkt': queue,
                'type': f"{type_a}-{type_b}",
                'status': 'UP'
            })
            processed_pairs.add(pair_key)
    return links

# 3: 路由策略生成 

def build_network_graph(topology_links):
    """
    根据链路列表构建 NetworkX 图
    图的边权重设置为 delay_ms，用于最短路计算
    """
    G = nx.Graph()
    for link in topology_links:
        # 添加带权边
        G.add_edge(link['src'], link['dst'], weight=link['delay_ms'])
    return G

def find_best_route(G, src_id, content_name, algo_mode):
    """
    寻找最佳路由路径
    返回: (next_hop_id, next_hop_ip, target_id)
    """
    
    # 1. 确定潜在的目标节点集合
    candidates = []
    
    if algo_mode == 'Content-Aware':
        # 策略：只要节点有缓存，就是候选目标
        for node, contents in CONTENT_LOCATIONS.items():
            if content_name in contents and node in G.nodes:
                candidates.append(node)
    
    # 如果 Content-Aware 没找到候选者，或者模式是 Greedy，则回源
    # 假设 SAT_02 是默认源站 
    if not candidates or algo_mode == 'Greedy':
        if 'SAT_02' in G.nodes:
            candidates = ['SAT_02']
        else:
            return None, None, None # 源站不可达

    # 2. 在图中搜索到所有候选者的最短路径
    best_path = None
    min_cost = float('inf')
    final_target = None
    
    for target in candidates:
        try:
            # Dijkstra 算法找最短延迟路径
            path = nx.shortest_path(G, source=src_id, target=target, weight='weight')
            # 计算路径总开销 (总延迟)
            cost = nx.shortest_path_length(G, source=src_id, target=target, weight='weight')
            
            # 如果延迟差不多，Content-Aware 会优先选 UAV (边缘)，Greedy 只能选 SAT (源站)
            
            if cost < min_cost:
                min_cost = cost
                best_path = path
                final_target = target
        except nx.NetworkXNoPath:
            continue

   # 3. 提取下一跳
    if best_path and len(best_path) > 1:
        next_hop_id = best_path[1] # path[0]是源，path[1]是下一跳
        
        # 直接调用生成函数获取 IP
        next_hop_ip = get_ip_by_id(next_hop_id)
        
        # 简单校验一下生成的 IP 是否有效 (可选)
        if next_hop_ip and next_hop_ip != "127.0.0.1": 
            return next_hop_id, next_hop_ip, final_target
        else:
            # 如果 IP 生成逻辑失败，打个警告
            print(f"[Warn] Cannot generate valid IP for {next_hop_id}")
            return None, None, None
            
    return None, None, None

def generate_routing_rules(current_links, time_ms):
    """生成某一时刻的路由规则"""
    rules = []
    
    # --- 1. 构建当前时刻的网络图 ---
    G = build_network_graph(current_links)
    
    # --- 2. 定义业务需求 ---
    # 需求：GS_01 想要 map.tif
    # 目标 IP (dst_cidr)：我们假设内容请求是发往一个虚拟 IP 或源站 IP (SAT_02 的 IP)
    # S4 会拦截这个 IP 的流量，根据我们的规则转发
    target_content_ip = "10.0.3.26/32" 
    
    # --- 3. 计算 Greedy 路径 (基准) ---
    # Greedy 只会去找源站 SAT_02
    nh_greedy, nh_ip_greedy, target_greedy = find_best_route(G, 'GS_01', 'map.tif', 'Greedy')
    
    if nh_greedy:
        rules.append({
            "time_ms": int(time_ms),
            "node": "GS_01",
            "dst_cidr": target_content_ip, 
            "action": "replace",
            "next_hop": nh_greedy,
            "next_hop_ip": nh_ip_greedy,
            "algo": "Greedy",
            "debug_info": f"Target: {target_greedy}"
        })

    # --- 4. 计算 Content-Aware 路径 ---
    # Content-Aware 可能会找到近处的 UAV_01
    nh_smart, nh_ip_smart, target_smart = find_best_route(G, 'GS_01', 'map.tif', 'Content-Aware')
    
    if nh_smart:
        rules.append({
            "time_ms": int(time_ms),
            "node": "GS_01",
            "dst_cidr": target_content_ip, 
            "action": "replace",
            "next_hop": nh_smart,
            "next_hop_ip": nh_ip_smart,
            "algo": "Content-Aware-CGR",
            "debug_info": f"Target: {target_smart}" 
        })

    return rules

# 主流程 (保持不变)
def main():
    print(">>> S3 Brain Starting...")
    
    # 1. 读取轨迹
    df = pd.read_csv('mock_trace.csv')
    timestamps = df['time_ms'].unique()
    timestamps.sort()
    
    all_links = []
    all_rules = {"meta": {"version": "v1"}, "rules": []}
    
    # 2. 时间步循环
    for t in timestamps:
        t_val = int(t)
        df_t = df[df['time_ms'] == t]
        
        # A. 计算拓扑
        current_links = compute_topology_at_time(df_t, t_val)
        all_links.extend(current_links)
        
        # B. 计算路由
        current_rules = generate_routing_rules(current_links, t_val)
        all_rules["rules"].extend(current_rules)
        
        print(f"Time {t_val}ms: Generated {len(current_links)} links, {len(current_rules)} rules.")

    # 3. 输出文件
    df_links = pd.DataFrame(all_links)
    cols = ['time_ms', 'src', 'dst', 'direction', 'distance_km', 'delay_ms', 
            'jitter_ms', 'loss_pct', 'bw_mbps', 'max_queue_pkt', 'type', 'status']
    df_links[cols].to_csv('topology_links.csv', index=False)
    print(">>> Saved topology_links.csv")
    
    with open('routing_rules.json', 'w') as f:
        json.dump(all_rules, f, indent=2, cls=NumpyEncoder)
    print(">>> Saved routing_rules.json")

if __name__ == "__main__":
    main()