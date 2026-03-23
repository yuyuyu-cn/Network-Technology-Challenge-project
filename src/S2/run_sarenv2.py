import os
import csv
import math
import random
from pymap3d import enu2ecef

import sarenv
from sarenv import DataGenerator, DatasetLoader, LostPersonLocationGenerator
from sarenv.analytics.paths import generate_spiral_path

# -------------------------
# 1. 地理与规模配置
# -------------------------
# 四川成都某区域中心 (青城山附近，适合搜救场景)
SICHUAN_LAT = 30
SICHUAN_LON = 104
ANCHOR_ALT = 559
DATASET_DIR = "sarenv_dataset_sichuan"
SIZE = "medium"  # 使用 medium 规模

# 仿真参数
NUM_UAVS = 3
SEARCH_RADIUS_M = 2500     # 2.5km 半径，刚好覆盖 5km 区域
ALTITUDE_M = 50
DETECTION_RANGE_M = 50     # 检测范围
TOTAL_DURATION_MS = 600000 # 10分钟
TIME_STEP_MS = 100         # 10Hz

# -------------------------
# 2. 自动检查并下载四川 OSM 数据
# -------------------------
if not os.path.exists(DATASET_DIR):
    print(f"[OSM] 未检测到本地数据，开始下载四川区域地图 ({SICHUAN_LAT}, {SICHUAN_LON})...")
    try:
        # region_size_km=10 确保下载范围足够 medium 使用
        generator = DataGenerator(
            center_lat=SICHUAN_LAT,
            center_lon=SICHUAN_LON,
            region_size_km=10, 
            output_dir=DATASET_DIR
        )
        generator.export_dataset()
        print("[OSM] 数据集生成成功！")
    except Exception as e:
        print(f"[ERROR] 下载失败，请检查网络: {e}")
        exit()

# -------------------------
# 3. 加载环境并生成真实分布的受害者
# -------------------------
print(f"[S1] 加载四川 {SIZE} 环境...")
loader = DatasetLoader(DATASET_DIR)
env_item = loader.load_environment(SIZE)

# 确保受害者是在我们设置的锚点附近生成的
victim_generator = LostPersonLocationGenerator(env_item)
# 生成 30 个受害者，基于真实的道路/水系概率模型
victims = victim_generator.generate_locations(n=30, percent_random_samples=0)

# 转换为相对于中心点的 ENU 坐标
victims_enu = [(v.x, v.y) for v in victims]
print(f"[S1] 成功！在四川真实地形中生成了 {len(victims_enu)} 个受害者。")

# -------------------------
# 4. 路径规划与仿真逻辑
# -------------------------
print("[S2] 规划 3 架无人机的协同螺旋路径...")
# 注意：center_x/y 取 0 表示以地图中心（即我们下载的中心）起飞
spiral_paths = generate_spiral_path(
    center_x=0, center_y=0,
    max_radius=SEARCH_RADIUS_M,
    fov_deg=60, altitude=ALTITUDE_M,
    overlap=0.2, num_drones=NUM_UAVS,
    path_point_spacing_m=30,
)

def simulate_mission(path, victims_list):
    coords = list(path.coords)
    traj_data = {}
    current_time_ms = 0
    detected_ids = set()
    cache_until_ms = -1
    uav_speed = 15
    
    for i in range(len(coords) - 1):
        p1, p2 = coords[i], coords[i+1]
        dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
        seg_ms = int((dist / uav_speed) * 1000)
        steps = max(1, seg_ms // TIME_STEP_MS)
        angle = math.degrees(math.atan2(p2[0]-p1[0], p2[1]-p1[1])) % 360
        
        for step in range(steps):
            t = current_time_ms + step * TIME_STEP_MS
            if t > TOTAL_DURATION_MS: break
            
            ratio = step / steps
            curr_x, curr_y = p1[0] + (p2[0]-p1[0])*ratio, p1[1] + (p2[1]-p1[1])*ratio
            
            for vid, (vx, vy) in enumerate(victims_list):
                if vid not in detected_ids:
                    if math.hypot(curr_x - vx, curr_y - vy) < DETECTION_RANGE_M:
                        detected_ids.add(vid)
                        cache_until_ms = t + 10000 # 发现后 CACHE 10秒
                        print(f"  [t={t}ms] 发现目标 #{vid}！")
            
            role = "CACHE" if t < cache_until_ms else "RELAY"
            traj_data[t] = (curr_x, curr_y, angle, role)
        current_time_ms += seg_ms
        if current_time_ms > TOTAL_DURATION_MS: break
    return traj_data, len(detected_ids)

print("[S3] 计算飞行轨迹...")
results = [simulate_mission(p, victims_enu) for p in spiral_paths]

# -------------------------
# 5. 生成 CSV 文件
# -------------------------
os.makedirs("traces", exist_ok=True)
GS_ECEF = enu2ecef(0, 0, 0, SICHUAN_LAT, SICHUAN_LON, ANCHOR_ALT, deg=True)

for start_t in range(0, TOTAL_DURATION_MS, 60000):
    rows = []
    end_t = start_t + 60000
    for t in range(start_t, end_t, TIME_STEP_MS):
        # GS
        rows.append({
            "time_ms": t, "node_id": "GS_01", "role": "CLIENT", "type": "GS",
            "ecef_x": round(GS_ECEF[0], 1), "ecef_y": round(GS_ECEF[1], 1), "ecef_z": round(GS_ECEF[2], 1),
            "ip": "10.0.0.1", "heading_deg": -1.0, "battery_pct": -1
        })
        # UAVs
        for i in range(NUM_UAVS):
            traj, _ = results[i]
            state = traj.get(t) or traj[max(traj.keys())]
            ux, uy, uh, urole = state
            ex, ey, ez = enu2ecef(ux, uy, ALTITUDE_M, SICHUAN_LAT, SICHUAN_LON, ANCHOR_ALT, deg=True)
            batt = round(max(0.0, 100 - (t / 1000 * 0.1)), 1)
            rows.append({
                "time_ms": t, "node_id": f"UAV_{i+1:02d}", "role": urole, "type": "UAV",
                "ecef_x": round(ex, 1), "ecef_y": round(ey, 1), "ecef_z": round(ez, 1),
                "ip": f"10.0.0.{2+i}", "heading_deg": round(uh, 1), "battery_pct": batt
            })
            
    filename = f"traces/uav_trace_{start_t}_{end_t}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["time_ms", "node_id", "role", "type", "ecef_x", "ecef_y", "ecef_z", "ip", "heading_deg", "battery_pct"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[SUCCESS] {filename}")

print("\n仿真结束，数据已按四川真实地形生成。")
