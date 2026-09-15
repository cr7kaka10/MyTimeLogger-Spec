import type { NotificationService } from './services'
import type { NotificationPreferences } from './notificationPreferences'
import { classifyNotificationEvents, externalNotificationKey, ledgerNotificationKey } from './notificationEvents'

type Facts = { external: any[]; ledger: any[] }
type Dependencies = { readFacts(): Facts | Promise<Facts>; preferences: NotificationPreferences; notifications: NotificationService; isForeground(): boolean }

export function createNotificationCoordinator(dependencies: Dependencies) {
  let queue = Promise.resolve()
  const run = async () => {
    const facts = await dependencies.readFacts()
    const keys = [...facts.external.map(externalNotificationKey), ...facts.ledger.map(ledgerNotificationKey)]
    const reconciliation = await dependencies.preferences.reconcileKeys(keys)
    if (reconciliation.baseline || !reconciliation.unseen.length) return { delivered: 0, baseline: reconciliation.baseline }
    const unseen = new Set(reconciliation.unseen)
    const batch = classifyNotificationEvents(
      facts.external.filter(item => unseen.has(externalNotificationKey(item))),
      facts.ledger.filter(item => unseen.has(ledgerNotificationKey(item))),
    )
    const settings = await dependencies.preferences.getSettings(); let delivered = 0
    for (const message of batch.notifications) {
      if (!settings.master || !settings[message.channel] || (dependencies.isForeground() && !settings.foreground)) continue
      try { if (await dependencies.notifications.notify(message) === 'delivered') delivered += 1 } catch { /* notifications never block business state */ }
    }
    await dependencies.preferences.markHandled(batch.handledKeys)
    return { delivered, baseline: false }
  }
  return { reconcile() { const result = queue.then(run, run); queue = result.then(() => {}, () => {}); return result } }
}

export type NotificationCoordinator = ReturnType<typeof createNotificationCoordinator>
