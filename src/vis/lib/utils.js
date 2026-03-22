import { shared } from './state.js';

export function getLinkStatus(idA, idB, currentTimeMs) {
    const key = [String(idA), String(idB)].sort().join('---');
    const lastEvent = shared.topologyEvents
        .filter(e => e.key === key && e.time <= currentTimeMs)
        .sort((a, b) => b.time - a.time)[0];
    return lastEvent ? lastEvent.status : null;
}
