"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const rewardCatalogRefresh_1 = require("./rewardCatalogRefresh");
const assert = (value, message) => { if (!value)
    throw new Error(message); };
const emitted = [];
Object.assign(globalThis, { window: { dispatchEvent: (event) => emitted.push(event.type) } });
(0, rewardCatalogRefresh_1.notifyRewardCatalogUpdated)();
assert(rewardCatalogRefresh_1.REWARD_CATALOG_UPDATED === 'reward-catalog-updated', 'reward catalog refresh event has a stable name');
assert(emitted.length === 1 && emitted[0] === rewardCatalogRefresh_1.REWARD_CATALOG_UPDATED, 'successful reward saves notify the backpack exactly once');
console.log('useRewards refresh contracts passed');
