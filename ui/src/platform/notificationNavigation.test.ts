import { createNotificationNavigator, normalizeNotificationRoute } from './notificationNavigation'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const navigated: string[] = []; let authenticated = false
const navigator = createNotificationNavigator(() => authenticated, route => navigated.push(route))
assert(normalizeNotificationRoute('javascript:alert(1)') === null && normalizeNotificationRoute('goals') === 'goals', 'only allowlisted routes accepted')
assert(navigator.open('rewards') === 'pending' && navigated.length === 0, 'logged-out tap must defer navigation')
authenticated = true
assert(navigator.consumePending() === 'rewards' && navigator.consumePending() === null, 'pending route is consumed exactly once after login')
assert(navigated.join() === 'rewards', 'legal route reaches expected tab')
assert(navigator.open('file:///etc/passwd') === 'rejected', 'arbitrary destinations are rejected')
console.log('notification navigation tests passed')
