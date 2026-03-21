import * as echarts from 'echarts';
import * as Cesium from 'cesium';
import { shared } from './state.js';
import { getLinkStatus } from './utils.js';

export function update2DTopology(viewer) {
    const container = document.getElementById('topo-2d-container');
    if (!shared.state.showAnalytics || !container) {
        if (shared.chart2D) { shared.chart2D.clear(); shared.lastEdgesString = ""; }
        return;
    }

    if (!shared.chart2D) {
        shared.chart2D = echarts.init(container, 'dark');

        const nodeCount = shared.nodeInfoList.length || 1;
        const baseRepulsion = Math.min(2000, 600 + nodeCount * 18);
        const baseEdgeLength = Math.min(300, 120 + nodeCount * 4);
        const baseGravity = 0.15;
        const initialRadius = Math.min(600, 150 + nodeCount * 4);

        const initialNodesWithPos = shared.nodeInfoList.map((n, i) => {
            const angle = (i / nodeCount) * Math.PI * 2;
            const radius = initialRadius;
            return {
                id: String(n.id),
                name: n.name,
                x: Math.cos(angle) * radius,
                y: Math.sin(angle) * radius,
                symbolSize: 25
            };
        });

        shared.chart2D.setOption({
            backgroundColor: 'transparent',
            series: [{
                type: 'graph', layout: 'force', data: initialNodesWithPos, draggable: true, roam: true,
                force: { repulsion: baseRepulsion, edgeLength: baseEdgeLength, gravity: baseGravity, initLayout: 'circular', layoutAnimation: true },
                label: { show: true, position: 'right', color: '#fff', formatter: '{b}' },
                edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 8, lineStyle: { width: 2, curveness: 0.1 }
            }]
        });

        // 拖拽时降低抖动：监听拖拽开始/结束事件，调整力参数并在结束时短暂启用动画以加速收敛
        try {
            let dragTimer = null;
            shared.chart2D.on && shared.chart2D.on('dragstart', params => {
                if (params && params.dataType === 'node') {
                    shared.chart2D.setOption({ series: [{ force: { repulsion: Math.max(80, baseRepulsion * 0.5), gravity: 0.5, layoutAnimation: false } }] }, false);
                    if (dragTimer) { clearTimeout(dragTimer); dragTimer = null; }
                }
            });
            shared.chart2D.on && shared.chart2D.on('dragend', params => {
                if (params && params.dataType === 'node') {
                    // 恢复基础参数并短暂启用动画促进收敛
                    shared.chart2D.setOption({ series: [{ force: { repulsion: baseRepulsion, gravity: baseGravity, layoutAnimation: true } }] }, false);
                    if (dragTimer) clearTimeout(dragTimer);
                    dragTimer = setTimeout(() => {
                        try { shared.chart2D.setOption({ series: [{ force: { layoutAnimation: false } }] }, false); } catch (e) {}
                        dragTimer = null;
                    }, 900);
                }
            });
        } catch (e) { /* ignore if events not supported */ }
    }

    const ms = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, shared.startUtc) * 1000;
    const edges = [];
    shared.nodeInfoList.forEach((n1, i) => {
        shared.nodeInfoList.slice(i + 1).forEach(n2 => {
            const status = getLinkStatus(n1.id, n2.id, ms);
            if (status) edges.push({ source: String(n1.id), target: String(n2.id), status });
        });
    });

    const currentEdgesString = JSON.stringify(edges.map(e => e.source + e.target + e.status).sort());
    if (currentEdgesString === shared.lastEdgesString) return;
    shared.lastEdgesString = currentEdgesString;

    shared.chart2D.setOption({
        series: [{
            data: shared.nodeInfoList.map(n => ({ id: String(n.id), name: n.name, symbolSize: 25,
                itemStyle: { color: n.id === shared.state.currentTarget ? '#ff4757' : '#00f2ff', shadowBlur: n.id === shared.state.currentTarget ? 15 : 0, shadowColor: '#fff' }
            })),
            links: edges.map(e => ({ source: e.source, target: e.target, label: { show: true, formatter: e.status, color: '#00ff88', fontSize: 10 },
                lineStyle: { color: e.status.includes('up') ? '#00f2ff' : '#f1c40f', opacity: 0.8, width: 2 }
            }))
        }]
    }, false);
}
