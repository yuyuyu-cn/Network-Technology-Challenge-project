import * as Cesium from 'cesium';
import "cesium/Build/Cesium/Widgets/widgets.css";
import { shared } from './lib/state.js';
import { initSystem } from './lib/initSystem.js';
import { update2DTopology } from './lib/topo2d.js';

Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlNjdhNjdjZC1mMjA0LTQwMWEtYTcwYi02MTA5YWY5ZTZhYzEiLCJpZCI6Mzg4MDQ1LCJpYXQiOjE3NzA0Mzc0MTR9.Dfqi_zBqKJV_Yia-9waxWRMQ5VkYP4IAkQin7t5vVao';

const viewer = new Cesium.Viewer('app', {
    terrainProvider: null,
    baseLayerPicker: false, shouldAnimate: true,
    selectionIndicator: false, infoBox: false, navigationHelpButton: false,
    sceneModePicker: false, homeButton: false, geocoder: false
});

window.toggleOption = (type) => {
    if (type === 'ANA') {
        shared.state.showAnalytics = !shared.state.showAnalytics;
        const anaView = document.getElementById('analytics-view');
        const appView = document.getElementById('app');
        if (shared.state.showAnalytics) {
            // 仅呈现网络拓扑
            anaView.style.height = '40%'; appView.style.height = '60%';
            const right = document.getElementById('main-chart-right');
            if (right) right.style.display = 'none';
            setTimeout(() => { shared.chart2D?.resize(); update2DTopology(viewer); }, 400);
        } else {
            anaView.style.height = '0'; appView.style.height = '100%';
            const right = document.getElementById('main-chart-right');
            if (right) right.style.display = 'block';
        }
    }
};

// changeView no longer used (全局预览/跟踪已移除)
window.changeView = (mode) => {};

// 选择框现在仅作为视图模式开关：保存当前目标但不自动跟踪
window.selectTarget = (id) => {
    shared.state.currentTarget = id || null;
    if (!id) {
        // 取消持续跟随并回到总览视角（缩放至所有实体）
        viewer.trackedEntity = undefined;
        try { viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY); } catch (e) { /* ignore */ }
        try { viewer.zoomTo(viewer.entities); } catch (e) { /* ignore */ }
        return;
    }
    const target = shared.entityMap.get(id);
    if (target) {
        // 设置为持续跟随目标实体
        viewer.trackedEntity = target;
        // 指定一个较远的默认偏移，便于观察实体周围环境；若实体自带 viewFrom，可选择覆盖为更远距离
        const defaultViewFrom = new Cesium.Cartesian3(-800.0, -800.0, 450.0);
        try { viewer.trackedEntity.viewFrom = target.viewFrom || defaultViewFrom; } catch (e) { /* ignore */ }
    }
};

initSystem(viewer);

// 