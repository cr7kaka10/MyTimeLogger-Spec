import React from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import { RewardAddSheet } from '../src/components/Rewards/RewardAddSheet'

const reward = {
  id: 'visual-reward', title: '解锁手机', icon: '📱', price: 0, description: '1/7解锁手机碎片，获得7个碎片可以合成一张完整卡片', is_active: 1,
  redemption_mode: 'task' as const, inventory_mode: 'monthly' as const, inventory_limit: 10,
  unlock_required_count: 7, fulfillment_mode: 'fragment' as const, fragment_target_count: 7,
}

createRoot(document.getElementById('root')!).render(<React.StrictMode>
  <main className="min-h-screen bg-gray-100 dark:bg-gray-950">
    <RewardAddSheet reward={reward} onSave={async () => undefined} onClose={() => document.body.setAttribute('data-closed', 'true')} />
  </main>
</React.StrictMode>)
