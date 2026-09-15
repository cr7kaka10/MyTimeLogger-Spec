// ui/src/pages/UnifiedChecklistPage/TaskSection.tsx
// 今日任务分组组件 - 根据选中日期筛选任务
import { memo, useCallback, useEffect, useState, useMemo } from 'react'
import type { TaskItem } from '../../types'
import { dateToShanghaiDateString, tickTickDateToShanghaiDateString } from '../../utils/shanghaiDate'
import { filterTasksForChecklistDate } from '../../utils/checklistFilter'
import { formatTaskFocusBlockedMessage } from '../../hooks/taskFocusRouting'
import { isTaskFocusActive } from './taskFocusState'
import { TaskEditDialog } from '../../components/Checklist/TaskEditDialog'
import { SourceRewardSummary } from '../../components/Rewards/SourceRewardSummary'
import { SourceRewardEditor } from '../../components/Rewards/SourceRewardEditor'

const PRIORITY_MAP: Record<number, { label: string; color: string; badgeBg: string }> = {
  5: { label: '高', color: 'text-red-500 border-red-200 bg-red-50/50', badgeBg: 'bg-red-500' },
  3: { label: '中', color: 'text-orange-500 border-orange-200 bg-orange-50/50', badgeBg: 'bg-orange-500' },
  1: { label: '低', color: 'text-blue-500 border-blue-200 bg-blue-50/50', badgeBg: 'bg-blue-500' },
  0: { label: '无', color: 'text-gray-400 border-gray-200 bg-gray-50/50', badgeBg: 'bg-gray-400' },
}

interface TaskSectionProps {
  tasks: TaskItem[]
  selectedDate: Date
  categories: any[]
  timer: any
  onNavigate: (tab: any) => void
  onComplete: (task: TaskItem) => Promise<void>
  onAdd: (title: string, dueDate: string) => Promise<void>
  onDelete: (taskId: string) => Promise<void>
  onUpdateTask: (task: TaskItem, patch: { title?: string; startDate?: string | null; dueDate?: string | null }) => Promise<{ status: string } | null>
  onUpdatePriority: (taskId: string, priority: number) => Promise<void>
  mode?: 'incomplete' | 'completed'
}

export const TaskSection = memo(({
  tasks,
  selectedDate,
  categories,
  timer,
  onNavigate,
  onComplete,
  onAdd,
  onDelete,
  onUpdateTask,
  onUpdatePriority,
  mode = 'incomplete'
}: TaskSectionProps) => {
  const [activeTaskId, setActiveTaskId] = useState<string | null>(() => {
    return localStorage.getItem('active_focus_task_id')
  })

  const [contextMenu, setContextMenu] = useState<{
    show: boolean
    x: number
    y: number
    task: any | null
  }>({ show: false, x: 0, y: 0, task: null })
  const [editor, setEditor] = useState<{ task: TaskItem | null } | null>(null)
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null)
  const [rewardTask, setRewardTask] = useState<TaskItem | null>(null)
  const [draftTitle, setDraftTitle] = useState('')
  const editorForm = editor ? <form className="mb-2 rounded-lg border p-2 dark:border-gray-700" onSubmit={(event) => { event.preventDefault(); const title = draftTitle.trim(); if (!title) return; void onAdd(title, dateToShanghaiDateString(new Date())); setEditor(null) }}><div className="flex gap-2"><input autoFocus value={draftTitle} onChange={event => setDraftTitle(event.target.value)} className="min-w-0 flex-1 rounded border px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100" placeholder="任务标题" aria-label="任务标题"/><button className="theme-accent-button rounded px-3 text-sm" type="submit">确认</button><button className="rounded px-2 text-sm dark:text-gray-200" type="button" onClick={() => setEditor(null)}>取消</button></div><p className="mt-1 text-xs text-gray-500 dark:text-gray-400">保存为 MyTimeLogger 原生任务，默认日期为北京时间今天</p></form> : null

  // 根据选中日期筛选任务（精确匹配：今天只显示今天的任务）
  const filteredTasks = useMemo(() => {
    console.log('=== TaskSection 过滤任务 ===')
    console.log('输入 tasks:', tasks)
    console.log('输入 selectedDate:', selectedDate)
    
    if (!tasks || !Array.isArray(tasks) || !selectedDate || !(selectedDate instanceof Date) || isNaN(selectedDate.getTime())) {
      console.warn('⚠️ tasks 数据无效或 selectedDate 无效')
      return []
    }

    try {
      const selectedDateStr = dateToShanghaiDateString(selectedDate)
      console.log('selectedDateStr (北京时间):', selectedDateStr)

      const filtered = filterTasksForChecklistDate(tasks, selectedDate).filter(task => {
        if (!task) {
          console.log('跳过空任务')
          return false
        }
        
        console.log('---')
        console.log('任务:', task.title)
        console.log('  ID:', task.id)
        console.log('  status:', task.status)
        console.log('  due_date:', task.due_date)
        
        const taskDateStr = tickTickDateToShanghaiDateString(task.due_date)
        console.log('  任务日期(北京时间):', taskDateStr)
        
        const match = taskDateStr === selectedDateStr
        console.log('  精确匹配:', match ? '✅ 是' : '❌ 否')
        return match
      })

      console.log('过滤后任务数量:', filtered.length)
      console.log('过滤后任务:', filtered)
      return filtered
    } catch (error) {
      console.error('TaskSection filter error:', error)
      return []
    }
  }, [tasks, selectedDate])

  // 按 status 分组任务（未完成 vs 已完成）
  const { incompleteTasks, completedTasks } = useMemo(() => {
    const incomplete = filteredTasks.filter(task => task.status !== 2)
    const completed = filteredTasks.filter(task => task.status === 2)
    
    console.log('=== 任务分组 ===')
    console.log('未完成任务数:', incomplete.length)
    console.log('已完成任务数:', completed.length)
    
    return {
      incompleteTasks: incomplete,
      completedTasks: completed,
    }
  }, [filteredTasks])

  // 更新活跃任务 ID
  const updateActiveTaskId = (id: string | null) => {
    setActiveTaskId(id)
    if (id) {
      localStorage.setItem('active_focus_task_id', id)
    } else {
      localStorage.removeItem('active_focus_task_id')
    }
  }

  const getMatchedCategory = useCallback((task: TaskItem) => (
    categories.find((c: any) => task.tags?.some(tag => tag.trim() === c.name))
  ), [categories])

  useEffect(() => {
    if (!activeTaskId) return
    const cleanup = window.setTimeout(() => {
      const task = tasks.find(item => item.id === activeTaskId)
      const category = task ? getMatchedCategory(task) : null
      if (!task || !isTaskFocusActive(activeTaskId, task.id, timer.state, timer.currentCategory?.id, category?.id, timer.currentNote, task.title)) updateActiveTaskId(null)
    }, 250)
    return () => window.clearTimeout(cleanup)
  }, [activeTaskId, getMatchedCategory, tasks, timer.currentCategory?.id, timer.currentNote, timer.state])

  // 处理播放/暂停点击
  const handlePlayClick = useCallback(async (task: TaskItem) => {
    const matchedCat = getMatchedCategory(task)

    const currentFocus = isTaskFocusActive(activeTaskId, task.id, timer.state, timer.currentCategory?.id, matchedCat?.id, timer.currentNote, task.title)
    if (currentFocus) {
      timer.togglePause()
      return
    }

    let category = matchedCat
    if (!category) {
      const catNames = categories.map((c: any) => `${c.icon} ${c.name}`)
      const choice = prompt(`请选择任务「${task.title}」的专注分类:\n${catNames.map((n, i) => `${i + 1}. ${n}`).join('\n')}`)
      if (choice) {
        const idx = parseInt(choice, 10) - 1
        if (idx >= 0 && idx < categories.length) category = categories[idx]
      }
    }
    if (!category) return
    const result = await timer.requestTaskFocus(category.id, task.title)
    if (result.status === 'blocked') return alert(formatTaskFocusBlockedMessage(result.sourceCategoryName))
    if (result.status === 'unavailable') return alert('无法启动专注：计时分类或引擎不可用')
    updateActiveTaskId(task.id)
    onNavigate('timer')
  }, [activeTaskId, timer, categories, getMatchedCategory, onNavigate])

  // 任务完成处理
  const handleComplete = useCallback(async (task: TaskItem) => {
    if (activeTaskId === task.id) {
      if (timer.state !== 'stopped') {
        timer.endSession()
      }
      updateActiveTaskId(null)
    }
    await onComplete(task)
  }, [activeTaskId, timer, onComplete])

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

  // 获取日期显示文本
  const getDateLabel = () => {
    try {
      if (!selectedDate || !(selectedDate instanceof Date) || isNaN(selectedDate.getTime())) {
        return '今天 任务'
      }

      const selectedDateStr = dateToShanghaiDateString(selectedDate)
      const today = dateToShanghaiDateString(new Date())

      if (selectedDateStr === today) {
        return '今天 任务'
      }

      const displayMonth = selectedDate.getMonth() + 1
      const displayDay = selectedDate.getDate()
      return `${displayMonth}月${displayDay}日 任务`
    } catch (error) {
      console.error('getDateLabel error:', error)
      return '今天 任务'
    }
  }

  if (filteredTasks.length === 0 && mode === 'incomplete') {
    return (
      <div className="theme-surface rounded-xl border p-3 shadow-sm">
        <div className="mb-2 flex items-center justify-between px-1"><h3 className="text-sm font-bold text-gray-700">{getDateLabel()}</h3><button type="button" aria-label="添加任务" title="添加 MyTimeLogger 原生任务" className="theme-accent-button rounded-md px-2" onClick={() => { setDraftTitle(''); setEditor({ task: null }) }}>＋</button></div>{editorForm}
        <div className="flex items-center justify-center gap-2 py-2">
          <span className="text-xl text-gray-300">☑</span>
          <p className="text-xs font-medium text-gray-400">暂无任务</p>
        </div>
      </div>
    )
  }

  if (mode === 'completed' && completedTasks.length === 0) {
    return null // 已完成为空时不渲染任何内容
  }

  const tasksToRender = mode === 'incomplete' ? incompleteTasks : completedTasks

  if (mode === 'completed') {
    return (
      <div className="space-y-2" role="region" aria-label="已完成任务">
        {tasksToRender.map((task) => {
          const pri = PRIORITY_MAP[task.priority] || PRIORITY_MAP[0]
          const matchedCat = getMatchedCategory(task)

          return (
            <div
              key={task.id}
              onContextMenu={(e) => handleContextMenu(e, task)}
              className="grid min-h-12 w-full grid-cols-[28px_1fr_auto] items-center gap-2 rounded-xl border border-green-300 bg-green-50/30 p-2.5 opacity-80 shadow-sm transition-all duration-200 hover:bg-green-50/50"
            >
              {/* 完成勾选框 */}
              <button
                type="button"
                onClick={() => handleComplete(task)}
                className="flex h-5 w-5 items-center justify-center rounded-full border border-green-500 bg-green-500 text-[11px] text-white transition-all hover:bg-green-600 active:scale-95"
                title="取消完成"
                aria-label={`取消完成任务：${task.title}`}
                aria-pressed={true}
              >
                ✓
              </button>

              {/* 任务主体信息 */}
              <span className="min-w-0">
                <span className="block truncate text-sm font-normal leading-5 text-gray-500 line-through">
                  {task.title}
                </span>
                <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded-md font-bold text-[10px] border ${pri.color} opacity-60`}>
                    ⚑ {pri.label}
                  </span>
                  {task.due_date_full && (
                    <span className="inline-flex items-center font-medium text-gray-400">
                      ⏰ {task.due_date_full}
                    </span>
                  )}
                  {task.tags?.map(tag => (
                    <span
                      key={tag}
                      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold opacity-70 ${
                        matchedCat?.name === tag
                          ? 'border-blue-200 bg-blue-50 text-blue-600'
                          : 'border-gray-200 bg-gray-50 text-gray-500'
                      }`}
                      title={matchedCat?.name === tag ? '任务所属计时分类' : '滴答清单标签'}
                    >
                      # {tag}
                    </span>
                  ))}
                  <SourceRewardSummary sourceType="checklist_task" sourceId={task.id} compact onEdit={() => setRewardTask(task)} />
                  <span className="text-[10px] text-gray-400">{(task as any).source === 'local' || task.id.startsWith('local_') ? 'MyTimeLogger' : '滴答镜像'}</span>
                </span>
              </span>
            </div>
          )
        })}
        {/* 右键菜单 */}
        {contextMenu.show && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setContextMenu({ ...contextMenu, show: false })}
            />
            <div
              className="fixed z-50 min-w-40 rounded-xl bg-white border border-gray-100/80 shadow-xl p-1.5 animate-fadeIn"
              style={{ top: contextMenu.y, left: contextMenu.x }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                disabled
                className="flex w-full items-center px-3 py-2 text-xs font-semibold text-gray-400 text-left transition-colors"
                title="已完成任务需在滴答清单中调整"
              >
                ✏️ 已完成任务需在滴答清单调整
              </button>
              <button
                type="button"
                onClick={() => { setContextMenu({ ...contextMenu, show: false }); onDelete(contextMenu.task.id) }}
                className="flex w-full items-center px-3 py-2 text-xs font-semibold text-red-600 rounded-lg hover:bg-red-50 text-left transition-colors"
              >
                🗑️ 删除任务
              </button>
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2" role="region" aria-label={`${getDateLabel()}任务`}>
      <div className="flex items-center justify-between px-1"><h3 className="text-sm font-bold text-gray-700">{getDateLabel()}</h3><button type="button" aria-label="添加任务" title="添加 MyTimeLogger 原生任务" className="theme-accent-button rounded-md px-2" onClick={() => { setDraftTitle(''); setEditor({ task: null }) }}>＋</button></div>{editorForm}
      {tasksToRender.map((task) => {
        const pri = PRIORITY_MAP[task.priority] || PRIORITY_MAP[0]
        const matchedCat = getMatchedCategory(task)
        const isFocusing = isTaskFocusActive(activeTaskId, task.id, timer.state, timer.currentCategory?.id, matchedCat?.id, timer.currentNote, task.title)
        const isPaused = isFocusing && timer.isPaused
        const isCompleted = task.status === 2

        return (
          <div
            key={task.id}
            onContextMenu={(e) => handleContextMenu(e, task)}
            className={`grid min-h-12 w-full grid-cols-[28px_1fr_auto] items-center gap-2 rounded-xl border p-2.5 shadow-sm transition-all duration-200 ${
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
              className={`flex h-5 w-5 items-center justify-center rounded-full border text-[11px] transition-all active:scale-95 ${
                isCompleted
                  ? 'border-green-500 bg-green-500 text-white hover:bg-green-600'
                  : 'border-gray-200 text-blue-600 hover:border-blue-500 hover:bg-blue-50/50'
              }`}
              title={isCompleted ? "取消完成" : "标记完成"}
              aria-label={isCompleted ? `取消完成任务：${task.title}` : `标记完成任务：${task.title}`}
              aria-pressed={isCompleted}
            >
              ✓
            </button>

            {/* 任务主体信息 */}
            <span className="min-w-0">
              <span className={`block truncate text-sm font-semibold leading-5 ${
                isCompleted ? 'line-through text-gray-400 font-normal' : 'text-gray-800'
              }`}>{task.title}</span>
              <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                <button
                  type="button"
                  onContextMenu={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    if (isCompleted) return
                    const nextPriorities: Record<number, number> = { 5: 3, 3: 1, 1: 0, 0: 5 }
                    const nextPri = nextPriorities[task.priority] ?? 0
                    onUpdatePriority(task.id, nextPri)
                  }}
                  className={`inline-flex items-center px-1.5 py-0.5 rounded-md font-bold text-[10px] border active:scale-95 transition-all ${pri.color}`}
                  title="右键切换优先级"
                  disabled={isCompleted}
                >
                  ⚑ {pri.label}
                </button>
                {task.due_date_full && (
                  <span className={`inline-flex items-center font-medium ${task.is_overdue && !isCompleted ? 'text-red-500 font-bold' : 'text-gray-400'}`}>
                    {task.is_overdue && !isCompleted ? '🔴 ' : '⏰ '}{task.due_date_full}
                  </span>
                )}
                {task.tags?.map(tag => (
                  <span
                    key={tag}
                    className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${
                      matchedCat?.name === tag
                        ? 'border-blue-200 bg-blue-50 text-blue-600'
                        : 'border-gray-200 bg-gray-50 text-gray-500'
                    }`}
                    title={matchedCat?.name === tag ? '任务所属计时分类' : '滴答清单标签'}
                  >
                    # {tag}
                  </span>
                ))}
                <SourceRewardSummary sourceType="checklist_task" sourceId={task.id} compact onEdit={() => setRewardTask(task)} />
                <span className="text-[10px] text-gray-400">{(task as any).source === 'local' || task.id.startsWith('local_') ? 'MyTimeLogger' : '滴答镜像'}</span>
              </span>
            </span>

            {/* 右侧动作区 */}
            <div className="flex items-center gap-2">
              {!isCompleted ? (
                <button
                  type="button"
                  onClick={() => handlePlayClick(task)}
                  className={`flex h-7 w-7 items-center justify-center rounded-lg text-xs shadow-sm transition-all active:scale-90 ${
                    isFocusing
                      ? isPaused
                        ? 'bg-blue-500 text-white hover:bg-blue-600'
                        : 'bg-orange-500 text-white hover:bg-orange-600 animate-pulse'
                      : 'theme-accent-button bg-blue-50 text-blue-600 dark:text-blue-400 hover:bg-blue-100/80'
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

      {/* 移除旧的已完成任务折叠区域 */}

      {/* 右键菜单 */}
      {contextMenu.show && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setContextMenu({ ...contextMenu, show: false })}
          />
          <div
            className="fixed z-50 min-w-40 rounded-xl bg-white border border-gray-100/80 shadow-xl p-1.5 animate-fadeIn"
            style={{ top: contextMenu.y, left: contextMenu.x }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              disabled={Boolean(contextMenu.task.repeat_flag) || !contextMenu.task.project_id}
              onClick={() => { const task = contextMenu.task; setContextMenu({ ...contextMenu, show: false }); setEditingTask(task) }}
              className="flex w-full items-center px-3 py-2 text-xs font-semibold text-gray-700 rounded-lg hover:bg-gray-50 disabled:text-gray-400 disabled:hover:bg-transparent text-left transition-colors"
              title={contextMenu.task.repeat_flag ? '重复任务需在滴答清单中调整' : !contextMenu.task.project_id ? '任务同步信息不完整' : '更新任务'}
            >
              ✏️ {contextMenu.task.repeat_flag ? '重复任务需在滴答清单调整' : '更新任务'}
            </button>
            <button
              type="button"
              onClick={() => { setContextMenu({ ...contextMenu, show: false }); onDelete(contextMenu.task.id) }}
              className="flex w-full items-center px-3 py-2 text-xs font-semibold text-red-600 rounded-lg hover:bg-red-50 text-left transition-colors"
            >
              🗑️ 删除任务
            </button>
          </div>
        </>
      )}
      <TaskEditDialog task={editingTask} onClose={() => setEditingTask(null)} onSave={onUpdateTask} />
      {rewardTask && <SourceRewardEditor sourceType="checklist_task" sourceId={rewardTask.id} sourceTitle={rewardTask.title} onClose={() => setRewardTask(null)} />}
    </div>
  )
})

TaskSection.displayName = 'TaskSection'
