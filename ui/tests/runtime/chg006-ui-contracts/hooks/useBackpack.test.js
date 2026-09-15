"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const backpackRefresh_1 = require("./backpackRefresh");
const assert = (value, message) => { if (!value)
    throw new Error(message); };
const previous = [{ id: 'item', title: '说明已更新', icon: '🎁', description: '商品说明', created_at: '2026-08-05', is_used: false }];
const normalized = (0, backpackRefresh_1.normalizeBackpackItems)([{ ...previous[0], description: null }]);
assert(backpackRefresh_1.BACKPACK_REFRESH_EVENTS.includes('reward-catalog-updated') && backpackRefresh_1.BACKPACK_REFRESH_EVENTS.includes('sync-pull-complete'), 'backpack refreshes after local catalog saves and remote sync');
assert(normalized[0].description === '' && normalized[0].is_used === false, 'backpack normalizes incomplete API payloads');
assert((0, backpackRefresh_1.preserveBackpackSnapshot)(previous) === previous, 'a failed refresh keeps the last successful inventory');
console.log('useBackpack refresh contracts passed');
