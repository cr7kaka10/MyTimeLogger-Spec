import { useEffect, useState } from 'react'
import { getNotificationRuntime } from '../../platform/notificationRuntime'
import type { NotificationSettings as Settings } from '../../platform/notificationPreferences'

const labels: Array<[keyof Settings, string]> = [
  ['master', '桌面通知'], ['timer', '计时结束'], ['achievements', '目标成就'], ['rewards', '金币与奖励'], ['account', '账户状态'], ['foreground', '前台也显示系统通知'],
]

export function NotificationSettings() {
  const [settings, setSettings] = useState<Settings | null>(null); const [permission, setPermission] = useState('unknown')
  const runtime = getNotificationRuntime()
  useEffect(() => { if (runtime) { void runtime.preferences.getSettings().then(setSettings); void runtime.notifications.permissionStatus().then(setPermission) } }, [runtime])
  if (!runtime || !settings) return null
  const update = async (key: keyof Settings, checked: boolean) => {
    if (key === 'master' && checked) setPermission(await runtime.notifications.requestPermission().catch(() => 'unavailable'))
    setSettings(await runtime.preferences.updateSettings({ [key]: checked }))
  }
  const permissionText = permission === 'granted' ? '系统权限已允许' : permission === 'denied' ? '系统权限已拒绝，请到系统设置开启' : '首次通知时会请求系统权限'
  return <section className="overflow-hidden rounded-xl border border-gray-100 bg-white">
    <div className="flex items-center justify-between border-b border-gray-50 px-4 py-2">
      <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Android 通知</span>
      <span className="text-xs text-gray-400">{permissionText}</span>
    </div>
    {labels.map(([key, label]) => <label key={key} className="flex h-12 items-center justify-between border-b border-gray-50 px-4 last:border-0">
      <span className={key !== 'master' && !settings.master ? 'text-gray-300' : 'font-medium text-gray-900'}>{label}</span>
      <input type="checkbox" checked={settings[key]} disabled={key !== 'master' && !settings.master} onChange={event => { void update(key, event.target.checked) }} className="h-5 w-5 accent-blue-600" />
    </label>)}
  </section>
}
