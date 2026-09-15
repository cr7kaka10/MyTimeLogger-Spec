export type LearningGroupName = '输入' | '输出'

export function parseLearningPlanJson(jsonText: string): any {
  let data: any
  try { data = JSON.parse(jsonText) } catch { throw new Error('AI 方案 JSON 格式无效') }
  if (!Array.isArray(data?.krs)) throw new Error('AI 方案缺少 KR 列表')
  data.krs.forEach((kr: any, krIndex: number) => {
    if (!Array.isArray(kr?.tasks)) throw new Error(`第 ${krIndex + 1} 个 KR 缺少任务列表`)
    kr.tasks.forEach((task: any, taskIndex: number) => {
      if (task?.group_name !== '输入' && task?.group_name !== '输出') {
        throw new Error(`第 ${krIndex + 1} 个 KR 的第 ${taskIndex + 1} 条任务分类无效，必须是输入或输出`)
      }
    })
  })
  return data
}
