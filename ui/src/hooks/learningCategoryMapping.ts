export interface LearningCategoryRow { id: number; name: string }

export function mapLearningTaskCategories(krs: any[], categories: LearningCategoryRow[]): any[] {
  const ids = new Map(categories.filter(item => item.name === '输入' || item.name === '输出').map(item => [item.name, item.id]))
  if (!ids.has('输入') || !ids.has('输出')) throw new Error('学习分类配置缺失：必须同时存在输入和输出')
  return krs.map((kr, krIndex) => ({
    ...kr,
    tasks: (Array.isArray(kr?.tasks) ? kr.tasks : []).map((task: any, taskIndex: number) => {
      if (task?.group_name !== '输入' && task?.group_name !== '输出') {
        throw new Error(`第 ${krIndex + 1} 个 KR 的第 ${taskIndex + 1} 条任务分类无效`)
      }
      return { ...task, category_id: ids.get(task.group_name) }
    }),
  }))
}
