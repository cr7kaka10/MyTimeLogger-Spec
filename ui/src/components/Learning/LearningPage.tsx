import { memo, useEffect, useRef, useState } from 'react'
import type { MainTab } from '../../types'
import { useLearning, LearningObjective, LearningKR, LearningTask, LearningRuntime, type LearningCategory } from '../../hooks/useLearning'
import { AiCopilotDrawer } from './AiCopilotDrawer'
import { formatBeijingDate } from '@core/BeijingTime'
import { useChecklistTaskSubmission, type ChecklistTaskSubmission } from '../../hooks/useChecklistTaskSubmission'
import type { TaskFocusResult } from '../../hooks/taskFocusRouting'
import { SourceRewardSummary } from '../Rewards/SourceRewardSummary'
import { SourceRewardEditor } from '../Rewards/SourceRewardEditor'
import { useSourceRewards } from '../../hooks/useSourceRewards'

interface LearningPageProps {
  onNavigate: (tab: MainTab) => void
  onStartFocus: (categoryId: number | null, taskTitle: string) => Promise<TaskFocusResult>
  runtime?: LearningRuntime
}



const ProgressBar = ({ current, total }: { current: number; total: number }) => {
  const percent = total > 0 ? Math.round((current / total) * 100) : 0
  return (
    <div className="mt-2 w-full">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>进度</span>
        <span>{current} / {total} ({percent}%)</span>
      </div>
      <div className="h-2 w-full bg-gray-200 rounded-full overflow-hidden">
        <div 
          className="h-full bg-blue-500 rounded-full transition-all duration-500 ease-in-out"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  )
}

const ObjectiveRewardStatus = ({ objectiveId }: { objectiveId: string }) => {
  const { error, refresh } = useSourceRewards('learning_objective', objectiveId)
  if (!error) return null
  return <div className="mb-2 flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300">奖励暂未读取。<button type="button" onClick={() => void refresh().catch(() => undefined)} className="font-semibold underline">重试</button></div>
}

const createChecklistAttemptId = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`

const TaskItem = ({ task, index, onToggle, onRemove, onAddChecklist, submission, displayStatus, pending, actionError }: { task: LearningTask; index: number; onToggle: () => void | Promise<void>; onRemove: () => void; onAddChecklist: (task: LearningTask) => void; submission?: ChecklistTaskSubmission; displayStatus?: number; pending?: boolean; actionError?: string }) => {
  const isDone = (displayStatus ?? task.status) === 2
  const taskCategory = task.category_name === '输入' || task.category_name === '输出' ? task.category_name : null
  const compactActionClass = 'inline-flex h-7 items-center justify-center gap-1 rounded-md px-2.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2'
  const titleRef = useRef<HTMLParagraphElement>(null)
  const [isTitleOverflowing, setIsTitleOverflowing] = useState(false)
  const [showTitleTooltip, setShowTitleTooltip] = useState(false)
  const tooltipId = `learning-task-tooltip-${task.id}`

  const openTitleTooltip = () => {
    const title = titleRef.current
    const isOverflowing = !!title && title.scrollWidth > title.clientWidth
    setIsTitleOverflowing(isOverflowing)
    setShowTitleTooltip(isOverflowing)
  }
  
  // 优先级颜色映射
  const priorityColors: { [key: number]: string } = {
    0: 'text-gray-400',
    1: 'text-green-500',
    3: 'text-yellow-500',
    5: 'text-red-500',
  }
  
  const priorityLabels: { [key: number]: string } = {
    0: '无',
    1: '低',
    3: '中',
    5: '高',
  }
  
  return (
    <>
    <div className="group flex items-start gap-2.5 border-b border-gray-100 px-1 py-4 transition-colors last:border-b-0 hover:bg-blue-50/40 dark:border-gray-700/70 dark:hover:bg-blue-950/20 sm:px-2">
      <span className="flex h-5 min-w-5 flex-none items-center justify-center rounded-full bg-gray-100 px-1 text-[11px] font-semibold text-gray-500 dark:bg-gray-700 dark:text-gray-300" aria-label={`第 ${index} 项`}>{index}</span>
      <button 
        onClick={() => void onToggle()}
        disabled={pending}
        className={`mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-md border transition-colors focus:outline-none focus:ring-2 focus:ring-blue-300 dark:focus:ring-blue-700 ${
          isDone ? 'border-blue-500 bg-blue-500 text-white' : 'border-gray-300 bg-white hover:border-blue-400 dark:border-gray-600 dark:bg-gray-800'
        }`}
        aria-label={isDone ? '标记为未完成' : '标记为已完成'}
      >
        {isDone && <span className="text-xs">✓</span>}
      </button>
      <div className="min-w-0 flex-1">
        <div className="relative">
          <p ref={titleRef} tabIndex={0} aria-describedby={isTitleOverflowing ? tooltipId : undefined} onMouseEnter={openTitleTooltip} onMouseLeave={() => setShowTitleTooltip(false)} onFocus={openTitleTooltip} onBlur={() => setShowTitleTooltip(false)} className={`truncate text-sm leading-6 outline-none focus-visible:ring-2 focus-visible:ring-blue-300 dark:focus-visible:ring-blue-700 ${isDone ? 'text-gray-400 line-through dark:text-gray-500' : 'text-gray-800 dark:text-gray-100'}`}>{task.title}</p>
          {isTitleOverflowing && showTitleTooltip && (
            <div id={tooltipId} role="tooltip" className="pointer-events-none absolute left-0 top-7 z-50 w-80 max-w-[calc(100vw-6rem)] whitespace-normal break-words rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm leading-5 text-gray-800 shadow-xl dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100">
              {task.title}
            </div>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          {task.category_name && <span className="rounded-md bg-blue-50 px-2 py-1 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300" title="时间分组">📖 {task.category_name}</span>}
          {task.priority !== undefined && task.priority > 0 && <span className={`${priorityColors[task.priority]} rounded-md bg-gray-50 px-2 py-1 font-medium dark:bg-gray-700/70`} title="优先级">⚡ {priorityLabels[task.priority]}</span>}
          {!isDone && taskCategory && (pending ? <span className={`${compactActionClass} bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300`}>正在取消清单…</span> : <button type="button" onClick={() => onAddChecklist(task)} className={`${compactActionClass} bg-blue-500 text-white hover:bg-blue-600 focus:ring-blue-300 dark:focus:ring-blue-700`} title="加入今日清单">▣ {submission?.status === 'failed' ? '重试加入清单' : '加入清单'}</button>)}
          {isDone && pending && <span className={`${compactActionClass} bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300`}>正在加入清单…</span>}
          {isDone && !pending && submission?.status === 'confirmed' && <span className={`${compactActionClass} bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300`}>已加入清单</span>}
          <button type="button" disabled={pending} onClick={onRemove} className={`${compactActionClass} bg-red-600 text-white hover:bg-red-700 focus:ring-red-300 disabled:opacity-50 dark:bg-red-600 dark:hover:bg-red-500 dark:focus:ring-red-700`} title="删除任务" aria-label="删除任务">✕ 删除</button>
          {(submission?.status === 'failed' || actionError) && <span className="basis-full text-red-500">{actionError || submission?.error}</span>}
        </div>
      </div>
    </div>
    </>
  )
}

const KRCard = ({ kr, categories, isExpanded, onToggleExpanded, onAddTask, onToggleTask, onRemoveTask, onAddChecklist, submissions, statusOverrides, pendingTaskIds, actionErrors }: {
  kr: LearningKR; 
  categories: LearningCategory[];
  isExpanded: boolean;
  onToggleExpanded: () => void;
  onAddTask: (title: string, categoryId: number) => void;
  onToggleTask: (task: LearningTask) => void;
  onRemoveTask: (taskId: string, currentStatus: number) => void;
  onAddChecklist: (task: LearningTask) => void;
  submissions: Record<string, ChecklistTaskSubmission>;
  statusOverrides: Record<string, 0 | 2>;
  pendingTaskIds: Set<string>;
  actionErrors: Record<string, string>;
}) => {
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [newTaskCategory, setNewTaskCategory] = useState<'输入' | '输出'>('输入')
  const displayedStatus = (task: LearningTask) => statusOverrides[task.id] ?? task.status
  const completedCount = kr.tasks?.filter(task => displayedStatus(task) === 2).length ?? 0
  const taskCount = kr.tasks?.length ?? 0
  const optimisticDelta = kr.tasks?.reduce((total, task) => total + (displayedStatus(task) === 2 ? 1 : 0) - (task.status === 2 ? 1 : 0), 0) ?? 0
  const displayedCurrent = Math.max(0, Math.min(kr.target_value, kr.current_value + optimisticDelta))
  const percent = kr.target_value > 0 ? Math.round((displayedCurrent / kr.target_value) * 100) : 0

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault()
    const categoryId = categories.find(item => item.name === newTaskCategory)?.id
    if (!newTaskTitle.trim() || categoryId === undefined || categories.length !== 2) return
    onAddTask(newTaskTitle.trim(), categoryId)
    setNewTaskTitle('')
  }

  return (
    <section className={`${isExpanded ? 'mb-4 overflow-visible rounded-2xl shadow-sm hover:shadow-md' : 'mb-2 overflow-hidden rounded-xl shadow-sm'} border border-gray-200/80 bg-white transition-all dark:border-gray-700 dark:bg-gray-800/80`}>
      <button type="button" onClick={onToggleExpanded} aria-expanded={isExpanded} className={`flex w-full items-center gap-2.5 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/40 ${isExpanded ? 'px-4 pb-1 pt-4' : 'px-3 py-2'}`}>
        <span className={`flex h-5 w-5 flex-none items-center justify-center rounded-md bg-gray-100 text-base font-bold leading-none text-gray-500 transition-transform dark:bg-gray-700 dark:text-gray-300 ${isExpanded ? 'rotate-90' : ''}`}>›</span>
        <span className={`min-w-0 flex-1 text-sm font-bold leading-5 text-gray-900 dark:text-gray-100 ${isExpanded ? '' : 'truncate'}`} title={!isExpanded ? kr.title : undefined}>{kr.title}</span>
        <span className="flex-none rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-600 dark:bg-blue-900/30 dark:text-blue-300">{completedCount}/{taskCount}</span>
      </button>
      {isExpanded ? <div className="px-4 pb-3"><ProgressBar current={displayedCurrent} total={kr.target_value} /></div> : (
        <div className="mx-3 mb-2 h-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700" aria-label={`进度 ${percent}%`}>
          <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${percent}%` }} />
        </div>
      )}

      {isExpanded && <div className="border-t border-gray-100 px-4 pb-4 dark:border-gray-700/70">
        <div>
        {kr.tasks?.map((task, index) => (
          <TaskItem 
            key={task.id} 
            task={task}
            index={index + 1}
            onToggle={() => onToggleTask(task)}
            onRemove={() => onRemoveTask(task.id, task.status)}
            onAddChecklist={onAddChecklist}
            submission={submissions[`learning-${task.id}`]}
            displayStatus={displayedStatus(task)}
            pending={pendingTaskIds.has(task.id)}
            actionError={actionErrors[task.id]}
          />
        ))}
        </div>

      <form onSubmit={handleAddTask} className="mt-3 flex items-center gap-2 rounded-xl bg-gray-50 p-2 dark:bg-gray-900/30">
        <input 
          type="text" 
          value={newTaskTitle}
          onChange={(e) => setNewTaskTitle(e.target.value)}
          placeholder="添加最小执行单元..."
          className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm transition-colors focus:border-blue-400 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
        />
        <select value={newTaskCategory} onChange={event => setNewTaskCategory(event.target.value as '输入' | '输出')} className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800">
          <option value="输入">输入</option><option value="输出">输出</option>
        </select>
        <button 
          type="submit"
          disabled={!newTaskTitle.trim() || categories.length !== 2}
          className="rounded-lg bg-blue-500 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-600 disabled:opacity-40"
        >
          添加
        </button>
        {categories.length !== 2 && <span className="text-xs text-red-500">请先恢复输入/输出分类配置</span>}
      </form>
      </div>}
    </section>
  )
}

const ObjectiveCard = ({ objective, categories, onAddKR, onAddTask, onToggleTask, onRemoveTask, onAddChecklist, submissions, statusOverrides, pendingTaskIds, actionErrors, onOpenAi, onUpdate, onRemove, onOpenEdit }: {
  objective: LearningObjective; 
  categories: LearningCategory[];
  onAddKR: (title: string) => void;
  onAddTask: (krId: string, title: string, categoryId: number) => void;
  onToggleTask: (task: LearningTask) => void;
  onRemoveTask: (taskId: string, currentStatus: number, krId: string) => void;
  onAddChecklist: (task: LearningTask) => void;
  submissions: Record<string, ChecklistTaskSubmission>;
  statusOverrides: Record<string, 0 | 2>;
  pendingTaskIds: Set<string>;
  actionErrors: Record<string, string>;
  onOpenAi: (obj: LearningObjective) => void;
  onUpdate: (data: { title?: string; duration?: number; baseline?: string; target_description?: string }) => void;
  onRemove: () => void;
  onOpenEdit: () => void;
}) => {
  const [newKRTitle, setNewKRTitle] = useState('')
  const [showAddKR, setShowAddKR] = useState(false)
  const [expandedKrIds, setExpandedKrIds] = useState<Set<string>>(() => new Set(objective.krs?.map(kr => kr.id) ?? []))
  const [showRewardEditor, setShowRewardEditor] = useState(false)
  const krIds = objective.krs?.map(kr => kr.id) ?? []
  const allExpanded = krIds.length > 0 && krIds.every(id => expandedKrIds.has(id))

  useEffect(() => {
    setExpandedKrIds(current => {
      const next = new Set(current)
      krIds.forEach(id => next.add(id))
      return next
    })
  }, [objective.krs?.length])

  const toggleAllKrs = () => setExpandedKrIds(allExpanded ? new Set() : new Set(krIds))
  const toggleKr = (id: string) => setExpandedKrIds(current => {
    const next = new Set(current)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const handleRemoveObjective = () => {
    if (confirm(`确定要删除目标「${objective.title}」及其所有 KR 和子任务吗？\n此操作不可恢复！`)) {
      onRemove()
    }
  }

  const handleAddKR = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newKRTitle.trim()) return
    onAddKR(newKRTitle.trim())
    setNewKRTitle('')
    setShowAddKR(false)
  }

  return (
    <div className="relative mb-6">
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800/70 dark:bg-amber-950/35">
        <button type="button" onClick={toggleAllKrs} aria-expanded={allExpanded} aria-label={allExpanded ? '折叠全部 KR' : '展开全部 KR'} className="flex h-8 w-8 flex-none items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-amber-100/70 focus:outline-none focus:ring-2 focus:ring-amber-300 dark:text-gray-300 dark:hover:bg-amber-900/40 dark:focus:ring-amber-700" title={allExpanded ? '折叠全部 KR' : '展开全部 KR'}>
          <span className={`flex h-5 w-5 items-center justify-center rounded-md bg-gray-100 text-base font-bold leading-none text-gray-500 transition-transform dark:bg-gray-700 dark:text-gray-300 ${allExpanded ? 'rotate-90' : ''}`}>›</span>
        </button>
        <h3 className="min-w-[12rem] flex-1 basis-[12rem] break-words text-sm font-semibold leading-5 text-gray-900 dark:text-gray-100">
          {objective.title}
        </h3>
        <SourceRewardSummary sourceType="learning_objective" sourceId={objective.id} compact hideError onEdit={() => setShowRewardEditor(true)} />
        <div className="flex flex-none items-center gap-1">
          <button
            type="button"
            onClick={onOpenEdit}
            aria-label={`修改目标：${objective.title}`}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-sm text-gray-500 transition-colors hover:bg-amber-100/70 hover:text-blue-500 focus:outline-none focus:ring-2 focus:ring-amber-300 dark:text-gray-300 dark:hover:bg-amber-900/40 dark:focus:ring-amber-700"
            title="修改目标"
          >
            ✏️
          </button>
          <button
            type="button"
            onClick={handleRemoveObjective}
            aria-label={`删除目标：${objective.title}`}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-sm text-gray-500 transition-colors hover:bg-red-50 hover:text-red-500 focus:outline-none focus:ring-2 focus:ring-red-300 dark:text-gray-300 dark:hover:bg-red-950/40 dark:focus:ring-red-700"
            title="删除目标"
          >
            🗑️
          </button>
        </div>
        <button 
          type="button"
          onClick={() => onOpenAi(objective)}
          className="theme-accent-button group flex h-8 flex-none items-center gap-1 whitespace-nowrap rounded-full border border-blue-200 bg-white/80 px-2.5 text-sm font-medium text-blue-600 shadow-sm transition-all hover:bg-white dark:border-gray-600 dark:bg-gray-800/80 dark:text-blue-400"
        >
          <span className="group-hover:animate-pulse">✨</span> AI 智能拆解
        </button>
      </div>
      {showRewardEditor && <SourceRewardEditor sourceType="learning_objective" sourceId={objective.id} sourceTitle={objective.title} onClose={() => setShowRewardEditor(false)} />}
      <ObjectiveRewardStatus objectiveId={objective.id} />
      
      <div className="border-l-2 border-red-400 pl-4 dark:border-red-700 sm:pl-6">
        {objective.krs?.map(kr => (
          <KRCard 
            key={kr.id} 
            kr={kr} 
            categories={categories}
            isExpanded={expandedKrIds.has(kr.id)}
            onToggleExpanded={() => toggleKr(kr.id)}
            onAddTask={(title, categoryId) => onAddTask(kr.id, title, categoryId)}
            onToggleTask={onToggleTask}
            onRemoveTask={(taskId, status) => onRemoveTask(taskId, status, kr.id)}
            onAddChecklist={onAddChecklist}
            submissions={submissions}
            statusOverrides={statusOverrides}
            pendingTaskIds={pendingTaskIds}
            actionErrors={actionErrors}
          />
        ))}

        {!showAddKR ? (
          <button 
            onClick={() => setShowAddKR(true)}
            className="text-sm text-gray-500 hover:text-blue-500 flex items-center gap-1 transition-colors mt-2"
          >
            <span className="text-lg leading-none">+</span> 添加关键结果 (KR)
          </button>
        ) : (
          <form onSubmit={handleAddKR} className="mt-2 flex items-center gap-2">
            <input 
              type="text" 
              autoFocus
              value={newKRTitle}
              onChange={(e) => setNewKRTitle(e.target.value)}
              placeholder="输入 KR 标题..."
              className="flex-1 bg-white border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500 shadow-sm"
            />
            <button 
              type="submit"
              disabled={!newKRTitle.trim()}
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded text-sm transition-colors disabled:opacity-50 shadow-sm"
            >
              保存
            </button>
            <button 
              type="button"
              onClick={() => setShowAddKR(false)}
              className="bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 px-4 py-2 rounded text-sm transition-colors shadow-sm"
            >
              取消
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

// 新建目标 Modal 组件
const CreateObjectiveModal = ({ onClose, onCreate }: { onClose: () => void; onCreate: (data: { title: string; duration?: number; baseline?: string; target_description?: string }) => void }) => {
  const [title, setTitle] = useState('')
  const [duration, setDuration] = useState('')
  const [baseline, setBaseline] = useState('')
  const [targetDescription, setTargetDescription] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    
    onCreate({
      title: title.trim(),
      duration: duration ? parseInt(duration) : undefined,
      baseline: baseline.trim() || undefined,
      target_description: targetDescription.trim() || undefined,
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">创建新学习目标</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xl leading-none">✕</button>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 flex-1 overflow-y-auto">
          <div className="space-y-4">
            {/* 标题 - 必填 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                目标标题 <span className="text-red-500">*</span>
              </label>
              <input 
                type="text"
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如：深入掌握 React 高级特性"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            {/* 持续时长 - 可选 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                持续时长（天）
              </label>
              <input 
                type="number"
                min="1"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                placeholder="留空可让 AI 根据任务量推荐合理时长"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            {/* 当前现状 - 可选 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                当前现状
              </label>
              <textarea 
                rows={4}
                value={baseline}
                onChange={(e) => setBaseline(e.target.value)}
                placeholder="描述您目前对这个领域的了解程度..."
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors resize-none"
              />
            </div>

            {/* 预期目标 - 可选 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                预期目标
              </label>
              <textarea 
                rows={4}
                value={targetDescription}
                onChange={(e) => setTargetDescription(e.target.value)}
                placeholder="描述您希望达到的水平..."
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors resize-none"
              />
            </div>
          </div>
        </form>

        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
          <button 
            type="button"
            onClick={onClose}
            className="px-5 py-2.5 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors font-medium"
          >
            取消
          </button>
          <button 
            type="button"
            onClick={(e: any) => handleSubmit(e)}
            disabled={!title.trim()}
            className="px-5 py-2.5 text-sm text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium shadow-sm"
          >
            创建
          </button>
        </div>
      </div>
    </div>
  )
}

// 编辑目标 Modal 组件
const EditObjectiveModal = ({ objective, onClose, onSave }: { objective: LearningObjective; onClose: () => void; onSave: (data: { title?: string; duration?: number; baseline?: string; target_description?: string }) => void }) => {
  const [title, setTitle] = useState(objective.title)
  const [duration, setDuration] = useState(objective.duration?.toString() || '')
  const [baseline, setBaseline] = useState(objective.baseline || '')
  const [targetDescription, setTargetDescription] = useState(objective.target_description || '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    
    onSave({
      title: title.trim(),
      duration: duration ? parseInt(duration) : undefined,
      baseline: baseline.trim() || undefined,
      target_description: targetDescription.trim() || undefined,
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">编辑学习目标</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xl leading-none">✕</button>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 flex-1 overflow-y-auto">
          <div className="space-y-4">
            {/* 标题 - 必填 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                目标标题 <span className="text-red-500">*</span>
              </label>
              <input 
                type="text"
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如：深入掌握 React 高级特性"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            {/* 持续时长 - 可选 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                持续时长（天）
              </label>
              <input 
                type="number"
                min="1"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                placeholder="留空可让 AI 根据任务量推荐合理时长"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            {/* 当前现状 - 可选 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                当前现状
              </label>
              <textarea 
                rows={4}
                value={baseline}
                onChange={(e) => setBaseline(e.target.value)}
                placeholder="描述您目前对这个领域的了解程度..."
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors resize-none"
              />
            </div>

            {/* 预期目标 - 可选 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                预期目标
              </label>
              <textarea 
                rows={4}
                value={targetDescription}
                onChange={(e) => setTargetDescription(e.target.value)}
                placeholder="描述您希望达到的水平..."
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-gray-900 dark:text-white dark:bg-gray-700 focus:outline-none focus:border-blue-500 transition-colors resize-none"
              />
            </div>
          </div>
        </form>

        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
          <button 
            type="button"
            onClick={onClose}
            className="px-5 py-2.5 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors font-medium"
          >
            取消
          </button>
          <button 
            type="button"
            onClick={(e: any) => handleSubmit(e)}
            disabled={!title.trim()}
            className="px-5 py-2.5 text-sm text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium shadow-sm"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  )
}

export const LearningPage = memo(({ runtime }: LearningPageProps) => {
  const { objectives, learningCategories, createObjective, updateObjective, removeObjective, addKR, addTask, removeTask, cancelChecklistTask, refresh: refreshLearning, importFullObjective, importKRsToObjective } = useLearning(runtime)
  const { submissions, submit: submitChecklistTask, clear: clearChecklistTaskSubmission } = useChecklistTaskSubmission(runtime, refreshLearning)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingObjective, setEditingObjective] = useState<LearningObjective | null>(null)
  const [showImportModal, setShowImportModal] = useState(false)
  const [importJson, setImportJson] = useState('')
  const [activeAiObj, setActiveAiObj] = useState<LearningObjective | null>(null)
  const [recommendedDuration, setRecommendedDuration] = useState<{ duration: number; reasoning: string } | null>(null)
  const [selectedDurationOption, setSelectedDurationOption] = useState<'ai' | 'manual' | 'user'>('ai')
  const [manualDuration, setManualDuration] = useState('')
  const [statusOverrides, setStatusOverrides] = useState<Record<string, 0 | 2>>({})
  const [pendingTaskIds, setPendingTaskIds] = useState<Set<string>>(() => new Set())
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({})

  const setPendingTask = (taskId: string, pending: boolean) => setPendingTaskIds(current => {
    const next = new Set(current)
    pending ? next.add(taskId) : next.delete(taskId)
    return next
  })
  const setStatusOverride = (taskId: string, status?: 0 | 2) => setStatusOverrides(current => {
    const next = { ...current }
    if (status === undefined) delete next[taskId]
    else next[taskId] = status
    return next
  })
  const clearActionError = (taskId: string) => setActionErrors(current => {
    if (!current[taskId]) return current
    const next = { ...current }
    delete next[taskId]
    return next
  })

  useEffect(() => {
    const actualStatuses = new Map<string, number>()
    objectives.forEach(objective => objective.krs?.forEach(kr => kr.tasks?.forEach(task => actualStatuses.set(task.id, task.status))))
    setStatusOverrides(current => {
      const next = { ...current }
      Object.entries(current).forEach(([taskId, status]) => {
        if (actualStatuses.get(taskId) === status) delete next[taskId]
      })
      return next
    })
  }, [objectives])

  const handleCreateObjective = (data: { title: string; duration?: number; baseline?: string; target_description?: string }) => {
    createObjective(data)
    setShowCreateModal(false)
  }

  const handleUpdateObjective = (id: string, data: { title?: string; duration?: number; baseline?: string; target_description?: string }) => {
    updateObjective(id, data)
    setEditingObjective(null)
  }

  const handleAcceptJson = (json: string) => {
    if (!activeAiObj) return
    
    importKRsToObjective(activeAiObj.id, json, (duration, reasoning) => {
      // AI 推荐了时长
      setRecommendedDuration({ duration, reasoning })
      setSelectedDurationOption('ai')
    })
  }

  const handleApplyDuration = () => {
    if (!activeAiObj || !recommendedDuration) return
    
    let finalDuration: number | undefined
    
    if (selectedDurationOption === 'ai') {
      finalDuration = recommendedDuration.duration
    } else if (selectedDurationOption === 'manual' && manualDuration) {
      finalDuration = parseInt(manualDuration)
    } else if (selectedDurationOption === 'user' && activeAiObj.duration) {
      finalDuration = activeAiObj.duration
    }
    
    if (finalDuration) {
      updateObjective(activeAiObj.id, { duration: finalDuration })
    }
    
    // 重置状态
    setRecommendedDuration(null)
    setManualDuration('')
    setActiveAiObj(null)
  }

  const handleAddChecklist = (task: LearningTask) => {
    const category = task.category_name === '输入' || task.category_name === '输出' ? task.category_name : null
    if (!category || pendingTaskIds.has(task.id)) return
    const dueDate = formatBeijingDate()
    clearActionError(task.id)
    setStatusOverride(task.id, 2)
    setPendingTask(task.id, true)
    submitChecklistTask(`learning-${task.id}`, {
      requestId: `learning-${task.id}-${createChecklistAttemptId()}`, title: task.title, dueDate, tags: [category], learningTaskId: task.id,
      onConfirmed: () => setPendingTask(task.id, false),
      onFailed: error => { setStatusOverride(task.id); setPendingTask(task.id, false); setActionErrors(current => ({ ...current, [task.id]: error.message })) },
    })
  }

  const handleToggleTask = async (task: LearningTask) => {
    if (pendingTaskIds.has(task.id)) return
    clearActionError(task.id)
    if (task.status !== 2) {
      handleAddChecklist(task)
      return
    }
    try {
      setStatusOverride(task.id, 0)
      setPendingTask(task.id, true)
      const cancelled = await cancelChecklistTask(task.id)
      if (!cancelled) throw new Error('未找到关联清单任务，请同步后重试')
      clearChecklistTaskSubmission(`learning-${task.id}`)
    } catch (reason: any) {
      setStatusOverride(task.id)
      setActionErrors(current => ({ ...current, [task.id]: reason?.message || '无法取消该学习单元' }))
    } finally {
      setPendingTask(task.id, false)
    }
  }

  const handleImport = async () => {
    if (!importJson.trim()) return
    const success = await importFullObjective(importJson)
    if (success) {
      setImportJson('')
      setShowImportModal(false)
    } else {
      alert('导入失败，请检查 JSON 格式是否正确')
    }
  }

  const handleDownloadTemplate = () => {
    const template = {
      title: "在此输入学习目标标题 (例如: 深入学习 React 高级特性)",
      krs: [
        {
          title: "KR 1: 核心概念理解与源码剖析",
          tasks: [
            { 
              title: "阅读官方文档 Hooks 章节并输出思维导图", 
              group_name: "输入", 
              priority: 3, 
              reward: 5 
            },
            { 
              title: "手写实现一个简化版的 useState 钩子", 
              group_name: "输出", 
              priority: 5, 
              reward: 8 
            }
          ]
        },
        {
          title: "KR 2: 实战项目落地与性能优化",
          tasks: [
            { 
              title: "完成 TodoList 组件的性能基准测试", 
              group_name: "输入", 
              priority: 1, 
              reward: 3 
            },
            { 
              title: "使用 useMemo 和 useCallback 重构渲染瓶颈", 
              group_name: "输出", 
              priority: 5, 
              reward: 10 
            }
          ]
        }
      ]
    }
    
    const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'MTL_Learning_Template.json'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="theme-page flex h-full flex-col overflow-hidden">
      <header className="flex flex-none items-center justify-between gap-3 px-5 pb-2 pt-4">
        <div className="min-w-0 flex-1">
          <h2 className="flex h-8 items-center whitespace-nowrap text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">🏆 学习 (OKR)</h2>
        </div>
        <div className="flex flex-none items-center gap-1.5">
          <button 
            onClick={handleDownloadTemplate}
            className="flex h-8 items-center gap-1 whitespace-nowrap rounded-lg border border-gray-200 bg-white px-2 text-sm text-gray-500 shadow-sm transition-colors hover:bg-gray-50 hover:text-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
            title="下载标准 JSON 模板，便于大模型生成内容"
          >
            <span>📄</span> 标准模板
          </button>
          <button 
            onClick={() => setShowImportModal(true)}
            className="flex h-8 items-center gap-1 whitespace-nowrap rounded-lg border border-gray-200 bg-white px-2 text-sm text-gray-600 shadow-sm transition-colors hover:bg-gray-50 hover:text-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
          >
            <span>📥</span> 导入 JSON
          </button>
        </div>
      </header>

      {showImportModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
        <div className="theme-surface rounded-2xl border shadow-xl w-full max-w-lg overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
              <h3 className="font-bold text-gray-800">导入标准 JSON</h3>
              <button onClick={() => setShowImportModal(false)} className="text-gray-400 hover:text-gray-600">✕</button>
            </div>
            <div className="p-5 flex-1">
              <p className="text-xs text-gray-500 mb-2">
                请粘贴由大模型生成的标准 JSON (包含 title, krs, tasks)：
              </p>
              <textarea 
                value={importJson}
                onChange={e => setImportJson(e.target.value)}
                className="w-full h-64 border border-gray-200 rounded-lg p-3 text-sm focus:outline-none focus:border-blue-500 font-mono resize-none shadow-inner"
                placeholder='{\n  "title": "深入掌握 React",\n  "krs": [\n    { "title": "...", "tasks": [...] }\n  ]\n}'
              />
            </div>
            <div className="px-5 py-4 border-t border-gray-100 bg-gray-50/50 flex justify-end gap-3">
              <button 
                onClick={() => setShowImportModal(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-200 bg-gray-100 rounded-lg transition-colors"
              >
                取消
              </button>
              <button 
                onClick={handleImport}
                disabled={!importJson.trim()}
                className="px-4 py-2 text-sm text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors disabled:opacity-50 font-medium shadow-sm"
              >
                验证并导入
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="flex-1 overflow-y-auto px-5 py-4 scrollbar-hide">
        {objectives.map(obj => (
          <ObjectiveCard 
            key={obj.id} 
            objective={obj} 
            categories={learningCategories}
            onAddKR={(title) => addKR(obj.id, title)}
            onAddTask={(krId, title, categoryId) => addTask(krId, { title, category_id: categoryId })}
            onToggleTask={handleToggleTask}
            onRemoveTask={removeTask}
            onAddChecklist={handleAddChecklist}
            submissions={submissions}
            statusOverrides={statusOverrides}
            pendingTaskIds={pendingTaskIds}
            actionErrors={actionErrors}
            onOpenAi={setActiveAiObj}
            onUpdate={(data) => handleUpdateObjective(obj.id, data)}
            onRemove={() => removeObjective(obj.id)}
            onOpenEdit={() => setEditingObjective(obj)}
          />
        ))}

        <button 
          onClick={() => setShowCreateModal(true)}
          className="w-full mt-4 py-4 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl text-gray-500 dark:text-gray-300 hover:border-blue-400 hover:text-blue-500 hover:bg-blue-50/50 dark:hover:bg-gray-800 transition-all font-medium flex items-center justify-center gap-2"
        >
          <span className="text-xl leading-none">+</span> 创建新目标 (Objective)
        </button>
      </main>

      {showCreateModal && (
        <CreateObjectiveModal 
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateObjective}
        />
      )}

      {editingObjective && (
        <EditObjectiveModal 
          objective={editingObjective}
          onClose={() => setEditingObjective(null)}
          onSave={(data) => handleUpdateObjective(editingObjective.id, data)}
        />
      )}

      {activeAiObj && (
        <AiCopilotDrawer 
          objective={activeAiObj} 
          onClose={() => {
            setActiveAiObj(null)
            setRecommendedDuration(null)
            setManualDuration('')
          }}
          onAcceptJson={handleAcceptJson}
        />
      )}

      {recommendedDuration && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-md overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">✨ AI 推荐持续时长</h3>
            </div>
            
            <div className="p-6 space-y-4">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  <span className="font-bold text-blue-600 dark:text-blue-400">推荐：{recommendedDuration.duration} 天</span>
                </p>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                  💡 {recommendedDuration.reasoning}
                </p>
              </div>

              <div className="space-y-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input 
                    type="radio" 
                    checked={selectedDurationOption === 'ai'}
                    onChange={() => setSelectedDurationOption('ai')}
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    采纳 AI 推荐（{recommendedDuration.duration} 天）
                  </span>
                </label>

                {activeAiObj?.duration && (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input 
                      type="radio" 
                      checked={selectedDurationOption === 'user'}
                      onChange={() => setSelectedDurationOption('user')}
                      className="w-4 h-4"
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      使用我填写的时长（{activeAiObj.duration} 天）
                    </span>
                  </label>
                )}

                <label className="flex items-center gap-2 cursor-pointer">
                  <input 
                    type="radio" 
                    checked={selectedDurationOption === 'manual'}
                    onChange={() => setSelectedDurationOption('manual')}
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">手动调整</span>
                </label>

                {selectedDurationOption === 'manual' && (
                  <input 
                    type="number"
                    min="1"
                    value={manualDuration}
                    onChange={(e) => setManualDuration(e.target.value)}
                    placeholder="输入天数..."
                    className="ml-6 w-32 border border-gray-300 dark:border-gray-600 rounded px-3 py-1.5 text-sm"
                  />
                )}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
              <button 
                onClick={() => {
                  setRecommendedDuration(null)
                  setManualDuration('')
                }}
                className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
              >
                跳过
              </button>
              <button 
                onClick={handleApplyDuration}
                disabled={selectedDurationOption === 'manual' && !manualDuration}
                className="px-4 py-2 text-sm text-white bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors disabled:opacity-50"
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
})
