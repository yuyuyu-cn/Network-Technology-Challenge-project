import * as Cesium from 'cesium';
import "cesium/Build/Cesium/Widgets/widgets.css";
import Papa from 'papaparse';
import * as echarts from 'echarts';

// --- 0. 基础配置 ---
Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlNjdhNjdjZC1mMjA0LTQwMWEtYTcwYi02MTA5YWY5ZTZhYzEiLCJpZCI6Mzg4MDQ1LCJpYXQiOjE3NzA0Mzc0MTR9.Dfqi_zBqKJV_Yia-9waxWRMQ5VkYP4IAkQin7t5vVao';

const startUtc = Cesium.JulianDate.fromIso8601("2026-01-27T12:00:00Z");
const state = { showTopology: true, showAnalytics: false, currentTarget: null, viewMode: 'OVERVIEW' };
const entityMap = new Map();
const topologyEvents = []; 
let nodeInfoList = []; 
let chart2D;
let lastEdgesString = "";

const viewer = new Cesium.Viewer('app', {
    terrainProvider: null, 
    baseLayerPicker: false, shouldAnimate: true,
    selectionIndicator: false, infoBox: false, navigationHelpButton: false,
    sceneModePicker: false, homeButton: false, geocoder: false
});
function update2DTopology() {
    const container = document.getElementById('topo-2d-container');
    
    // 1. 安全检查：如果未显示或容器不存在，清理并退出
    if (!state.showAnalytics || !container) {
        if (chart2D) { 
            chart2D.clear(); 
            lastEdgesString = ""; 
        }
        return;
    }

    // 2. 初始化 ECharts 实例
    if (!chart2D) {
        chart2D = echarts.init(container, 'dark');
        
        // 【核心改进】手动预计算节点位置，打破“排成一排”的物理初始状态
        const initialNodesWithPos = nodeInfoList.map((n, i) => {
            const angle = (i / nodeInfoList.length) * Math.PI * 2;
            const radius = 150; // 初始散开半径
            return {
                id: String(n.id),
                name: n.name,
                // 强制分配初始 x,y 坐标，让它们从圆周散开
                x: Math.cos(angle) * radius,
                y: Math.sin(angle) * radius,
                symbolSize: 25
            };
        });

        chart2D.setOption({
            backgroundColor: 'transparent',
            series: [{
                type: 'graph',
                layout: 'force', // 使用力导向布局
                data: initialNodesWithPos,
                draggable: true,
                roam: true,
                force: {
                    repulsion: 600,      // 节点之间的斥力
                    edgeLength: 150,     // 连线的平衡长度
                    gravity: 0.1,        // 向中心的引力
                    initLayout: 'circular',
                    layoutAnimation: true // 允许布局动画过渡
                },
                label: { 
                    show: true, 
                    position: 'right', 
                    color: '#fff',
                    formatter: '{b}' 
                },
                edgeSymbol: ['none', 'arrow'],
                edgeSymbolSize: 8,
                lineStyle: { width: 2, curveness: 0.1 }
            }]
        });
    }

    // 3. 计算当前时间的链路数据
    const ms = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, startUtc) * 1000;
    const edges = [];
    
    nodeInfoList.forEach((n1, i) => {
        nodeInfoList.slice(i + 1).forEach(n2 => {
            const status = getLinkStatus(n1.id, n2.id, ms);
            if (status) {
                edges.push({ source: String(n1.id), target: String(n2.id), status: status });
            }
        });
    });

    // 4. 增量更新检查：只有链路状态变了才执行 setOption
    const currentEdgesString = JSON.stringify(edges.map(e => e.source + e.target + e.status).sort());
    if (currentEdgesString === lastEdgesString) return; 
    lastEdgesString = currentEdgesString;

    // 5. 执行增量更新
    chart2D.setOption({
        series: [{
            // 更新节点颜色和高亮状态
            data: nodeInfoList.map(n => ({ 
                id: String(n.id), 
                name: n.name, 
                symbolSize: 25,
                itemStyle: { 
                    color: n.id === state.currentTarget ? '#ff4757' : '#00f2ff',
                    shadowBlur: n.id === state.currentTarget ? 15 : 0,
                    shadowColor: '#fff'
                }
            })),
            // 更新链路颜色和标签
            links: edges.map(e => ({
                source: e.source,
                target: e.target,
                label: { 
                    show: true, 
                    formatter: e.status, 
                    color: '#00ff88', 
                    fontSize: 10 
                },
                lineStyle: { 
                    color: e.status.includes('up') ? '#00f2ff' : '#f1c40f',
                    opacity: 0.8,
                    width: 2
                }
            }))
        }]
    }, false); // 设置为 false，不合并更新，保留已有节点坐标
}

function getLinkStatus(idA, idB, currentTimeMs) {
    const key = [String(idA), String(idB)].sort().join('---');
    const lastEvent = topologyEvents
        .filter(e => e.key === key && e.time <= currentTimeMs)
        .sort((a, b) => b.time - a.time)[0];
    return lastEvent ? lastEvent.status : null; 
}

// --- 2. 3D 链路系统 ---
function create3DLinks() {
    const polylines = viewer.scene.primitives.add(new Cesium.PolylineCollection());
    const visualLinks = [];
    const ids = Array.from(entityMap.keys());

    for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) {
            const line = polylines.add({
                show: false, width: 3.0,
                material: Cesium.Material.fromType('PolylineGlow', { glowPower: 0.1 })
            });
            visualLinks.push({ line, idA: ids[i], idB: ids[j] });
        }
    }

    viewer.scene.preRender.addEventListener(() => {
        const ms = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, startUtc) * 1000;
        visualLinks.forEach(link => {
            const p1 = entityMap.get(link.idA).position.getValue(viewer.clock.currentTime);
            const p2 = entityMap.get(link.idB).position.getValue(viewer.clock.currentTime);
            if (p1 && p2) {
                const status = getLinkStatus(link.idA, link.idB, ms);
                if (status) {
                    link.line.show = true;
                    link.line.positions = [p1, p2];
                    link.line.material.uniforms.color = status.includes('up') ? Cesium.Color.CYAN : Cesium.Color.YELLOW;
                } else { link.line.show = false; }
            } else { link.line.show = false; }
        });
        if (state.showAnalytics) update2DTopology();
    });
}

// --- 3. 核心初始化函数 ---
async function initSystem() {
    try {
        viewer.terrainProvider = await Cesium.createWorldTerrainAsync();
        viewer.scene.globe.depthTestAgainstTerrain = true;

        const [topoRes, traceRes, satRes] = await Promise.all([
            fetch('/mock_topology.csv').then(r => r.text()),
            fetch('/mock_trace.csv').then(r => r.text()),
            fetch('/mock_sat.csv').then(r => r.text())
        ]);

        Papa.parse(topoRes, { header: true, dynamicTyping: true, skipEmptyLines: true }).data.forEach(row => {
            if (row.source && row.target) {
                topologyEvents.push({
                    time: row.time_ms,
                    key: [String(row.source).trim(), String(row.target).trim()].sort().join('---'),
                    status: String(row.status).trim()
                });
            }
        });

        const traceRows = Papa.parse(traceRes, { header: true, dynamicTyping: true }).data;
        const satRows = Papa.parse(satRes, { header: true, dynamicTyping: true }).data;
        const combined = [...traceRows, ...satRows];
        
        const groups = new Map();
        let maxTimeMs = 0;

        combined.forEach(row => {
            if (!row.node_id) return;
            const id = String(row.node_id).trim();
            if (!groups.has(id)) {
                groups.set(id, []);
                nodeInfoList.push({ id, name: row.name || id });
                const sel = document.getElementById('node-selector');
                if (sel) {
                    const opt = document.createElement('option');
                    opt.value = id; opt.innerText = row.name || id;
                    sel.appendChild(opt);
                }
            }
            groups.get(id).push(row);
            maxTimeMs = Math.max(maxTimeMs, row.time_ms);
        });

        viewer.clock.startTime = startUtc.clone();
        viewer.clock.stopTime = Cesium.JulianDate.addSeconds(startUtc, maxTimeMs/1000, new Cesium.JulianDate());
        viewer.clock.currentTime = startUtc.clone();

        groups.forEach((rows, id) => {
            const posProp = new Cesium.SampledPositionProperty();
            
            // 【关键：平滑插值配置】
            posProp.setInterpolationOptions({
                interpolationDegree: 2,
                interpolationAlgorithm: Cesium.HermitePolynomialApproximation
            });

            let lastAddedTime = -1;
            const MIN_GAP_MS = 500; // 【关键：降频去抖动】
            const type = String(rows[0].type).toUpperCase();
            const isGS = type === 'GS' || type === 'GROUNDSTATION';

            rows.forEach(r => {
                // 只有移动节点需要降频，GS保持全部采样以防坐标丢失
                if (!isGS && lastAddedTime !== -1 && (r.time_ms - lastAddedTime < MIN_GAP_MS)) return;

                const t = Cesium.JulianDate.addSeconds(startUtc, r.time_ms / 1000, new Cesium.JulianDate());
                
                // 【关键：坐标取整去噪】
                let rawPos = new Cesium.Cartesian3(
                    Math.round(r.ecef_x * 100) / 100,
                    Math.round(r.ecef_y * 100) / 100,
                    Math.round(r.ecef_z * 100) / 100
                );

                // 【关键：GS高度修正，解决连线指空问题】
                if (isGS) {
                    const cartographic = Cesium.Cartographic.fromCartesian(rawPos);
                    // cartographic.height = 0; // 强制高度归零
                    rawPos = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, cartographic.height);
                }

                posProp.addSample(t, rawPos);
                lastAddedTime = r.time_ms;
            });

            const isSat = type.includes('SAT');
            const entity = viewer.entities.add({
                id: id,
                position: posProp,
                orientation: new Cesium.VelocityOrientationProperty(posProp),
                model: {
                    uri: isSat ? '/models/satellite.glb' : (isGS ? '/models/gs.glb' : '/models/uav.glb'),
                    minimumPixelSize: isSat ? 60 : 40,
                    heightReference: Cesium.HeightReference.NONE // 坐标已修正，不再使用贴地偏移
                },
                label: {
                    text: rows[0].name || id, font: '12px sans-serif',
                    pixelOffset: new Cesium.Cartesian2(0, -40),
                    outlineWidth: 2, style: Cesium.LabelStyle.FILL_AND_OUTLINE
                },
                path: isSat ? {
                    resolution: 1, width: 1,
                    material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.WHITE.withAlpha(0.4) }),
                    leadTime: 0, trailTime: 3600
                } : undefined
            });
            entityMap.set(id, entity);
        });

        create3DLinks();
        viewer.zoomTo(viewer.entities);

    } catch (e) { console.error("初始化失败:", e); }
}

// --- 4. 窗口接口 ---
window.toggleOption = (type) => {
    if (type === 'ANA') {
        state.showAnalytics = !state.showAnalytics;
        const anaView = document.getElementById('analytics-view');
        const appView = document.getElementById('app');
        if (state.showAnalytics) {
            anaView.style.height = '40%'; appView.style.height = '60%';
            setTimeout(() => { chart2D?.resize(); update2DTopology(); }, 400);
        } else {
            anaView.style.height = '0'; appView.style.height = '100%';
        }
    }
};

window.changeView = (mode) => {
    if (mode === 'OVERVIEW') {
        viewer.trackedEntity = undefined;
        viewer.zoomTo(viewer.entities);
    } else if (state.currentTarget) {
        viewer.trackedEntity = entityMap.get(state.currentTarget);
    }
};

window.selectTarget = (id) => {
    if (!id) return;
    state.currentTarget = id;
    const target = entityMap.get(id);
    if (target) {
        target.viewFrom = new Cesium.Cartesian3(-300.0, -300.0, 150.0);
        viewer.trackedEntity = target;
    }
};

initSystem();
// import * as Cesium from 'cesium';
// import "cesium/Build/Cesium/Widgets/widgets.css";
// import Papa from 'papaparse';
// import * as echarts from 'echarts';
//
// // --- 0. 配置 Token (已填入你提供的) ---
// Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlNjdhNjdjZC1mMjA0LTQwMWEtYTcwYi02MTA5YWY5ZTZhYzEiLCJpZCI6Mzg4MDQ1LCJpYXQiOjE3NzA0Mzc0MTR9.Dfqi_zBqKJV_Yia-9waxWRMQ5VkYP4IAkQin7t5vVao';
//
// // --- 1. 基础全局变量 ---
// const startUtc = Cesium.JulianDate.fromIso8601("2026-01-27T12:00:00Z");
// const state = { showTopology: true, showAnalytics: false, currentTarget: null, viewMode: 'OVERVIEW' };
// const entityMap = new Map();
// const topologyEvents = []; 
// let nodeInfoList = []; 
// let chart2D;
// let lastEdgesString = "";
//
// // 初始化 Viewer
// const viewer = new Cesium.Viewer('app', {
//     terrainProvider: null, // 异步加载
//     baseLayerPicker: false, shouldAnimate: true,
//     selectionIndicator: false, infoBox: false, navigationHelpButton: false,
//     sceneModePicker: false, homeButton: false, geocoder: false
// });
//
// // --- 2. 辅助工具函数 ---
//
// // 状态同步 UI
// function updateViewUI(mode) {
//     state.viewMode = mode;
//     const ovBtn = document.getElementById('view-ov');
//     const trackBtn = document.getElementById('view-track');
//     if (ovBtn && trackBtn) {
//         ovBtn.classList.toggle('active', mode === 'OVERVIEW');
//         trackBtn.classList.toggle('active', mode === 'FOLLOW');
//     }
// }
//
// // 获取链路状态逻辑 (核心算法)
// function getLinkStatus(idA, idB, currentTimeMs) {
//     const key = [String(idA), String(idB)].sort().join('---');
//     const lastEvent = topologyEvents
//         .filter(e => e.key === key && e.time <= currentTimeMs)
//         .sort((a, b) => b.time - a.time)[0];
//     return lastEvent ? lastEvent.status : null; 
// }
//
// // --- 3. 2D 拓扑图 (ECharts) ---
// function update2DTopology() {
//     const container = document.getElementById('topo-2d-container');
//     if (!state.showAnalytics || !container) {
//         if (chart2D) { chart2D.clear(); lastEdgesString = ""; }
//         return;
//     }
//     if (!chart2D) chart2D = echarts.init(container, 'dark');
//
//     const ms = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, startUtc) * 1000;
//     const edges = [];
//
//     nodeInfoList.forEach((n1, i) => {
//         nodeInfoList.slice(i + 1).forEach(n2 => {
//             const status = getLinkStatus(n1.id, n2.id, ms);
//             if (status) edges.push({ source: n1.id, target: n2.id, status });
//         });
//     });
//
//     const currentEdgesString = JSON.stringify(edges.map(e => e.source + e.target + e.status).sort());
//     if (currentEdgesString === lastEdgesString) return; 
//     lastEdgesString = currentEdgesString;
//
//     chart2D.setOption({
//         backgroundColor: 'transparent',
//         series: [{
//             type: 'graph', layout: 'force',
//             data: nodeInfoList.map(n => ({ 
//                 id: n.id, name: n.name, symbolSize: 20,
//                 itemStyle: { color: n.id === state.currentTarget ? '#fff' : '#00f2ff' }
//             })),
//             links: edges.map(e => ({
//                 source: e.source, target: e.target,
//                 label: { show: true, formatter: e.status, fontSize: 10 },
//                 lineStyle: { color: e.status.includes('up') ? '#00f2ff' : '#f1c40f', width: 2 }
//             })),
//             force: { repulsion: 300, edgeLength: 100 },
//             label: { show: true, position: 'right', color: '#fff' },
//             roam: true, animation: false
//         }]
//     }, true);
// }
//
// // --- 4. 3D 链路系统 ---
// function create3DLinks() {
//     const polylines = viewer.scene.primitives.add(new Cesium.PolylineCollection());
//     const visualLinks = [];
//     const ids = Array.from(entityMap.keys());
//
//     // 建立所有可能的两两组合
//     for (let i = 0; i < ids.length; i++) {
//         for (let j = i + 1; j < ids.length; j++) {
//             const line = polylines.add({
//                 show: false, width: 3.0,
//                 material: Cesium.Material.fromType('PolylineGlow', { glowPower: 0.1, color: Cesium.Color.CYAN })
//             });
//             visualLinks.push({ line, idA: ids[i], idB: ids[j] });
//         }
//     }
//
//     // 每一帧更新连线位置和颜色
//     viewer.scene.preRender.addEventListener(() => {
//         const ms = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, startUtc) * 1000;
//         visualLinks.forEach(link => {
//             const p1 = entityMap.get(link.idA).position.getValue(viewer.clock.currentTime);
//             const p2 = entityMap.get(link.idB).position.getValue(viewer.clock.currentTime);
//
//             if (p1 && p2) {
//                 const status = getLinkStatus(link.idA, link.idB, ms);
//                 if (status) {
//                     link.line.show = true;
//                     link.line.positions = [p1, p2];
//                     link.line.material.uniforms.color = status.includes('up') ? Cesium.Color.CYAN : Cesium.Color.YELLOW;
//                 } else { link.line.show = false; }
//             } else { link.line.show = false; }
//         });
//         if (state.showAnalytics) update2DTopology();
//     });
// }
//
// // --- 5. 初始化系统 (重点：多CSV读取与卫星轨迹) ---
// async function initSystem() {
//     try {
//         // 加载地形
//         viewer.terrainProvider = await Cesium.createWorldTerrainAsync();
//         viewer.scene.globe.depthTestAgainstTerrain = true;
//
//         // A. 读取所有 CSV
//         const [topoRes, traceRes, satRes] = await Promise.all([
//             fetch('/mock_topology.csv').then(r => r.text()),
//             fetch('/mock_trace.csv').then(r => r.text()),
//             fetch('/mock_sat.csv').then(r => r.text())
//         ]);
//
//         // B. 解析拓扑事件
//         Papa.parse(topoRes, { header: true, dynamicTyping: true, skipEmptyLines: true }).data.forEach(row => {
//             if (row.source && row.target) {
//                 topologyEvents.push({
//                     time: row.time_ms,
//                     key: [String(row.source).trim(), String(row.target).trim()].sort().join('---'),
//                     status: String(row.status).trim()
//                 });
//             }
//         });
//
//         // C. 处理节点数据 (合并卫星与无人机数据)
//         const traceRows = Papa.parse(traceRes, { header: true, dynamicTyping: true }).data;
//         const satRows = Papa.parse(satRes, { header: true, dynamicTyping: true }).data;
//         const combined = [...traceRows, ...satRows];
//
//         const groups = new Map();
//         let maxTimeMs = 0;
//
//         combined.forEach(row => {
//             if (!row.node_id) return;
//             const id = String(row.node_id).trim();
//             if (!groups.has(id)) {
//                 groups.set(id, []);
//                 nodeInfoList.push({ id, name: row.name || id });
//                 // 更新下拉框
//                 const sel = document.getElementById('node-selector');
//                 if(sel) {
//                     const opt = document.createElement('option');
//                     opt.value = id; opt.innerText = row.name || id;
//                     sel.appendChild(opt);
//                 }
//             }
//             groups.get(id).push(row);
//             maxTimeMs = Math.max(maxTimeMs, row.time_ms);
//         });
//
//         // 设置时钟
//         viewer.clock.startTime = startUtc.clone();
//         viewer.clock.stopTime = Cesium.JulianDate.addSeconds(startUtc, maxTimeMs/1000, new Cesium.JulianDate());
//         viewer.clock.currentTime = startUtc.clone();
//
//         // D. 生成 Entity
//         groups.forEach((rows, id) => {
//             const posProp = new Cesium.SampledPositionProperty();
//             posProp.setInterpolationOptions({
//                 interpolationDegree: 2, // 阶数，通常 2 或 5 比较平滑
//                 interpolationAlgorithm: Cesium.HermitePolynomialApproximation // 使用埃尔米特多项式
//             });
//             rows.forEach(r => {
//                 const t = Cesium.JulianDate.addSeconds(startUtc, r.time_ms / 1000, new Cesium.JulianDate());
//                 posProp.addSample(t, new Cesium.Cartesian3(r.ecef_x, r.ecef_y, r.ecef_z));
//             });
//
//             const type = String(rows[0].type).toUpperCase();
//             const isSat = type === 'SAT' || type === 'SATELLITE';
//             const isGS = type === 'GS';
//
//             const entity = viewer.entities.add({
//                 id: id,
//                 position: posProp,
//                 // 卫星和无人机自动转向速度方向
//                 orientation: new Cesium.VelocityOrientationProperty(posProp),
//                 model: {
//                     uri: isSat ? '/models/satellite.glb' : (isGS ? '/models/gs.glb' : '/models/uav.glb'),
//                     minimumPixelSize: isSat ? 60 : 40,
//                     // 地面站强制贴地
//                     heightReference: isGS ? Cesium.HeightReference.CLAMP_TO_GROUND : Cesium.HeightReference.NONE
//                 },
//                 label: {
//                     text: rows[0].name || id, font: '12px sans-serif',
//                     pixelOffset: new Cesium.Cartesian2(0, -40),
//                     outlineWidth: 2, style: Cesium.LabelStyle.FILL_AND_OUTLINE
//                 },
//                 // 卫星额外显示轨道路径
//                 path: isSat ? {
//                     resolution: 1, width: 1,
//                     material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.WHITE.withAlpha(0.4) }),
//                     leadTime: 0, trailTime: 3600
//                 } : undefined
//             });
//             entityMap.set(id, entity);
//         });
//
//         create3DLinks();
//         viewer.zoomTo(viewer.entities);
//
//     } catch (e) { console.error("初始化错误: ", e); }
// }
//
// // --- 6. 暴露给 HTML 的交互接口 ---
// window.toggleOption = (type) => {
//     if (type === 'TOPO') {
//         state.showTopology = !state.showTopology;
//         document.getElementById('toggle-topo')?.classList.toggle('on', state.showTopology);
//     } else if (type === 'ANA') {
//         state.showAnalytics = !state.showAnalytics;
//         const anaView = document.getElementById('analytics-view');
//         const appView = document.getElementById('app');
//         if (state.showAnalytics) {
//             anaView.style.height = '40%'; appView.style.height = '60%';
//             setTimeout(() => { chart2D?.resize(); update2DTopology(); }, 400);
//         } else {
//             anaView.style.height = '0'; appView.style.height = '100%';
//         }
//     }
// };
//
// window.changeView = (mode) => {
//     updateViewUI(mode);
//     if (mode === 'OVERVIEW') {
//         viewer.trackedEntity = undefined;
//         viewer.zoomTo(viewer.entities);
//     } else if (state.currentTarget) {
//         viewer.trackedEntity = entityMap.get(state.currentTarget);
//     }
// };
//
// window.selectTarget = (id) => {
//     if (!id) return;
//     state.currentTarget = id;
//     const target = entityMap.get(id);
//     if (target) {
//         viewer.trackedEntity = target;
//         updateViewUI('FOLLOW');
//     }
// };
//
// // 启动
// initSystem();
