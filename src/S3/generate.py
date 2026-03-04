import csv
import math
import random

# --- 全局配置 ---
DURATION_SEC = 60          # 仿真时长 60秒
SAMPLE_RATE_HZ = 10        # 10Hz (100ms)
TOTAL_STEPS = DURATION_SEC * SAMPLE_RATE_HZ

# 节点数量配置
NUM_GS = 3
NUM_UAV = 10
NUM_SAT = 50

# 物理参数
SAT_ORBIT_HEIGHT = 500 * 1000  # 500km
SAT_VELOCITY = 7000            # 7km/s
SAT_SPACING = 50000            # 卫星间距 50km

UAV_HEIGHT = 500               # 500m
UAV_RADIUS = 3000              # 无人机活动半径 3km

def generate_csv():
    filename = 'mock_trace.csv'
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['time_ms', 'node_id', 'name', 'type', 'ecef_x', 'ecef_y', 'ecef_z', 'altitude_km', 'orbit_id', 'ip'])
        
        print(f"正在生成 {NUM_GS + NUM_UAV + NUM_SAT} 个节点, 共 {TOTAL_STEPS} 帧的数据...")

        for step in range(TOTAL_STEPS):
            time_ms = int(step * (1000 / SAMPLE_RATE_HZ))
            t = time_ms / 1000.0
            
            # --- 1. 生成地面站 (GS) ---
            # 分布在 x 轴上，间隔 10km
            for i in range(NUM_GS):
                node_id = f"GS_{i:02d}"
                x = i * 10000
                y = 0
                z = 0
                ip = f"10.0.1.{i+1}"
                writer.writerow([time_ms, node_id, f"GroundStation-{i}", 'GS', x, y, z, 0.0, 0, ip])

            # --- 2. 生成无人机群 (UAV) ---
            # 在 GS_00 附近随机盘旋
            for i in range(NUM_UAV):
                node_id = f"UAV_{i:02d}"
                # 每个无人机有不同的相位和半径，看起来像一群蜜蜂
                angle = (2 * math.pi / NUM_UAV) * i + (t * 0.2) # 旋转
                r = UAV_RADIUS + math.sin(t + i) * 500          # 半径轻微波动
                
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                z = UAV_HEIGHT + math.sin(t * 0.5 + i) * 50     # 高度轻微波动
                
                ip = f"10.0.2.{i+1}"
                writer.writerow([time_ms, node_id, f"Drone-{i}", 'UAV', int(x), int(y), int(z), round(z/1000, 3), 0, ip])

            # --- 3. 生成卫星星座 (SAT) ---
            # 模拟一条“星链”，沿 X 轴正方向快速飞行
            for i in range(NUM_SAT):
                node_id = f"SAT_{i:02d}"
                
                # 初始位置分布在一条线上：从 -1000km 到 +1500km
                # 加上速度 * 时间
                start_x = (i - NUM_SAT//2) * SAT_SPACING 
                current_x = start_x + SAT_VELOCITY * t
                
                y = 0 # 就在头顶正上方
                z = SAT_ORBIT_HEIGHT
                
                # 模拟地球曲率 (简单近似)：离中心越远，Z轴稍微降低一点点
                # z = sqrt(R^2 - x^2) - R ... 这里简化处理，直接用平面
                
                ip = f"10.0.3.{i+1}"
                writer.writerow([time_ms, node_id, f"Starlink-{i}", 'SAT', int(current_x), int(y), int(z), 500.0, 1, ip])

    print(f"✅ 生成完毕! 文件大小可能较大，请注意。")

if __name__ == '__main__':
    generate_csv()