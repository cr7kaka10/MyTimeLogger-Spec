import { describe, expect, it } from 'vitest'
import { filterTasksForChecklistDate } from '../../ui/src/utils/checklistFilter'

const selectedDate = new Date('2026-06-13T08:00:00+08:00')

describe('checklist date filter', () => {
  it('includes unfinished and completed tasks with matching due date only', () => {
    const tasks: any[] = [
      { id: 'active-today', title: 'today active', status: 0, due_date: '2026-06-13 00:00:00' },
      { id: 'done-today', title: 'today done', status: 2, due_date: '2026-06-13 00:00:00' },
      { id: 'done-undated', title: 'old done without date', status: 2, due_date: '' },
      { id: 'active-other-day', title: 'other day', status: 0, due_date: '2026-06-12 00:00:00' },
    ]

    expect(filterTasksForChecklistDate(tasks, selectedDate).map(task => task.id)).toEqual([
      'active-today',
      'done-today',
    ])
  })
})
