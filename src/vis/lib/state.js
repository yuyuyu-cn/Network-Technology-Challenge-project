import * as Cesium from 'cesium';

export const shared = {
    startUtc: Cesium.JulianDate.fromIso8601("2026-01-27T12:00:00Z"),
    state: { showTopology: true, showAnalytics: false, currentTarget: null, viewMode: 'OVERVIEW' },
    entityMap: new Map(),
    topologyEvents: [],
    nodeInfoList: [],
    chart2D: null,
    lastEdgesString: ""
};
