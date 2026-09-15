import { useEffect, useMemo, useRef, useState } from 'react'
import { useManagementPlan, type ManagementPlanDraft, type ManagementPlanItem, type ManagementPlanPayload, type ManagementPlanRuntime } from '../../hooks/useManagementPlan'
import { useManagementPlanVersions } from '../../hooks/useManagementPlanVersions'
import { ManagementPlanMindmap, type MindmapNavigation } from './ManagementPlanMindmap'
import { ManagementPlanHistory } from './ManagementPlanHistory'
import { useBehaviorAuditLog } from '../../hooks/useBehaviorAuditLog'
import type { MainTab } from '../../types'

interface Props { runtime: ManagementPlanRuntime; onClose: () => void; onNavigate?: (intent: MindmapNavigation) => void; initialRequest?: string; initialDraft?: ManagementPlanDraft | null; open?: boolean; mode?: 'draft' | 'history' }

const actionLabels: Record<string, string> = { create: '新增', update: '调整', bind: '绑定', keep: '保留', disable: '停用' }
const sourceLabels: Record<string, string> = { checklist_task: '任务', habit: '习惯', learning_task: '学习任务', goal: '目标', exercise_checkin: '运动打卡' }
const periodLabels: Record<string, string> = { daily: '每日', weekly: '每周', monthly: '每月', per_session: '每次' }
const inventoryLabel = (mode: string, limit?: number | null) => mode === 'unlimited' ? '不限量' : `${periodLabels[mode] || mode}${limit ? ` ${limit} 个` : ''}`

export function ManagementPlanSheet({ runtime, onClose, onNavigate, initialRequest = '', initialDraft = null, open = true, mode = 'draft' }: Props) {
  const plan = useManagementPlan(runtime)
  const versions = useManagementPlanVersions(runtime)
  const [requestText, setRequestText] = useState(initialRequest)
  const [editedPayload, setEditedPayload] = useState<ManagementPlanPayload | null>(null)
  const [selectedRevision, setSelectedRevision] = useState<any>(null)
  const [historyContent, setHistoryContent] = useState<any>(null)
  const [historyError, setHistoryError] = useState('')
  const [historyView, setHistoryView] = useState<'mindmap' | 'versions' | 'behavior'>('mindmap')
  const [showGenerator, setShowGenerator] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [fullscreenError, setFullscreenError] = useState('')
  const generatedRequestRef = useRef('')
  const sheetRef = useRef<HTMLDivElement>(null)
  const items = useMemo<ManagementPlanItem[]>(() => editedPayload?.items || plan.draft?.payload?.items || [], [editedPayload, plan.draft])
  const draftMode = plan.draft?.payload?.mode || 'proposal'
  const isReview = draftMode === 'review'
  const evidence = plan.draft?.payload?.review?.evidence
  const impactByKey = useMemo(() => new Map((plan.preview?.impact || []).map(item => [item.logical_key, item])), [plan.preview])
  const busy = ['generating', 'previewing', 'applying'].includes(plan.state)
  const audit = useBehaviorAuditLog(runtime, mode === 'history' && !showGenerator && historyView === 'behavior')

  useEffect(() => {
    if (mode !== 'draft') return
    if (initialDraft) { plan.setDraft(initialDraft); setEditedPayload(null); return }
    const request = initialRequest.trim()
    if (!request || generatedRequestRef.current === request) return
    generatedRequestRef.current = request
    setRequestText(request)
    void plan.generate(request).catch(() => {})
  }, [initialDraft, initialRequest, mode, plan.generate, plan.setDraft])

  useEffect(() => {
    const syncFullscreen = () => setIsFullscreen(document.fullscreenElement === sheetRef.current)
    document.addEventListener('fullscreenchange', syncFullscreen)
    return () => document.removeEventListener('fullscreenchange', syncFullscreen)
  }, [])

  if (!open) return null

  const updateItem = (index: number, enabled: boolean) => {
    const payload = editedPayload || plan.draft?.payload
    if (!payload || payload.mode === 'review') return
    const next: ManagementPlanPayload = { ...payload, items: payload.items.map((item, itemIndex) => itemIndex === index ? { ...item, action: enabled ? (item.action === 'disable' ? 'keep' : item.action) : 'disable' } : item) }
    setEditedPayload(next)
    plan.setDraft(current => current ? { ...current, payload: next, plan_digest: undefined } : current)
  }

  const selectRevision = async (revision: any) => {
    setSelectedRevision(revision)
    setHistoryContent(null)
    setHistoryError('')
    try {
      setHistoryContent(await versions.exportRevision(revision.id))
    } catch (cause: any) {
      setHistoryError(String(cause?.message || '读取版本内容失败'))
    }
  }

  const historyMode = mode === 'history' && !showGenerator
  const toggleFullscreen = async () => {
    setFullscreenError('')
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await sheetRef.current?.requestFullscreen()
    } catch {
      setFullscreenError('浏览器未允许全屏显示')
    }
  }

  return (
    <div className={`fixed inset-0 z-[70] flex bg-black/40 backdrop-blur-sm ${isFullscreen ? 'items-stretch justify-stretch p-0' : 'items-end justify-center px-0 sm:items-center sm:px-4'}`} role="dialog" aria-modal="true" aria-label={historyMode ? '管理方案历史' : 'AI 管理方案'}>
      <div ref={sheetRef} className={`theme-surface flex w-full flex-col overflow-hidden border shadow-2xl ${isFullscreen ? 'h-[100dvh] max-h-none max-w-none rounded-none' : 'max-h-[92dvh] max-w-2xl rounded-t-3xl sm:rounded-2xl'}`}>
        <header className="flex items-center justify-between border-b px-5 py-4">
          <div><h2 className="text-base font-bold">{historyMode ? '管理方案' : 'AI 管理方案'}</h2><p className="mt-1 text-xs text-gray-500">{historyMode ? (historyView === 'mindmap' ? '当前数据库配置与奖励关系' : historyView === 'behavior' ? '按北京时间查看当前账户行为日志' : '已发布方案版本历史') : isReview ? '总结当前方案，只读不应用' : '输入需求，逐项审阅后再生成执行内容'}</p></div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => void toggleFullscreen()} aria-label={isFullscreen ? '退出全屏' : '全屏'} aria-pressed={isFullscreen} title={isFullscreen ? '退出全屏' : '全屏'} className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700">
              <span aria-hidden="true" className="relative block h-4 w-4">
                <span className="absolute left-0 top-0 h-1.5 w-1.5 border-l border-t border-current" />
                <span className="absolute right-0 top-0 h-1.5 w-1.5 border-r border-t border-current" />
                <span className="absolute bottom-0 left-0 h-1.5 w-1.5 border-b border-l border-current" />
                <span className="absolute bottom-0 right-0 h-1.5 w-1.5 border-b border-r border-current" />
              </span>
            </button>
            <button type="button" onClick={onClose} aria-label="关闭管理方案" title="关闭" className="rounded-lg px-2 py-1 text-xl text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700">×</button>
          </div>
        </header>
        {fullscreenError && <p className="px-5 py-2 text-xs text-amber-700" role="status">{fullscreenError}</p>}
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {historyMode ? (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2 border-b pb-3"><button type="button" onClick={() => setShowGenerator(true)} className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white">生成整体方案</button><button type="button" aria-pressed={historyView === 'mindmap'} onClick={() => setHistoryView('mindmap')} className="rounded-lg border px-3 py-1.5 text-sm data-[active=true]:bg-blue-600" data-active={historyView === 'mindmap'}>当前导图</button><button type="button" aria-pressed={historyView === 'versions'} onClick={() => setHistoryView('versions')} className="rounded-lg border px-3 py-1.5 text-sm data-[active=true]:bg-blue-600" data-active={historyView === 'versions'}>版本历史</button><button type="button" aria-pressed={historyView === 'behavior'} onClick={() => setHistoryView('behavior')} className="rounded-lg border px-3 py-1.5 text-sm data-[active=true]:bg-blue-600" data-active={historyView === 'behavior'}>行为日志</button></div>
              {historyView === 'mindmap' ? (
                <ManagementPlanMindmap runtime={runtime} onNavigate={intent => { onNavigate?.(intent); onClose() }} />
              ) : historyView === 'behavior' ? <section className="space-y-3" aria-label="行为日志"><input type="date" value={audit.date} onChange={event => audit.setDate(event.target.value)} className="rounded-lg border px-3 py-2 text-sm" />{audit.error ? <button type="button" onClick={audit.reload} className="rounded-lg border border-red-300 px-3 py-2 text-sm text-red-700">重试：{audit.error}</button> : null}{audit.loading && !audit.events.length ? <p className="text-sm text-gray-500">正在读取行为日志…</p> : audit.events.length ? <div className="space-y-2">{audit.events.map(event => <div key={event.event_id} className="rounded-lg border p-3 text-sm"><div className="flex justify-between gap-2"><strong>{event.summary || '执行了系统操作'}</strong><span>{event.occurred_at.slice(11)}</span></div><p className="mt-1 text-xs text-gray-600 dark:text-gray-300">{event.detail}</p><p className="mt-1 text-[11px] text-gray-400">{event.page_label} · {event.action}</p></div>)}</div> : <p className="text-sm text-gray-500">该日期暂无行为日志。</p>}{audit.cursor ? <button type="button" disabled={audit.loading} onClick={audit.loadMore} className="rounded-lg border px-3 py-2 text-sm">加载更多</button> : null}</section> : (
                <>
                  <ManagementPlanHistory runtime={runtime} onSelect={revision => void selectRevision(revision)} />
                  {historyError && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300" role="alert">{historyError}</p>}
                  {selectedRevision && <section className="space-y-2 border-t pt-4" aria-label="管理方案版本内容">
                    <h3 className="text-sm font-semibold">{selectedRevision.version}</h3>
                    {!historyContent ? <p className="text-sm text-gray-500">正在读取版本内容…</p> : <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg border bg-gray-50 p-3 text-xs leading-5 text-gray-700 dark:bg-gray-900 dark:text-gray-200">{historyContent.markdown || JSON.stringify(historyContent.manifest || {}, null, 2)}</pre>}
                  </section>}
                </>
              )}
            </div>
          ) : plan.state === 'idle' || plan.state === 'generating' || plan.state === 'error' ? (
            <div className="space-y-3">
              <textarea value={requestText} onChange={event => setRequestText(event.target.value)} disabled={busy} rows={6} placeholder="例如：我想在保证睡眠的前提下，每周稳定学习 React、保持运动，并给完成任务设置合理的奖励" className="w-full resize-y rounded-xl border bg-transparent p-3 text-sm outline-none focus:border-blue-500" />
              {plan.error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{plan.error}</p>}
              <button type="button" disabled={busy || !requestText.trim()} onClick={() => void plan.generate(requestText)} className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{plan.state === 'generating' ? '正在生成…' : '生成方案草案'}</button>
            </div>
          ) : isReview ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-3 text-sm dark:border-blue-900 dark:bg-blue-950/20">{plan.draft?.payload?.summary || '已完成当前管理方案总结。'}</div>
              <section className="space-y-2 border-b pb-4" aria-label="金币规则">
                <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">金币规则</h3><span className="text-xs text-gray-500">{evidence?.summary.reward_rule_count || 0} 条</span></div>
                {(evidence?.reward_rules || []).length > 0 ? <div className="space-y-2">{evidence!.reward_rules.map(rule => <div key={`${rule.kind}-${rule.source_id}`} className="rounded-lg border bg-amber-50/50 px-3 py-2 text-sm dark:border-amber-900 dark:bg-amber-950/20"><div className="flex justify-between gap-3"><strong className="truncate">{rule.source_title}</strong><span className="shrink-0 font-semibold text-amber-700 dark:text-amber-300">完成 +{rule.coins} / 失败 -{rule.penalty} 金币</span></div><p className="mt-1 text-xs text-gray-500">{sourceLabels[rule.kind] || rule.kind}{rule.period ? ` · ${periodLabels[rule.period] || rule.period}` : ''}{rule.source_status === 'source_missing' ? ' · 来源已不存在' : ''}</p></div>)}</div> : <p className="text-xs text-gray-500">尚未建立任务、习惯、学习或目标金币规则。</p>}
              </section>
              <section className="space-y-2 border-b pb-4" aria-label="商品奖励">
                <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">商品奖励</h3><span className="text-xs text-gray-500">{evidence?.summary.store_item_count || 0} 件</span></div>
                {(evidence?.store_items || []).length > 0 ? <div className="space-y-2">{evidence!.store_items.map(item => <div key={`${item.title}-${item.source_title}`} className="rounded-lg border px-3 py-2 text-sm"><div className="flex justify-between gap-3"><strong className="truncate">{item.title}</strong><span className="shrink-0 font-semibold text-amber-700 dark:text-amber-300">{item.source_type ? '完成解锁' : `${item.price} 金币`}</span></div><p className="mt-1 text-xs text-gray-500">{item.source_type ? `${sourceLabels[item.source_type] || item.source_type}：${item.source_title}${item.required_count > 1 ? ` · 累计 ${item.required_count} 次` : ''}` : '金币兑换'} · {inventoryLabel(item.inventory_mode, item.inventory_limit)}{item.source_status === 'source_missing' ? ' · 来源已不存在' : ''}</p></div>)}</div> : <p className="text-xs text-gray-500">尚未建立可兑换或可解锁的商品奖励。</p>}
                {evidence?.summary.truncated && <p className="text-xs text-gray-500">仅展示最近的配置项。</p>}
              </section>
              {[
                ['当前基础', plan.draft?.payload?.review?.strengths || []],
                ['需要关注', plan.draft?.payload?.review?.risks || []],
                ['下一步建议', plan.draft?.payload?.review?.recommendations || []],
              ].map(([title, entries]) => <section key={String(title)} className="border-b pb-3 last:border-b-0">
                <h3 className="text-sm font-semibold">{title}</h3>
                {(entries as string[]).length > 0 ? <ul className="mt-2 space-y-1 text-sm text-gray-700 dark:text-gray-200">{(entries as string[]).map((entry, index) => <li key={`${title}-${index}`}>{entry}</li>)}</ul> : <p className="mt-2 text-xs text-gray-500">暂无</p>}
              </section>)}
              <div className="flex items-center justify-between text-xs text-gray-500"><span>规则版本</span><span className="font-mono">{plan.draft?.payload?.policy_version || 'legacy'}</span></div>
              <button type="button" disabled={busy} onClick={() => void plan.generate(requestText).catch(() => {})} className="w-full rounded-xl border px-4 py-3 text-sm font-semibold disabled:opacity-50">重新分析</button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-3 text-sm dark:border-blue-900 dark:bg-blue-950/20">{plan.draft?.payload?.summary || '已生成草案，请逐项审阅。确认前不会写入业务数据。'}</div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-500"><span>规划规则<br /><span className="font-mono">{plan.draft?.payload?.policy_version || 'legacy'}</span></span><span>技能版本<br /><span className="font-mono">{String(plan.draft?.payload?.skill_version || 'legacy')}</span></span></div>
              {items.length === 0 ? <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">草案不含可执行项目，请重新生成方案。</div> : null}
              <div className="space-y-2">
                {items.map((item, index) => {
                  const enabled = item.action !== 'disable'
                  const impact = impactByKey.get(item.logical_key)
                  return <label key={item.logical_key || index} className="flex items-start gap-3 rounded-xl border p-3 text-sm">
                    <input type="checkbox" checked={enabled} onChange={event => updateItem(index, event.target.checked)} className="mt-1 h-4 w-4" />
                    <span className="min-w-0 flex-1"><strong className="block truncate">{item.title || item.name || item.logical_key}</strong><span className="mt-1 block text-xs text-gray-500">{actionLabels[item.action] || item.action} · {item.type}{item.expected_minutes ? ` · ${item.expected_minutes} 分钟` : ''}{impact ? ` · 已校验为${actionLabels[impact.action] || impact.action}` : ''}{item.reason ? ` · ${item.reason}` : ''}</span></span>
                    {item.reward?.coins != null && <span className="shrink-0 text-xs font-semibold text-amber-600">+{item.reward.coins} 金币</span>}
                  </label>
                })}
              </div>
              {(plan.preview?.warnings || []).length > 0 && <div className="space-y-1 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200" role="status"><strong>校验提醒</strong>{plan.preview!.warnings!.map((warning, index) => <p key={`warning-${index}`}>{warning}</p>)}<p>请确认来源和影响后再应用。</p></div>}
              {plan.error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">{plan.error}</p>}
              <div className="flex gap-2">
                <button type="button" disabled={busy || items.length === 0} onClick={() => void plan.previewDraft(editedPayload || plan.draft?.payload)} className="flex-1 rounded-xl border px-4 py-3 text-sm font-semibold disabled:opacity-50">{plan.state === 'previewing' ? '校验中…' : '校验变更'}</button>
                <button type="button" disabled={busy || items.length === 0 || !plan.draft?.plan_digest} onClick={() => void plan.apply()} className="flex-1 rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{plan.state === 'applying' ? '应用中…' : '确认并应用'}</button>
              </div>
              {plan.state === 'result' && <div className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200">方案已应用，版本：{plan.result?.result?.revision?.version || '已保存'}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
