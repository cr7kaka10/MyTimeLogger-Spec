import type { NotificationRoute } from './services'

const allowed = new Set<NotificationRoute>(['timer', 'sleep', 'goals', 'rewards', 'backpack', 'settings'])
export const normalizeNotificationRoute = (route: string): NotificationRoute | null => allowed.has(route as NotificationRoute) ? route as NotificationRoute : null

export function createNotificationNavigator(isAuthenticated: () => boolean, navigate: (route: NotificationRoute) => void) {
  let pending: NotificationRoute | null = null
  return {
    open(rawRoute: string) {
      const route = normalizeNotificationRoute(rawRoute); if (!route) return 'rejected' as const
      if (!isAuthenticated()) { pending = route; return 'pending' as const }
      navigate(route); return 'opened' as const
    },
    consumePending() {
      if (!pending || !isAuthenticated()) return null
      const route = pending; pending = null; navigate(route); return route
    },
  }
}
