import * as echarts from 'echarts';
import * as Cesium from 'cesium';
import { shared } from './state.js';
import { getLinkStatus } from './utils.js';

// 辅助函数：通过名称判断节点类型
function getNodeType(name) {
    const upperName = (name || '').toUpperCase();
    if (upperName.includes('GS') || upperName.includes('GROUND')) return 'GS';
    if (upperName.includes('UAV')) return 'UAV';
    return 'SAT'; // 默认为卫星
}

export function update2DTopology(viewer) {
    const container = document.getElementById('topo-2d-container');
    if (!shared.state.showAnalytics || !container) {
        if (shared.chart2D) { shared.chart2D.clear(); shared.lastEdgesString = ""; }
        return;
    }

    // 获取容器宽高，用于计算固定节点的位置
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;
    const nodeCount = shared.nodeInfoList.length || 1;

    // 预先找出所有 GS 节点，用于均匀分布在底部
    const gsNodes = shared.nodeInfoList.filter(n => getNodeType(n.name) === 'GS');
    const gsCount = gsNodes.length || 1;

    // 辅助函数：生成节点的通用属性（包含固定位置、大小、斥力值等）
    const generateNodeProps = (n, index) => {
        const type = getNodeType(n.name);
        const isGS = type === 'GS';
        
        let x, y, fixed;
        if (isGS) {
            // 将 GS 固定在底部，并根据数量均匀分布
            const gsIdx = gsNodes.findIndex(gs => gs.id === n.id);
            x = (width / (gsCount + 1)) * (gsIdx + 1);
            y = height - 60; // 距离底部 60px
            fixed = true;    // 开启固定
        } else {
            // 其他节点初始按圆形分布在上方
            const angle = (index / nodeCount) * Math.PI * 2;
            const radius = Math.min(width, height) * 0.35;
            x = width / 2 + Math.cos(angle) * radius;
            y = height / 2 - 50 + Math.sin(angle) * radius;
            fixed = false;
        }

        return {
            id: String(n.id),
            name: n.name,
            x: x,
            y: y,
            fixed: fixed,
            // 大小区分：GS最大(40)，UAV中等(35)，卫星最小(20)
            symbolSize: isGS ? 40 : (type === 'UAV' ? 35 : 20),
            // value用于映射斥力：GS和UAV斥力大，卫星斥力小
            value: isGS ? 200 : (type === 'UAV' ? 100 : 10),
            itemStyle: { 
                // 颜色区分：当前目标红色，GS绿色，UAV橙色，卫星青色
                color: n.id === shared.state.currentTarget ? '#ff4757' : 
                       (isGS ? '#2ecc71' : type === 'UAV' ? '#f39c12' : '#00f2ff'), 
                shadowBlur: n.id === shared.state.currentTarget ? 15 : 0, 
                shadowColor: '#fff' 
            }
        };
    };

    if (!shared.chart2D) {
        shared.chart2D = echarts.init(container, 'dark');

        const baseRepulsion = Math.min(2000, 600 + nodeCount * 18);
        const baseEdgeLength = Math.min(300, 120 + nodeCount * 4);
        const baseGravity = 0.15;

        const initialNodesWithPos = shared.nodeInfoList.map((n, i) => generateNodeProps(n, i));

        shared.chart2D.setOption({
            backgroundColor: 'transparent',
            series: [{
                type: 'graph', 
                layout: 'force', 
                data: initialNodesWithPos, 
                draggable: true, 
                roam: true,
                force: { 
                    // 改为数组：让 ECharts 根据 node.value 动态映射斥力
                    repulsion: [baseRepulsion * 0.3, baseRepulsion * 3], 
                    // 改为数组：让 ECharts 根据 link.value 动态映射边长
                    edgeLength: [baseEdgeLength * 0.5, baseEdgeLength * 2.5], 
                    gravity: baseGravity, 
                    // 取消 initLayout，使用我们手动计算的 x, y 初始位置
                    layoutAnimation: true 
                },
                label: { show: true, position: 'right', color: '#fff', formatter: '{b}' },
                edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 8, lineStyle: { width: 2, curveness: 0.1 }
            }]
        });

        // 拖拽防抖逻辑保持不变
        try {
            let dragTimer = null;
            shared.chart2D.on && shared.chart2D.on('dragstart', params => {
                if (params && params.dataType === 'node') {
                    // 注意这里的 repulsion 也最好保持数组格式，或者直接给个中间值
                    shared.chart2D.setOption({ series: [{ force: { repulsion: [80, baseRepulsion], gravity: 0.5, layoutAnimation: false } }] }, false);
                    if (dragTimer) { clearTimeout(dragTimer); dragTimer = null; }
                }
            });
            shared.chart2D.on && shared.chart2D.on('dragend', params => {
                if (params && params.dataType === 'node') {
                    shared.chart2D.setOption({ series: [{ force: { repulsion: [baseRepulsion * 0.3, baseRepulsion * 3], gravity: baseGravity, layoutAnimation: true } }] }, false);
                    if (dragTimer) clearTimeout(dragTimer);
                    dragTimer = setTimeout(() => {
                        try { shared.chart2D.setOption({ series: [{ force: { layoutAnimation: false } }] }, false); } catch (e) {}
                        dragTimer = null;
                    }, 900);
                }
            });
        } catch (e) { /* ignore */ }
    }

    // 更新连线数据
    const ms = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, shared.startUtc) * 1000;
    const edges = [];
    shared.nodeInfoList.forEach((n1, i) => {
        shared.nodeInfoList.slice(i + 1).forEach(n2 => {
            const status = getLinkStatus(n1.id, n2.id, ms);
            if (status) {
                const type1 = getNodeType(n1.name);
                const type2 = getNodeType(n2.name);
                // 核心逻辑：卫星之间的连线极短(value小)，涉及GS/UAV的连线长(value大)
                const edgeValue = (type1 === 'SAT' && type2 === 'SAT') ? 10 : 100;
                edges.push({ source: String(n1.id), target: String(n2.id), status, value: edgeValue });
            }
        });
    });

    const currentEdgesString = JSON.stringify(edges.map(e => e.source + e.target + e.status).sort());
    if (currentEdgesString === shared.lastEdgesString) return;
    shared.lastEdgesString = currentEdgesString;

    // 渲染更新
    shared.chart2D.setOption({
        series: [{
            // 每次更新都重新获取节点的各项属性，确保固定的 GS 不会被力导向重置飘走
            data: shared.nodeInfoList.map((n, i) => generateNodeProps(n, i)),
            links: edges.map(e => ({ 
                source: e.source, 
                target: e.target, 
                value: e.value, // 传入控制边长的 value
                label: { show: true, formatter: e.status, color: '#00ff88', fontSize: 10 },
                lineStyle: { color: e.status.includes('up') ? '#00f2ff' : '#f1c40f', opacity: 0.8, width: 2 }
            }))
        }]
    }, false);
}
