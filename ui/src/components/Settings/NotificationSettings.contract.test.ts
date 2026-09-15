import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const component = readFileSync(fileURLToPath(new URL('./NotificationSettings.tsx', import.meta.url)), 'utf8')
const page = readFileSync(fileURLToPath(new URL('./SettingsPage.tsx', import.meta.url)), 'utf8')
for (const text of ['桌面通知', '计时结束', '目标成就', '金币与奖励', '账户状态', '前台也显示系统通知']) assert(component.includes(text), `missing notification setting: ${text}`)
assert(component.includes('requestPermission') && component.includes('系统权限已拒绝'), 'permission state must be actionable')
assert(component.includes('runtime.preferences.updateSettings') && page.includes('<NotificationSettings />'), 'settings must use device-local notification preferences')
assert(!component.includes('updateSetting(') && !component.includes('getDatabase'), 'notification settings must not enter synced database settings')
console.log('notification settings contract passed')
