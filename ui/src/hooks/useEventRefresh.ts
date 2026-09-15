/**
 * 监听指定 window 事件，返回刷新触发器
 * 用于在同步完成或余额变更后自动刷新 Hook 数据
 */
import { useEffect, useState } from 'react'

export function useEventRefresh(eventNames: readonly string[]): number {
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const eventKey = eventNames.join(',')

  useEffect(() => {
    const handler = () => setRefreshTrigger(prev => prev + 1)
    for (const name of eventNames) {
      window.addEventListener(name, handler)
    }
    return () => {
      for (const name of eventNames) {
        window.removeEventListener(name, handler)
      }
    }
  }, [eventKey])

  return refreshTrigger
}

/** 仅监听 sync-pull-complete 的便捷封装 */
export function useSyncRefresh(): number {
  return useEventRefresh(['sync-pull-complete'])
}
