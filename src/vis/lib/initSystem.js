import * as Cesium from 'cesium';
import Papa from 'papaparse';
import { shared } from './state.js';
import { create3DLinks } from './links3d.js';

export async function initSystem(viewer) {
    try {
        // 使用全球真实地形并开启深度测试（恢复地形起伏）
        viewer.terrainProvider = await Cesium.createWorldTerrainAsync();
        // 在 lib/initSystem.js 的 viewer.terrainProvider 附近添加：
        try {
            const buildingsTileset = await Cesium.createOsmBuildingsAsync();
            viewer.scene.primitives.add(buildingsTileset);
        } catch (error) {
            console.error("加载 3D 建筑失败:", error);
        }
        viewer.scene.globe.depthTestAgainstTerrain = true;

        const [topoRes, traceRes, satRes] = await Promise.all([
            fetch('/mock_topology.csv').then(r => r.text()),
            fetch('/mock_trace.csv').then(r => r.text()),
            fetch('/mock_sat.csv').then(r => r.text())
        ]);

        // 解析拓扑 CSV，字段参照：time_ms, src, dst, direction, distance_km, delay_ms,
        // jitter_ms, loss_pct, bw_mbps, max_queue_pkt, quality, status, type
        Papa.parse(topoRes, { header: true, dynamicTyping: true, skipEmptyLines: true }).data.forEach(row => {
            const src = row.src ? String(row.src).trim() : '';
            const dst = row.dst ? String(row.dst).trim() : '';
            if (!src || !dst) return;
            const time = Number(row.time_ms) || 0;
            const key = [src, dst].sort().join('---');
            const status = row.status ? String(row.status).trim().toLowerCase() : '';

            shared.topologyEvents.push({
                // 兼容现有工具函数（使用 time 与 key、status）并保留额外元数据
                time: time,
                key: key,
                status: status,
                src: src,
                dst: dst,
                direction: row.direction ? String(row.direction).trim().toUpperCase() : 'BIDIR',
                distance_km: row.distance_km != null ? Number(row.distance_km) : null,
                delay_ms: row.delay_ms != null ? Number(row.delay_ms) : null,
                jitter_ms: row.jitter_ms != null ? Number(row.jitter_ms) : null,
                loss_pct: row.loss_pct != null ? Number(row.loss_pct) : null,
                bw_mbps: row.bw_mbps != null ? Number(row.bw_mbps) : null,
                max_queue_pkt: row.max_queue_pkt != null ? Number(row.max_queue_pkt) : null,
                quality: row.quality ? String(row.quality).trim().toUpperCase() : null,
                type: row.type ? String(row.type).trim() : null
            });
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
                shared.nodeInfoList.push({ id, name: row.name || id });
            }
            groups.get(id).push(row);
            maxTimeMs = Math.max(maxTimeMs, row.time_ms);
        });

        viewer.clock.startTime = shared.startUtc.clone();
        viewer.clock.stopTime = Cesium.JulianDate.addSeconds(shared.startUtc, maxTimeMs/1000, new Cesium.JulianDate());
        viewer.clock.currentTime = shared.startUtc.clone();

        groups.forEach((rows, id) => {
            const posProp = new Cesium.SampledPositionProperty();
            posProp.setInterpolationOptions({ interpolationDegree: 2, interpolationAlgorithm: Cesium.HermitePolynomialApproximation });

            let lastAddedTime = -1;
            const MIN_GAP_MS = 500;
            const type = String(rows[0].type).toUpperCase();
            const isGS = type === 'GS' || type === 'GROUNDSTATION';

            rows.forEach(r => {
                if (!isGS && lastAddedTime !== -1 && (r.time_ms - lastAddedTime < MIN_GAP_MS)) return;
                const t = Cesium.JulianDate.addSeconds(shared.startUtc, r.time_ms / 1000, new Cesium.JulianDate());
                let rawPos = new Cesium.Cartesian3(
                    Math.round(r.ecef_x * 100) / 100,
                    Math.round(r.ecef_y * 100) / 100,
                    Math.round(r.ecef_z * 100) / 100
                );
                if (isGS) {
                    const cartographic = Cesium.Cartographic.fromCartesian(rawPos);
                    rawPos = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, cartographic.height);
                }
                posProp.addSample(t, rawPos);
                lastAddedTime = r.time_ms;
            });

            const typeFlag = String(rows[0].type).toUpperCase();
            const isSat = typeFlag.includes('SAT');
            const isGsFlag = typeFlag === 'GS' || typeFlag === 'GROUNDSTATION';

            const entity = viewer.entities.add({
                id: id,
                position: posProp,
                orientation: new Cesium.VelocityOrientationProperty(posProp),
                model: { 
                    uri: isSat ? '/models/satellite.glb' : (isGsFlag ? '/models/gs.glb' : '/models/uav.glb'), 
                    minimumPixelSize: isSat ? 60 : 40, 
                    heightReference: Cesium.HeightReference.NONE 
                },
                label: {
                    text: rows[0].name || id,
                    // 1. 换用更锐利的系统无衬线字体，并加上 bold (加粗)，能大幅减少细线条带来的边缘发虚
                    font: 'bold 48px Arial, Helvetica, sans-serif',
                
                    scale: 0.25,
                
                    // 2. 缩小描边宽度。之前的 outlineWidth: 8 太粗了，在 WebGL 中渲染很容易变成一团黑糊糊的边缘。降到 4 左右刚刚好。
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    outlineWidth: 4,
                    fillColor: Cesium.Color.WHITE,
                    outlineColor: Cesium.Color.BLACK.withAlpha(0.7), // 给描边加一点点透明度，让边缘过渡更柔和
                
                // 3. 极其关键：禁用深度测试。防止文字在旋转视角时陷入模型或地球内部产生锯齿和闪烁
                    disableDepthTestDistance: Number.POSITIVE_INFINITY, 
                
                    pixelOffset: new Cesium.Cartesian2(0, -40),
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM
                },
                path: isSat ? { 
                    resolution: 1, 
                    width: 1.2, 
                    material: new Cesium.PolylineGlowMaterialProperty({ color: Cesium.Color.WHITE.withAlpha(0.9), glowPower: 0.15 }), 
                    leadTime: 8, 
                    trailTime: 0 
                } :   undefined
            });
            shared.entityMap.set(id, entity);
        });

        // 3D 连线功能按需动态导入，避免因循环依赖或模块尚未初始化导致的 ReferenceError
        // 若要禁用则注释掉下面这段
        // try {
        //     import('./links3d.js').then(m => {
        //         if (m && typeof m.create3DLinks === 'function') m.create3DLinks(viewer);
        //     }).catch(err => console.warn('动态导入 create3DLinks 失败:', err));
        // } catch (e) {
        //     console.warn('创建 3D 连线失败:', e?.message || e);
        // }

        // 聚焦到在当前时间有位置的实体，避免 zoomTo 因缺失位置而聚焦到无关位置
        try {
            const now = viewer.clock.currentTime || shared.startUtc;
            const visibleEntities = [];
            for (const [nid, entity] of shared.entityMap.entries()) {
                try {
                    const p = entity.position && entity.position.getValue(now);
                    if (p) visibleEntities.push(entity);
                } catch (e) { /* ignore */ }
            }
            if (visibleEntities.length > 0) {
                viewer.zoomTo(visibleEntities);
            } else {
                viewer.camera.flyTo({ destination: Cesium.Rectangle.fromDegrees(-180, -90, 180, 90), duration: 1.2 });
            }
        } catch (e) {
            try { viewer.zoomTo(viewer.entities); } catch (err) { /* ignore */ }
        }

        // 动态刷新下拉选择器：只显示在当前时间有位置数据的实体
        const refreshSelector = () => {
            const sel = document.getElementById('node-selector');
            if (!sel) return;
            const current = viewer.clock.currentTime;
            const prev = sel.value;
            sel.innerHTML = '';
            const overview = document.createElement('option');
            overview.value = '';
            overview.innerText = 'Overview';
            sel.appendChild(overview);

            for (const [nid, entity] of shared.entityMap.entries()) {
                try {
                    const pos = entity.position && entity.position.getValue(current);
                    if (pos) {
                        const info = shared.nodeInfoList.find(n => n.id === nid) || { id: nid };
                        const opt = document.createElement('option');
                        opt.value = nid; opt.innerText = info.name || nid;
                        sel.appendChild(opt);
                    }
                } catch (e) {
                    // ignore entities that can't provide a value at current time
                }
            }

            if (prev) {
                const exists = Array.from(sel.options).some(o => o.value === prev);
                if (exists) sel.value = prev;
                else {
                    // 如果之前选中的目标不再可用，重置追踪
                    if (shared.state.currentTarget === prev) {
                        shared.state.currentTarget = null;
                        viewer.trackedEntity = undefined;
                    }
                }
            }
        };

        // 首次填充并在时钟进度上更新
        refreshSelector();
        viewer.clock.onTick.addEventListener(refreshSelector);

    } catch (e) { console.error("初始化失败:", e); }
}
