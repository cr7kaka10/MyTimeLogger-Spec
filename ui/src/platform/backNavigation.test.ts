import { createBackNavigationService, runBackNavigation } from './backNavigation'
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const order: string[] = []
assert(runBackNavigation(() => { order.push('overlay'); return true }, () => { order.push('tab'); return true }) && order.join(',') === 'overlay', 'overlay should handle first and stop tab navigation')
assert(runBackNavigation(() => false, () => true), 'previous tab should handle after overlays')
let listener = () => {}; let registered = 0; let exited = 0
const app = { addListener: async (_event: 'backButton', next: () => void) => { registered++; listener = next; return { remove() {} } }, exitApp: () => { exited++ } }
createBackNavigationService('electron', app).subscribe(() => false)
assert(registered === 0, 'Electron must not register Android listener')
createBackNavigationService('capacitor-android', app).subscribe(() => false)
await Promise.resolve(); listener()
assert(registered === 1 && exited === 1, 'unhandled Android back should exit')
console.log('platform back navigation tests passed')
