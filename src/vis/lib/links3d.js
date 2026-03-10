import * as Cesium from 'cesium';
import { shared } from './state.js';
import { getLinkStatus } from './utils.js';
import { update2DTopology } from './topo2d.js';

export function create3DLinks(viewer) {
    const polylines = viewer.scene.primitives.add(new Cesium.PolylineCollection());
    const visualLinks = [];
    const ids = Array.from(shared.entityMap.keys());

    // 如果节点数量较大，避免创建 O(n^2) 的所有连线，改为仅创建出现在 topologyEvents 的连线
    const MAX_FULL_PAIRS = 120;
    let pairs = [];
    if (ids.length <= MAX_FULL_PAIRS) {
        for (let i = 0; i < ids.length; i++) {
            for (let j = i + 1; j < ids.length; j++) {
                pairs.push([ids[i], ids[j]]);
            }
        }
    } else {
        const idsSet = new Set(ids.map(String));
        const seen = new Set();
        for (const ev of shared.topologyEvents) {
            if (!ev || !ev.key) continue;
            if (seen.has(ev.key)) continue;
            const parts = ev.key.split('---');
            if (parts.length !== 2) continue;
            const [a, b] = parts;
            if (idsSet.has(a) && idsSet.has(b)) {
                pairs.push([a, b]);
                seen.add(ev.key);
            }
        }
    }

    for (const [a, b] of pairs) {
        const line = polylines.add({ show: false, width: 3.0, material: Cesium.Material.fromType('PolylineGlow', { glowPower: 0.12, color: Cesium.Color.WHITE }) });
        visualLinks.push({ line, idA: a, idB: b });
    }

    viewer.scene.preRender.addEventListener(() => {
        const ms = Cesium.JulianDate.secondsDifference(viewer.clock.currentTime, shared.startUtc) * 1000;
        for (const link of visualLinks) {
            const eA = shared.entityMap.get(link.idA);
            const eB = shared.entityMap.get(link.idB);
            const p1 = eA?.position?.getValue ? eA.position.getValue(viewer.clock.currentTime) : undefined;
            const p2 = eB?.position?.getValue ? eB.position.getValue(viewer.clock.currentTime) : undefined;
            if (p1 && p2) {
                const status = getLinkStatus(link.idA, link.idB, ms);
                if (status) {
                    link.line.show = true;
                    link.line.positions = [p1, p2];
                    // 重新创建材质以安全更新颜色（避免直接修改可能不存在的 uniforms）
                    link.line.material = Cesium.Material.fromType('PolylineGlow', { glowPower: 0.12, color: status.includes('up') ? Cesium.Color.CYAN : Cesium.Color.YELLOW });
                } else {
                    link.line.show = false;
                }
            } else {
                link.line.show = false;
            }
        }
        if (shared.state.showAnalytics) update2DTopology(viewer);
    });
}
