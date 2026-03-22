import networkx as nx
import csv
import random
import os
from config import action, LogColor

class Engine:
    def __init__(self):
        self.req_id = 1
        self.rules = dict()
        self.G = nx.DiGraph()
        self.content = dict()
    
    def StopNet(self):
        # 非动态拓扑，不做任何处理
        pass

    def addLink(self, link):
       
        edge_attr = {k : v for k, v in link.items() if k != 'direction' and k != 'src' and k != 'dst'}
        self.G.add_node(link['src'])
        self.G.add_node(link['dst'])

        if link['direction'] == 'BIDIR':
            self.G.add_edge(link['src'], link['dst'], **edge_attr)
            self.G.add_edge(link['dst'], link['src'], **edge_attr)
        elif link['direction'] == 'UNIDIR':
            self.G.add_edge(link['src'], link['dst'], **edge_attr)
        else:
            raise RuntimeError('wrong direction type')
            
    def PrintGraph(self):
        for u, v, data in self.G.edges(data=True):
            LogColor.info(f'{u} -> {v} {data}')

    def UpdateRule(self, rule, meta):
        self.version = meta['version']
        # self.src_script = meta['generated_by']
        # self.algo = meta['default_algo']
        # self.create_time = meta['create_time']

        if rule['action'] == action.REPLACE and rule['node'] not in self.rules.keys():
            rule['action'] = action.ADD
        if rule['action'] == action.ADD:
            if rule['node'] in self.rules.keys():
                raise RuntimeError('invaild rule : add existed rule')
            self.rules[rule['node']] = {k: v for k, v in rule.items() if k != "node"}
        elif rule['action'] == action.REPLACE:
            cur_node = rule['node']
            for k, v in self.rules[cur_node].items():
                self.rules[cur_node][k] = rule[k]
        elif rule['action'] == action.DEL:
            if rule['node'] in self.rules.keys():
                self.rules.pop(rule['node'])
        
    def AddContent(self, target, filename, **fileinfo):
        if target in self.content.keys():
            self.content[target][filename] = fileinfo 
        else:
            self.content[target] = {filename : fileinfo }
    
    def DeleteContent(self, target, filename):
        if target in self.content.keys():
            self.content[target].pop(filename)

    def UpdateContent(self, target, filename, **fileinfo):
        self.AddContent(target, filename, **fileinfo)

    def GetContent(self, target, filename):
        if target in self.content.keys() and (filename in self.content[target].keys()):
            return self.content[target][filename]
        return None

    # 单位分别为毫秒，mbps
    def compute_path_metrics(self, path, weight='delay_ms'):
        total_delay = 0.0
        min_bw = float('inf')

        for u, v in zip(path[:-1], path[1:]):
            key, data = min(
                self.G[u][v].items(),
                key=lambda item: item[1][weight]
            )
            total_delay += random.uniform(data['delay_ms'] - data['jitter_ms'], data['delay_ms'] + data['jitter_ms'])
            min_bw = min(min_bw, data['bw_mbps'])

        return total_delay, min_bw

    def ExecuteReq(self, client, content_id, time, log_path):
        if client not in self.rules.keys():
            raise RuntimeError('invalid request: no such client')
        
        target = self.rules[client]['next_hop']
        algo = self.rules[client]['algo']
        cache_status = 'HIT'
        http_code = 200

        if (target in self.content.keys()) and (content_id in self.content[target].keys()):
            def edge_cost(u, v, data):
                if data['status'] != 'UP':
                    return float('inf')
                return data['delay_ms']
            
            path = nx.shortest_path(
                self.G,
                source=client,
                target=target,
                weight=edge_cost
            )

            content_info = self.content[target][content_id]
            file_size_MB = content_info['filesize']

            total_delay, min_bw = self.compute_path_metrics(path)

            download_time = file_size_MB * 8 / min_bw * 1000 + total_delay * 2

            tmp = dict()
            tmp['time_ms'] = time
            tmp['req_id'] = self.req_id
            self.req_id += 1
            tmp['node_id'] = client
            tmp['content_id'] = content_id
            tmp['file_size_MB'] = file_size_MB
            tmp['algo'] = algo
            tmp['path'] = path
            tmp['server_node'] = target
            tmp['latency_ms'] = total_delay * 2
            tmp['throughput_mbps'] = min_bw
            tmp['http_code'] = http_code
            tmp['cache_status'] = cache_status
            tmp['download_time'] = download_time

            self.WriteLog(tmp, log_path)
        else:
            raise RuntimeError('invalid request: no such content')



    def WriteLog(self, row, csv_path):
        if len(row) == 0:
            return
        file_exists = os.path.exists(csv_path)
        write_header = True

        if file_exists:
            # 文件存在但大小为 0，仍然要写表头
            write_header = os.path.getsize(csv_path) == 0

        with open(csv_path, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())

            if write_header:
                writer.writeheader()

            writer.writerow(row)