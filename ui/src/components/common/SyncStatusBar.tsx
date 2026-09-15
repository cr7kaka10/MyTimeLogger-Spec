import { memo, useEffect, useState } from 'react'
import { type SharedSyncState, type SharedSyncStatus } from '../../db'
import { formatBeijingDateTime } from '@core/BeijingTime'

const labels: Record<SharedSyncState, string> = {
  connecting: '连接中',
  syncing: '同步中',
  synced: '已同步',
  offline: '离线',
  failed: '同步失败',
}

const dotTones: Record<SharedSyncState, string> = {
  connecting: 'bg-amber-500',
  syncing: 'bg-blue-500',
  synced: 'bg-emerald-500',
  offline: 'bg-gray-400 dark:bg-gray-500',
  failed: 'bg-red-500',
}

const initialStatus = (): SharedSyncStatus => ({
  state: typeof navigator !== 'undefined' && navigator.onLine === false ? 'offline' : 'connecting',
  at: formatBeijingDateTime(),
})

export const SyncStatusBar = memo(() => {
  const [status, setStatus] = useState<SharedSyncStatus>(initialStatus)

  useEffect(() => {
    const update = (event: Event) => setStatus((event as CustomEvent<SharedSyncStatus>).detail)
    const pullComplete = () => setStatus({ state: 'synced', at: formatBeijingDateTime() })
    const online = () => setStatus({ state: 'connecting', at: formatBeijingDateTime() })
    const offline = () => setStatus({ state: 'offline', at: formatBeijingDateTime() })
    window.addEventListener('mtl:sync-status', update)
    window.addEventListener('sync-pull-complete', pullComplete)
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => {
      window.removeEventListener('mtl:sync-status', update)
      window.removeEventListener('sync-pull-complete', pullComplete)
      window.removeEventListener('online', online)
      window.removeEventListener('offline', offline)
    }
  }, [])

  const lastSuccess = status.state === 'synced' ? ` · ${status.at.slice(11)}` : ''
  return <div className="pointer-events-none inline-flex h-6 items-center rounded-md border border-gray-200/80 bg-white/75 px-1.5 text-[10px] font-semibold text-gray-600 backdrop-blur dark:border-gray-700 dark:bg-gray-800/75 dark:text-gray-200" aria-live="polite" title={`服务端-客户端${labels[status.state]}${status.error ? `：${status.error}` : ''}`}>
    <span className={`${status.state === 'syncing' ? 'animate-pulse' : ''} mr-1 inline-block h-1.5 w-1.5 rounded-full ${dotTones[status.state]}`} />
    {labels[status.state]}{lastSuccess}
  </div>
})

SyncStatusBar.displayName = 'SyncStatusBar'
