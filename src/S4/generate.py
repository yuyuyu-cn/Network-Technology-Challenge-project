import random

def generate_sar_traffic(uav_list, main_gs, max_time_ms=60000):
    requests = []
    
    for current_time in range(0, max_time_ms, 100):
        
        if current_time % 1000 == 0:
            for uav in uav_list:
                requests.append({
                    'time': current_time + random.randint(0, 50),
                    'node_id': main_gs,
                    'content_id': f'telemetry_{uav}'
                })
        #
        # # 阶段 1: 常规搜索 (0-30s)，地面站拉取低清图像
        # if current_time < 30000 and current_time % 2000 == 0:
        #     for uav in uav_list:
        #         requests.append({
        #             'time': current_time + random.randint(0, 100),
        #             'node_id': main_gs,      # 请求方是地面站
        #             'content_id': f'low_res_img_{uav}'
        #         })
        #
        # # 阶段 2: 发现目标 (30s 之后)！地面站疯狂拉取高清视频
        # if current_time >= 30000 and current_time % 500 == 0:
        #     requests.append({
        #         'time': current_time,
        #         'node_id': main_gs,          # 请求方是地面站
        #         'content_id': '4k_video_stream'
        #     })
        #
        # if current_time == 35000:
        #     for uav in uav_list:
        #         if uav != 'UAV_02': # 假设 UAV_02 忙着发视频，其他飞机去支援
        #             requests.append({
        #                 'time': current_time,
        #                 'node_id': uav,       # 请求方是无人机
        #                 'content_id': 'c2_converge_cmd'
        #             })
        #
    # 按 'time' 排序，适配主循环判断
    requests.sort(key=lambda x: x['time'])
    return requests
