import { filterTasksForChecklistDate } from '../utils/checklistFilter'
import { isTaskFocusActive } from '../pages/UnifiedChecklistPage/taskFocusState'

const inboxTask = {
  id: 'inbox-task',
  title: '收集箱任务',
  priority: 0,
  status: 0,
  tags: [],
  due_date: '2026-07-31T09:00:00+0800',
  due_date_full: '2026-07-31 09:00:00',
  is_overdue: false,
}

const visible = filterTasksForChecklistDate(
  [inboxTask],
  new Date('2026-07-31T12:00:00+08:00'),
)
if (visible.length !== 1 || visible[0].id !== 'inbox-task') {
  throw new Error('PC/Android 共用清单拉取结果应在截止日期匹配时可见')
}
if (isTaskFocusActive(null, 'inbox-task', 'studying', 1, 1, '', inboxTask.title)) {
  throw new Error('未确认的收集箱任务草稿不应进入专注状态')
}

console.log('useChecklist contract tests passed')
