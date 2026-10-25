import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import managementPlanMarkdown from '../../../../docs/管理方案.md?raw'

export function ManagementPlanText() {
  return <article aria-label="文字版管理方案" className="space-y-4 break-words text-sm leading-6 text-gray-700 dark:text-gray-200">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      h1: ({ children }) => <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{children}</h1>,
      h2: ({ children }) => <h2 className="mt-6 border-b border-gray-200 pb-2 text-base font-bold text-gray-900 dark:border-gray-700 dark:text-gray-100">{children}</h2>,
      p: ({ children }) => <p className="text-sm leading-6 text-gray-600 dark:text-gray-300">{children}</p>,
      ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
      ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
      table: ({ children }) => <div className="max-w-full overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700"><table className="w-full min-w-[40rem] border-collapse text-left text-xs">{children}</table></div>,
      th: ({ children }) => <th className="whitespace-nowrap border-b border-gray-200 bg-gray-50 px-3 py-2 font-semibold text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">{children}</th>,
      td: ({ children }) => <td className="border-b border-gray-100 px-3 py-2 align-top text-gray-600 dark:border-gray-800 dark:text-gray-300">{children}</td>,
      blockquote: ({ children }) => <blockquote className="border-l-2 border-blue-400 pl-3 text-gray-500 dark:text-gray-400">{children}</blockquote>,
      code: ({ children }) => <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs dark:bg-gray-800">{children}</code>,
    }}>{managementPlanMarkdown}</ReactMarkdown>
  </article>
}
