"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.notifyRewardCatalogUpdated = exports.REWARD_CATALOG_UPDATED = void 0;
exports.REWARD_CATALOG_UPDATED = 'reward-catalog-updated';
const notifyRewardCatalogUpdated = () => {
    window.dispatchEvent(new Event(exports.REWARD_CATALOG_UPDATED));
};
exports.notifyRewardCatalogUpdated = notifyRewardCatalogUpdated;
