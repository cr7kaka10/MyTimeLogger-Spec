import { useEffect, useState } from 'react'
import { getNotificationRuntime } from '../../platform/notificationRuntime'
import type { NotificationSettings as Settings } from '../../platform/notificationPreferences'

type MorningStatus = { enabled: boolean; permission: boolean; exactAlarm: boolean; next: string; lastResult: string; lastAt: string }
const morningBridge = () => (window as any).MorningMotivationBridge as undefined | { status(): string; setEnabled(value: boolean): void; trial(): boolean }

const labels: Array<[keyof Settings, string]> = [
  ['master', '桌面通知'], ['timer', '计时结束'], ['achievements', '目标成就'], ['rewards', '金币与奖励'], ['account', '账户状态'], ['foreground', '前台也显示系统通知'],
]

export function NotificationSettings() {
  const [settings, setSettings] = useState<Settings | null>(null); const [permission, setPermission] = useState('unknown')
  const [morning, setMorning] = useState<MorningStatus | null>(null)
  const refreshMorning = () => { try { const native = morningBridge(); if (native) setMorning(JSON.parse(native.status())) } catch { setMorning(null) } }
  const runtime = getNotificationRuntime()
  useEffect(() => { if (runtime) { void runtime.preferences.getSettings().then(setSettings); void runtime.notifications.permissionStatus().then(setPermission) }; refreshMorning() }, [runtime])
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
    {morning && <div className="border-t border-gray-100 px-4 py-3 text-sm text-gray-700">
      <label className="flex items-center justify-between font-medium">每天 07:30 激励提醒
        <input type="checkbox" checked={morning.enabled} onChange={event => { morningBridge()?.setEnabled(event.target.checked); refreshMorning() }} className="h-5 w-5 accent-blue-600" />
      </label>
      <p className="mt-2 text-xs">通知权限：{morning.permission ? '已开启' : '未开启'} · 精确闹钟：{morning.exactAlarm ? '已允许' : '未允许，可能延迟'}</p>
      <p className="mt-1 text-xs">下次排程：{morning.enabled ? `北京时间 ${morning.next}` : '已关闭'} · 最近投递：{morning.lastResult}{morning.lastAt ? `（${morning.lastAt}）` : ''}</p>
      <button type="button" className="mt-2 rounded-lg border border-blue-200 px-3 py-1 text-blue-600" onClick={() => { morningBridge()?.trial(); refreshMorning() }}>试发激励通知</button>
    </div>}
  </section>
}
