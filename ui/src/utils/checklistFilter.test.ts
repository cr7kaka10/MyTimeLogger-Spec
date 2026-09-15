import { filterTasksForChecklistDate } from './checklistFilter'
import type { TaskItem } from '../types'

const task = (id: string, due_date: string): TaskItem => ({
  id,
  title: id,
  priority: 0,
  status: 0,
  tags: [],
  due_date,
  due_date_full: due_date,
  is_overdue: false,
})

const selected = new Date('2026-07-31T12:00:00+08:00')
const matching = task('inbox-due', '2026-07-31T09:00:00+0800')
const noDueDate = task('inbox-no-due', '')
const otherDate = task('inbox-other-date', '2026-08-02T09:00:00+0800')

if (filterTasksForChecklistDate([matching], selected).map(item => item.id).join() !== 'inbox-due') {
  throw new Error('收集箱带截止日期任务应在匹配日期显示')
}
if (filterTasksForChecklistDate([noDueDate], selected).length !== 0) {
  throw new Error('无截止日期的收集箱任务不应显示')
}
if (filterTasksForChecklistDate([otherDate], selected).length !== 0) {
  throw new Error('截止日期不匹配的收集箱任务不应显示')
}

console.log('checklistFilter tests passed')
