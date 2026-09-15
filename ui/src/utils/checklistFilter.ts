import type { TaskItem } from '../types'
import { dateToShanghaiDateString, tickTickDateToShanghaiDateString } from './shanghaiDate'

export const filterTasksForChecklistDate = (tasks: TaskItem[], selectedDate: Date): TaskItem[] => {
  if (!tasks || !Array.isArray(tasks) || !selectedDate || !(selectedDate instanceof Date) || isNaN(selectedDate.getTime())) {
    return []
  }
  const selectedDateStr = dateToShanghaiDateString(selectedDate)
  return tasks.filter(task => {
    if (!task?.due_date) return false
    return tickTickDateToShanghaiDateString(task.due_date) === selectedDateStr
  })
}
