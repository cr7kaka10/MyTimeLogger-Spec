// ui/src/components/Timer/CategoryGrid.tsx
import { memo, useCallback, useMemo } from 'react'
import type { Category } from '../../types'
import type { TimerState } from '@core/LogicEngine'
import { CategoryIcon } from '../common/CategoryIcon'
import { isTimerCategoryGridBlocked } from '../../hooks/timerFocusGuard'

interface CategoryGridProps {
  categories: Category[]
  currentCategory: Category | null
  timerState: TimerState
  commandsEnabled?: boolean
  onStart: (id: number) => void
  onSwitch?: (id: number) => void
}

export const CategoryGrid = memo(({ categories, currentCategory, timerState, commandsEnabled = true, onStart, onSwitch }: CategoryGridProps) => {
  const sortedCategories = useMemo(() => [...categories]
    .filter(category => (category as Category & { is_active?: number }).is_active !== 0)
    .sort((a, b) => a.sort_order - b.sort_order), [categories])
  
  // 判断是否处于休息状态
  const isBreaking = useMemo(() => timerState === 'short_breaking', [timerState])
  
  // 处理分类点击事件
  const handleClick = useCallback(
    (categoryId: number) => () => {
      // 休息状态下不响应点击
      if (!commandsEnabled || isBreaking) return
      if (isTimerCategoryGridBlocked(currentCategory?.id, categoryId, currentCategory?.name, timerState)) return
      
      // 如果点击的是当前分类，不触发任何操作
      if (categoryId === currentCategory?.id) return
      
      // 如果有活跃分类且处于计时状态，调用 onSwitch 切换分类
      if (currentCategory && timerState !== 'stopped' && onSwitch) {
        onSwitch(categoryId)
      } else {
        // 否则直接启动新分类（包括 stopped 状态或 currentCategory 为 null 的情况）
        onStart(categoryId)
      }
    },
    [commandsEnabled, isBreaking, currentCategory, timerState, onSwitch, onStart]
  )
  
  return (
    <div className="grid grid-cols-5 gap-2">
      {sortedCategories.length === 0 ? (
        <div className="col-span-full flex min-h-32 items-center justify-center rounded-xl border border-dashed border-gray-200 px-4 text-center text-sm text-gray-400">
          暂无计时分类，请确认初始化示例数据已写入或当前环境已登录同步
        </div>
      ) : null}
      {sortedCategories.map((category) => {
        const focusBlocked = isTimerCategoryGridBlocked(currentCategory?.id, category.id, currentCategory?.name, timerState)
        const disabled = !commandsEnabled || isBreaking || focusBlocked
        return (
          <button
            key={category.id}
            type="button"
            onClick={handleClick(category.id)}
            disabled={disabled}
            aria-disabled={disabled}
            className={`flex min-h-20 flex-col items-center justify-center gap-2 rounded-xl border border-transparent text-center text-sm font-semibold text-gray-900 transition-all dark:text-gray-100 ${
              disabled
                ? 'cursor-not-allowed opacity-40 grayscale dark:opacity-35'
                : 'active:bg-gray-100 dark:active:bg-gray-700 md:hover:bg-gray-50 dark:md:hover:bg-gray-800'
            }`}
          >
            <CategoryIcon icon={category.icon} color={category.color} className="h-8 w-8" />
            <span className="line-clamp-1">{category.name}</span>
          </button>
        )
      })}
    </div>
  )
})

CategoryGrid.displayName = 'CategoryGrid'
