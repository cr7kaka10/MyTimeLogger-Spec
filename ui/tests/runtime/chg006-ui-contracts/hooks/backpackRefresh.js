"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.preserveBackpackSnapshot = exports.normalizeBackpackItems = exports.BACKPACK_REFRESH_EVENTS = void 0;
exports.BACKPACK_REFRESH_EVENTS = ['reward-catalog-updated', 'sync-pull-complete'];
const normalizeBackpackItems = (items) => items.map(item => ({
    ...item,
    description: typeof item.description === 'string' ? item.description : '',
    is_used: Boolean(item.is_used),
}));
exports.normalizeBackpackItems = normalizeBackpackItems;
const preserveBackpackSnapshot = (previous) => previous;
exports.preserveBackpackSnapshot = preserveBackpackSnapshot;
