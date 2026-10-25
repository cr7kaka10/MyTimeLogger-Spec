import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import managementPlanMarkdown from '../../../../docs/管理方案.md?raw'
import type { Goal } from '../../types'

const anchor = '<!-- CURRENT_GOAL_COIN_SUMMARY -->'
const periodLabels: Record<string, string> = { daily: '每日', weekly: '每周', monthly: '每月', per_session: '每次' }
const markdownComponents = {
  h1: ({ children }: any) => <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{children}</h1>,
  h2: ({ children }: any) => <h2 className="mt-6 border-b border-gray-200 pb-2 text-base font-bold text-gray-900 dark:border-gray-700 dark:text-gray-100">{children}</h2>,
  p: ({ children }: any) => <p className="text-sm leading-6 text-gray-600 dark:text-gray-300">{children}</p>,
  ul: ({ children }: any) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }: any) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
  table: ({ children }: any) => <div className="max-w-full overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700"><table className="w-full min-w-[40rem] border-collapse text-left text-xs">{children}</table></div>,
  th: ({ children }: any) => <th className="whitespace-nowrap border-b border-gray-200 bg-gray-50 px-3 py-2 font-semibold text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">{children}</th>,
  td: ({ children }: any) => <td className="border-b border-gray-100 px-3 py-2 align-top text-gray-600 dark:border-gray-800 dark:text-gray-300">{children}</td>,
  blockquote: ({ children }: any) => <blockquote className="border-l-2 border-blue-400 pl-3 text-gray-500 dark:text-gray-400">{children}</blockquote>,
  code: ({ children }: any) => <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs dark:bg-gray-800">{children}</code>,
}

export function ManagementPlanText({ goals }: { goals: Goal[] }) {
  const [beforeGoals, afterGoals] = managementPlanMarkdown.split(anchor)
  const sortedGoals = [...goals].sort((a, b) => Math.max(Math.abs(b.reward_coins), Math.abs(b.penalty_coins)) - Math.max(Math.abs(a.reward_coins), Math.abs(a.penalty_coins)))
  const renderMarkdown = (source: string) => <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{source}</ReactMarkdown>
  return <article aria-label="文字版管理方案" className="space-y-4 break-words text-sm leading-6 text-gray-700 dark:text-gray-200">
    {renderMarkdown(beforeGoals)}
    {managementPlanMarkdown.includes(anchor) && <section aria-label="当前目标金币奖惩" className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">当前账户全部目标（按最高奖惩金额排序）</h3>
      {sortedGoals.length ? sortedGoals.map(goal => {
        const value = Number(goal.target_value)
        const conditionValue = goal.metric === 'duration' ? value % 60 === 0 ? `${value / 60} 小时` : `${value} 分钟` : `${value} 次`
        return <div key={goal.id} className="rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-700">
          <div className="flex flex-wrap justify-between gap-x-3"><strong>{goal.title}</strong><span>{periodLabels[goal.period] || goal.period} · {goal.metric === 'duration' ? '时长' : '次数'} {goal.operator} {conditionValue}</span></div>
          <p className="mt-1">达标 +{Math.abs(goal.reward_coins)} 金币 · 未达标 -{Math.abs(goal.penalty_coins)} 金币 · {goal.is_active ? '启用中' : '已停用'}</p>
        </div>
      }) : <p>当前账户暂无目标。</p>}
    </section>}
    {managementPlanMarkdown.includes(anchor) ? renderMarkdown(afterGoals || '') : null}
  </article>
}
