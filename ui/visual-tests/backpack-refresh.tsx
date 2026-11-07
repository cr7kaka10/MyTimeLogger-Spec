import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BackpackPage } from '../src/components/Backpack/BackpackPage'
import type { UseBackpackReturn } from '../src/hooks/useBackpack'

function Fixture() {
  const [isRefreshing, setRefreshing] = useState(false)
  const [syncState, setSyncState] = useState<UseBackpackReturn['syncState']>('fresh')
  const props: UseBackpackReturn = {
    items: [
      { id: 'dev-card', title: '开发环境测试卡', icon: '🎁', created_at: '2026-10-13 18:00:00', is_used: false },
      { id: 'dev-used-card', title: '开发环境已使用卡', icon: '📱', created_at: '2026-10-13 18:00:00', is_used: true, used_at: '2026-10-13 18:10:00' },
    ],
    fragments: [], expiredFragments: [], events: [], isLoading: false, isRefreshing,
    hasMoreEvents: false, isLoadingMoreEvents: false, syncState,
    errorMessage: syncState === 'fresh' ? '' : '网络暂不可用，保留上次成功数据',
    lastSuccessfulAt: '2026-10-13 18:00:00', serverUrl: 'http://127.0.0.1:8000',
    useItem: async () => {}, discardItem: async () => {}, loadMoreEvents: async () => {}, refresh: async () => {},
  }
  return <>
    <button id="begin-refresh" onClick={() => setRefreshing(true)}>开始刷新</button>
    <button id="fail-refresh" onClick={() => { setRefreshing(false); setSyncState('stale') }}>模拟失败</button>
    <BackpackPage {...props} />
  </>
}

createRoot(document.getElementById('root')!).render(<Fixture />)
