// ui/src/components/common/TabBar.tsx
// 底部导航栏组件 - 包含主要 tab 和设置按钮
import { memo, useCallback } from 'react'
import type { MainTab } from '../../types'
import { TabIcon, type TabIconName } from './TabIcon'

interface TabBarProps {
  activeTab: MainTab
  onChange: (tab: MainTab) => void
}

// 主要导航 tab（不包含设置）
const mainTabs: { id: TabIconName; label: string }[] = [
  { id: 'timer', label: '计时' },
  { id: 'timebook', label: '时间书' },
  { id: 'learning', label: '学习' },
  { id: 'checklist', label: '清单' },
  { id: 'exercise', label: '运动' },
  { id: 'sleep', label: '睡眠' },
]

export const TabBar = memo(({ activeTab, onChange }: TabBarProps) => {
  const handleClick = useCallback((tab: MainTab) => () => onChange(tab), [onChange])

  return (
    <nav className="safe-area-tabbar fixed bottom-0 left-1/2 flex w-full max-w-[480px] -translate-x-1/2 items-center border-t border-gray-100 bg-white">
      {/* 主要导航 tab 区域 - 使用 flex-1 均分空间 */}
      <div className="flex flex-1 items-center">
        {mainTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={handleClick(tab.id)}
            className={`flex min-h-11 flex-1 flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors ${
              activeTab === tab.id ? 'text-blue-600' : 'text-gray-400'
            }`}
          >
            <TabIcon name={tab.id} />
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* 设置按钮 - 固定在右下角 */}
      <button
        type="button"
        onClick={handleClick('settings')}
        className={`flex h-16 w-[68px] flex-col items-center justify-center gap-1 border-l border-gray-100 text-[10px] font-medium transition-colors ${
          activeTab === 'settings' ? 'text-blue-600' : 'text-gray-400'
        }`}
        style={{ minWidth: '44px', minHeight: '44px' }}
        aria-label="设置"
        title="设置"
      >
        <TabIcon name="settings" />
        <span>设置</span>
      </button>
    </nav>
  )
})

TabBar.displayName = 'TabBar'
