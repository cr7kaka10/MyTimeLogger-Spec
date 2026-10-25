// ui/src/components/common/TabBar.tsx
// 底部导航栏组件 - 均分展示主要 tab
import { memo, useCallback } from 'react'
import { Settings } from 'lucide-react'
import type { MainTab } from '../../types'
import { TabIcon, type TabIconName } from './TabIcon'

interface TabBarProps {
  activeTab: MainTab
  onChange: (tab: MainTab) => void
}

// 主要导航 tab
const mainTabs: { id: TabIconName; label: string }[] = [
  { id: 'timer', label: '计时' },
  { id: 'timebook', label: '时间书' },
  { id: 'goals', label: '目标' },
  { id: 'learning', label: '学习' },
  { id: 'checklist', label: '清单' },
  { id: 'exercise', label: '运动' },
  { id: 'sleep', label: '睡眠' },
  { id: 'settings', label: '设置' },
]

export const TabBar = memo(({ activeTab, onChange }: TabBarProps) => {
  const handleClick = useCallback((tab: MainTab) => () => onChange(tab), [onChange])

  return (
    <nav className="safe-area-tabbar relative z-40 mx-auto flex w-full max-w-[480px] shrink-0 items-center border-t border-gray-100 bg-white">
      {/* 所有主标签均分空间，保持图标、标题与点击区域对齐 */}
      <div className="flex w-full items-center">
        {mainTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={handleClick(tab.id)}
            className={`flex min-h-11 flex-1 flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors ${
              activeTab === tab.id ? 'text-blue-600' : 'text-gray-400'
            }`}
          >
            {tab.id === 'settings' ? <Settings aria-hidden="true" size={20} strokeWidth={1.8} /> : <TabIcon name={tab.id} />}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
})

TabBar.displayName = 'TabBar'
