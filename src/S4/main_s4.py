
import config as cf
from config import action, LogColor
import time
import csv
import json


if cf.MODE == "soft":
    from mode_b import Engine
    LogColor.info("mode b imported")
else:
    from mode_a import Engine
    LogColor.info("mode a imported")

def ReadLinks(csv_path):
    links = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            tmp = dict()
            for k, v in row.items():
                tmp[k] = v
            links.append(tmp)
    return links

def ReadRules(json_path):
    with open(json_path, 'r', newline='', encoding='utf-8') as f:
        data = json.load(f)

        tmp_action = action.NOP
        for rule in data['rules']:
            if rule['action'] == 'del':
                tmp_action = action.DEL
            elif rule['action'] == 'add':
                tmp_action = action.ADD
            elif rule['action'] == 'replace':
                tmp_action = action.REPLACE
            
            rule['action'] = tmp_action
        return data['meta'], data['rules']

if __name__ == '__main__':
    links = ReadLinks('test_data/topology_links.csv')
    engine = Engine()
    # engine.PrintGraph()

    meta, rules = ReadRules('test_data/routing_rules.json')
    engine.AddContent('UAV_01', 'test.jpg', filesize=50)
    timer = 0
    rule_ind = 0
    req_ind = 0
    edge_ind = 0
    reqs = [
    ]

    try:
        while True:
            LogColor.info(f'time : {timer}')
            while edge_ind < len(links) and int(links[edge_ind]['time_ms']) <= timer:
                engine.addLink(links[edge_ind])
                LogColor.info(f'edge {edge_ind} applied')
                edge_ind += 1

            while rule_ind < len(rules) and rules[rule_ind]['time_ms'] <= timer:
                engine.UpdateRule(rules[rule_ind], meta)
                LogColor.info(f'rule {rule_ind} applied')
                rule_ind += 1
            while req_ind < len(reqs) and reqs[req_ind]['time']  <= timer:
                req = reqs[req_ind]
                engine.ExecuteReq(req['node_id'], req['content_id'], timer, 'output/networks.csv')
                req_ind += 1
            timer += 100
            time.sleep(0.1)
    except KeyboardInterrupt:
        engine.PrintGraph()
        pass
    finally:
        engine.StopNet()
