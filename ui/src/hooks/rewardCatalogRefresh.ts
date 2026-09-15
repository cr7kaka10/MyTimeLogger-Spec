export const REWARD_CATALOG_UPDATED = 'reward-catalog-updated'

export const notifyRewardCatalogUpdated = () => {
  window.dispatchEvent(new Event(REWARD_CATALOG_UPDATED))
}
