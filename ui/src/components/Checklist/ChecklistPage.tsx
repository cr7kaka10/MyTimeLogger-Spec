// ui/src/components/Checklist/ChecklistPage.tsx
import { memo, useCallback, useState, useEffect, useRef } from 'react'
import type { TaskItem } from '../../types'
import type { UseChecklistReturn } from '../../hooks/useChecklist'
import { getDatabase } from '../../db'
import { TaskEditDialog } from './TaskEditDialog'

const PRIORITY_MAP: Record<number, { label: string; color: string; badgeBg: string }> = {
  5: { label: '高', color: 'text-red-500 border-red-200 bg-red-50/50', badgeBg: 'bg-red-500' },
  3: { label: '中', color: 'text-orange-500 border-orange-200 bg-orange-50/50', badgeBg: 'bg-orange-500' },
  1: { label: '低', color: 'text-blue-500 border-blue-200 bg-blue-50/50', badgeBg: 'bg-blue-500' },
  0: { label: '无', color: 'text-gray-400 border-gray-200 bg-gray-50/50', badgeBg: 'bg-gray-400' },
}

interface ChecklistPageProps extends UseChecklistReturn {
  timer: any
  categories: any[]
  onNavigate: (tab: any) => void
  onOpenLedger?: () => void
}

export const ChecklistPage = memo(({
  tasks, isLoading, syncStatus,
  completeTask, deleteTask, refreshFromTickTick, updateTaskPriority, updateTask,
  timer, categories, onNavigate, onOpenLedger,
}: ChecklistPageProps) => {

  // 专注任务关联
  const [activeTaskId, setActiveTaskId] = useState<string | null>(() => {
    return localStorage.getItem('active_focus_task_id')
  })

  // 右键菜单状态
  const [contextMenu, setContextMenu] = useState<{
    show: boolean
    x: number
    y: number
    task: any | null
  }>({ show: false, x: 0, y: 0, task: null })

  // 弹窗状态
  const [showRewardModal, setShowRewardModal] = useState(false)
  const [rewardInput, setRewardInput] = useState({ coins: '0.1', penalty: '0.1' })

  const [showExclusiveModal, setShowExclusiveModal] = useState(false)
  const [exclusiveInput, setExclusiveInput] = useState({ title: '', icon: '🎁', description: '' })
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null)

  // 点击外部关闭右键菜单
  useEffect(() => {
    const closeMenu = () => setContextMenu(prev => prev.show ? { ...prev, show: false } : prev)
    window.addEventListener('click', closeMenu)
    return () => window.removeEventListener('click', closeMenu)
  }, [])

  // 保存 activeTaskId
  const updateActiveTaskId = (id: string | null) => {
    setActiveTaskId(id)
    if (id) {
      localStorage.setItem('active_focus_task_id', id)
    } else {
      localStorage.removeItem('active_focus_task_id')
    }
  }

  // 处理播放/暂停点击
  const handlePlayClick = useCallback(async (task: TaskItem) => {
    const db = await getDatabase()

    // 情况 1: 如果当前计时器正在专注该任务，点击则 toggle 暂停/恢复
    if (activeTaskId === task.id && timer.state !== 'stopped') {
      timer.togglePause()
      return
    }

    // 情况 2: 启动新专注
    // 匹配标签即分类名 (直接秒开，跳过分类选择弹窗)
    const matchedCat = categories.find(c => task.tags?.includes(c.name))

    if (matchedCat) {
      updateActiveTaskId(task.id)
      timer.start(matchedCat.id)
      onNavigate('timer')
    } else {
      // 弹出分类选择模态框，这里为了简化，我们直接弹出一个选择列表
      const catNames = categories.map(c => `${c.icon} ${c.name}`)
      const choice = prompt(`请选择任务「${task.title}」的专注分类:\n${catNames.map((n, i) => `${i + 1}. ${n}`).join('\n')}`)
      if (choice) {
        const idx = parseInt(choice, 10) - 1
        if (idx >= 0 && idx < categories.length) {
          const selectedCat = categories[idx]
          updateActiveTaskId(task.id)
          timer.start(selectedCat.id)
          onNavigate('timer')
        }
      }
    }
  }, [activeTaskId, timer, categories, onNavigate])

  // 任务完成处理
  const handleComplete = useCallback(async (task: TaskItem) => {
    // 如果该任务是正在专注的任务，先停掉计时器并清除焦点
    if (activeTaskId === task.id) {
      if (timer.state !== 'stopped') {
        timer.endSession()
      }
      updateActiveTaskId(null)
    }

    await completeTask(task)
  }, [activeTaskId, timer, completeTask])

  // 右键菜单触发
  const handleContextMenu = (e: React.MouseEvent, task: any) => {
    e.preventDefault()
    setContextMenu({
      show: true,
      x: e.clientX,
      y: e.clientY,
      task,
    })
  }

  // 弹出自定义奖励修改模态框
  const openRewardModal = () => {
    if (!contextMenu.task) return
    const t = contextMenu.task
    setRewardInput({
      coins: String(t.reward_coins ?? 0.1),
      penalty: String(t.penalty_coins ?? 0.1)
    })
    setShowRewardModal(true)
  }

  const saveRewardConfig = async () => {
    if (!contextMenu.task) return
    const db = await getDatabase()
    const coins = parseFloat(rewardInput.coins) || 0.1
    const penalty = parseFloat(rewardInput.penalty) || 0.1
    db.setItemReward('task', contextMenu.task.id, coins, penalty)
    setShowRewardModal(false)
    refreshFromTickTick() // 强刷加载
  }

  // 弹出专属奖励模态框
  const openExclusiveModal = () => {
    if (!contextMenu.task) return
    setExclusiveInput({
      title: `${contextMenu.task.title} 专属奖品`,
      icon: '🎁',
      description: `完成待办「${contextMenu.task.title}」解锁的专属限定奖励商品。`,
    })
    setShowExclusiveModal(true)
  }

  const saveExclusiveReward = async () => {
    if (!contextMenu.task) return
    const db = await getDatabase()
    // 添加价格为 0 的奖励，并绑定此任务ID作为 unlock_task_id
    db.addReward(
      exclusiveInput.title,
      exclusiveInput.icon,
      0 // 专属商品金币价格为0，只靠任务完成自动触发买入
    )

    // 获取刚才插入的奖励 ID，并把 unlock_task_id 和 unlock_task_title 更新上去
    const rewards = db.getRewards()
    const latestReward = rewards[rewards.length - 1]
    if (latestReward) {
      db.runRaw(
        `UPDATE rewards SET unlock_task_id = ?, unlock_task_title = ? WHERE id = ?`,
        [contextMenu.task.id, contextMenu.task.title, latestReward.id]
      )
    }

    setShowExclusiveModal(false)
    alert('专属奖励绑定成功！已加入商店，完成此任务后商品将自动送达背包 🎁')
  }

  return (
    <div className="min-h-full space-y-4 bg-[#FAFAFA] p-6 relative">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight">清单</h1>
          <div className="mt-2 text-sm text-gray-400">今日待办与 TickTick 同步</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refreshFromTickTick(true)}
            className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold text-blue-600 active:bg-blue-50 hover:bg-blue-50/50 transition-all"
            title="同步待办与习惯"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={(syncStatus?.includes('同步中') || syncStatus?.includes('正在')) ? 'animate-spin' : ''}>
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M16 3h5v5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M8 21H3v-5" />
            </svg>
          </button>
          {onOpenLedger && (
            <button
              type="button"
              onClick={onOpenLedger}
              className="flex min-h-11 items-center rounded-xl border border-gray-100 bg-white px-3 text-sm font-semibold hover:bg-amber-50 active:bg-amber-100 transition-all"
              title="金币流水"
            >
              💰
            </button>
          )}
        </div>
      </header>

      {tasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 bg-white rounded-2xl border border-gray-100/80 shadow-sm">
          <span className="text-5xl text-gray-300">☑</span>
          <p className="mt-4 text-sm font-medium text-gray-400">所有任务已消灭，今日非常充实！</p>
          <button
            type="button"
            onClick={() => refreshFromTickTick(true)}
            className="mt-4 rounded-xl bg-blue-500 px-5 py-2.5 text-sm font-semibold text-white shadow-md active:bg-blue-600 transition-colors"
          >
            拉取最新待办
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => {
            const pri = PRIORITY_MAP[task.priority] || PRIORITY_MAP[0]
            const isFocusing = activeTaskId === task.id && timer.state !== 'stopped'
            const isPaused = isFocusing && timer.isPaused
            const isCompleted = task.status === 2

            return (
              <div
                key={task.id}
                onContextMenu={(e) => handleContextMenu(e, task)}
                className={`grid min-h-16 w-full grid-cols-[36px_1fr_auto] items-center gap-3 rounded-2xl border p-4 shadow-sm transition-all duration-200 ${
                  isFocusing
                    ? 'border-blue-500 ring-2 ring-blue-500/20 bg-blue-50/10'
                    : isCompleted
                    ? 'border-green-300 bg-green-50/30 hover:bg-green-50/50'
                    : 'border-gray-100/80 hover:border-gray-200 bg-white'
                } ${task.is_overdue && !isCompleted ? 'border-l-4 border-l-red-500' : ''}`}
              >
                {/* 完成勾选框 */}
                <button
                  type="button"
                  onClick={() => handleComplete(task)}
                  className={`flex h-6 w-6 items-center justify-center rounded-full border active:scale-95 transition-all ${
                    isCompleted
                      ? 'border-green-500 bg-green-500 text-white hover:bg-green-600'
                      : 'border-gray-200 text-blue-600 hover:border-blue-500 hover:bg-blue-50/50'
                  }`}
                  title={isCompleted ? "取消完成" : "标记完成"}
                >
                  ✓
                </button>

                {/* 任务主体信息 */}
                <span className="min-w-0">
                  <span className={`block truncate font-semibold text-[15px] ${
                    isCompleted ? 'line-through text-gray-400 font-normal' : 'text-gray-800'
                  }`}>{task.title}</span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                    <button
                      type="button"
                      onContextMenu={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        if (isCompleted) return
                        const nextPriorities: Record<number, number> = { 5: 3, 3: 1, 1: 0, 0: 5 }
                        const nextPri = nextPriorities[task.priority] ?? 0
                        updateTaskPriority(task.id, nextPri)
                      }}
                      className={`inline-flex items-center px-1.5 py-0.5 rounded-md font-bold text-[10px] border active:scale-95 transition-all ${pri.color}`}
                      title="右键切换优先级"
                      disabled={isCompleted}
                    >
                      ⚑ {pri.label}
                    </button>
                    {task.reward_coins !== undefined && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-amber-50 text-amber-700 text-[10px] font-semibold border border-amber-100">
                        🪙 奖:{task.reward_coins} 惩:{task.penalty_coins}
                      </span>
                    )}
                    {task.due_date_full && (
                      <span className={`inline-flex items-center font-medium ${task.is_overdue && !isCompleted ? 'text-red-500 font-bold' : 'text-gray-400'}`}>
                        {task.is_overdue && !isCompleted ? '🔴 ' : '⏰ '}{task.due_date_full}
                      </span>
                    )}
                    {task.tags?.map((t: string) => (
                      <span key={t} className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-gray-50 border border-gray-100 text-gray-400 text-[10px] font-semibold">
                        🏷 {t}
                      </span>
                    ))}
                  </span>
                </span>

                {/* 右侧动作区 (播放计时联动) */}
                <div className="flex items-center gap-2">
                  {!isCompleted ? (
                    <button
                      type="button"
                      onClick={() => handlePlayClick(task)}
                      className={`flex h-8 w-8 items-center justify-center rounded-xl transition-all active:scale-90 shadow-sm ${
                        isFocusing
                          ? isPaused
                            ? 'bg-blue-500 text-white hover:bg-blue-600'
                            : 'bg-orange-500 text-white hover:bg-orange-600 animate-pulse'
                          : 'bg-blue-50 text-blue-600 hover:bg-blue-100/80'
                      }`}
                      title={isFocusing ? (isPaused ? '恢复专注' : '暂停专注') : '以此任务启动专注'}
                    >
                      {isFocusing ? (isPaused ? '▶' : '⏸') : '▶'}
                    </button>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 状态栏 */}
      <div className="text-center text-xs text-gray-400 mt-2 font-medium">
        {syncStatus} · {tasks.length} 条待办
      </div>

      {/* 自定义右键菜单 */}
      {contextMenu.show && (
        <div
          className="fixed z-50 min-w-40 rounded-xl bg-white border border-gray-100/80 shadow-xl p-1.5 animate-fadeIn"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            disabled={contextMenu.task.status === 2 || Boolean(contextMenu.task.repeat_flag) || !contextMenu.task.project_id}
            onClick={() => { setEditingTask(contextMenu.task); setContextMenu({ ...contextMenu, show: false }) }}
            className="flex w-full items-center px-3 py-2 text-xs font-semibold text-gray-700 rounded-lg hover:bg-blue-50 hover:text-blue-600 disabled:text-gray-400 disabled:hover:bg-transparent text-left transition-colors"
            title={contextMenu.task.status === 2 ? '已完成任务需在滴答清单中调整' : contextMenu.task.repeat_flag ? '重复任务需在滴答清单中调整' : !contextMenu.task.project_id ? '任务同步信息不完整' : '更新任务'}
          >
            ✎ {contextMenu.task.status === 2 ? '已完成任务需在滴答清单调整' : contextMenu.task.repeat_flag ? '重复任务需在滴答清单调整' : '更新任务'}
          </button>
          <button
            type="button"
            onClick={() => { setContextMenu({ ...contextMenu, show: false }); openRewardModal() }}
            className="flex w-full items-center px-3 py-2 text-xs font-semibold text-gray-700 rounded-lg hover:bg-blue-50 hover:text-blue-600 text-left transition-colors"
          >
            🪙 设置奖惩金币
          </button>
          <button
            type="button"
            onClick={() => { setContextMenu({ ...contextMenu, show: false }); openExclusiveModal() }}
            className="flex w-full items-center px-3 py-2 text-xs font-semibold text-gray-700 rounded-lg hover:bg-blue-50 hover:text-blue-600 text-left transition-colors"
          >
            🎁 绑定专属奖励
          </button>
          <div className="h-px bg-gray-100 my-1" />
          <button
            type="button"
            onClick={() => { setContextMenu({ ...contextMenu, show: false }); deleteTask(contextMenu.task.id) }}
            className="flex w-full items-center px-3 py-2 text-xs font-semibold text-red-600 rounded-lg hover:bg-red-50 text-left transition-colors"
          >
            🗑️ 物理删除待办
          </button>
        </div>
      )}

      <TaskEditDialog task={editingTask} onClose={() => setEditingTask(null)} onSave={updateTask} />

      {/* 奖惩金币设置模态框 */}
      {showRewardModal && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm animate-fadeIn" onClick={() => setShowRewardModal(false)}>
          <div className="w-full max-w-[480px] bg-white rounded-t-3xl p-6 space-y-4 shadow-2xl border-t border-gray-100" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-bold text-gray-900">设置金币奖惩</h3>
              <button onClick={() => setShowRewardModal(false)} className="text-gray-400 font-bold hover:text-gray-600">✕</button>
            </div>
            <p className="text-xs text-gray-400">为任务「{contextMenu.task?.title}」单独定制达标奖励及失败罚款。</p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1">完成奖励 (🪙)</label>
                <input
                  type="number"
                  step="0.1"
                  value={rewardInput.coins}
                  onChange={e => setRewardInput({ ...rewardInput, coins: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-gray-200 outline-none text-sm focus:border-blue-400 bg-gray-50 text-gray-800"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1">失败惩罚 (🪙)</label>
                <input
                  type="number"
                  step="0.1"
                  value={rewardInput.penalty}
                  onChange={e => setRewardInput({ ...rewardInput, penalty: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-gray-200 outline-none text-sm focus:border-blue-400 bg-gray-50 text-gray-800"
                />
              </div>
            </div>
            <button onClick={saveRewardConfig} className="w-full h-11 bg-blue-600 text-white font-semibold text-sm rounded-xl hover:bg-blue-700 shadow-md active:scale-98 transition-all">保存配置</button>
          </div>
        </div>
      )}

      {/* 绑定专属奖励模态框 */}
      {showExclusiveModal && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm animate-fadeIn" onClick={() => setShowExclusiveModal(false)}>
          <div className="w-full max-w-[480px] bg-white rounded-t-3xl p-6 space-y-4 shadow-2xl border-t border-gray-100" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-bold text-gray-900">绑定专属限定奖励</h3>
              <button onClick={() => setShowExclusiveModal(false)} className="text-gray-400 font-bold hover:text-gray-600">✕</button>
            </div>
            <p className="text-xs text-gray-400">为此任务量身定制一件奖品，任务完成后此奖品将自动购买并送入背包（免扣金币）。</p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1">奖品图标 (Emoji)</label>
                <input
                  type="text"
                  maxLength={2}
                  value={exclusiveInput.icon}
                  onChange={e => setExclusiveInput({ ...exclusiveInput, icon: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-gray-200 outline-none text-sm focus:border-blue-400 bg-gray-50 text-gray-800"
                  placeholder="如 🎁, 🎮, 🍰..."
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1">奖品标题</label>
                <input
                  type="text"
                  value={exclusiveInput.title}
                  onChange={e => setExclusiveInput({ ...exclusiveInput, title: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-gray-200 outline-none text-sm focus:border-blue-400 bg-gray-50 text-gray-800"
                  placeholder="如 爽玩 2 小时黑神话"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1">奖品描述</label>
                <textarea
                  value={exclusiveInput.description}
                  onChange={e => setExclusiveInput({ ...exclusiveInput, description: e.target.value })}
                  className="w-full px-3.5 py-2 rounded-xl border border-gray-200 outline-none text-sm focus:border-blue-400 bg-gray-50 text-gray-800 min-h-16"
                  placeholder="对奖品的解释或兑换规则描述..."
                />
              </div>
            </div>
            <button onClick={saveExclusiveReward} className="w-full h-11 bg-blue-600 text-white font-semibold text-sm rounded-xl hover:bg-blue-700 shadow-md active:scale-98 transition-all">创建并绑定</button>
          </div>
        </div>
      )}

    </div>
  )
})

ChecklistPage.displayName = 'ChecklistPage'
