import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import MindElixir, { type MindElixirData, type NodeObj } from 'mind-elixir'
import 'mind-elixir/style.css'
import type { MainTab } from '../../types'
import type { ManagementPlanRuntime } from '../../hooks/useManagementPlan'
import { type MindmapItem, type MindmapProduct, useManagementPlanMindmap } from '../../hooks/useManagementPlanMindmap'
import { useManagementBundle } from '../../hooks/useManagementBundle'
import { ManagementBundleImportModal } from './ManagementBundleImportModal'

const MINDMAP_DOMAIN_ORDER = ['goal', 'sleep', 'learning_task', 'habit', 'checklist_task']
const domainTitles: Record<string, string> = { goal: '目标', sleep: '睡眠', learning_task: '学习', habit: '习惯', checklist_task: '任务' }
const routeFor: Record<string, MainTab | undefined> = { checklist_task: 'checklist', habit: 'checklist', learning_objective: 'learning', learning_kr: 'learning', learning_task: 'learning', goal: 'goals', sleep: 'sleep' }
const domainColors: Record<string, string> = { goal: '#d46d54', sleep: '#879f7c', learning_task: '#4f897c', habit: '#cf885f', checklist_task: '#cf6a52' }

export interface MindmapRewardReturnContext { sourceType: string; sourceId: string; productId?: string; fingerprint: string }
export interface MindmapNavigation { tab: MainTab; returnContext?: MindmapRewardReturnContext }
interface Props { runtime: ManagementPlanRuntime; onNavigate: (intent: MindmapNavigation) => void }
type MindmapNodeMeta = { kind: 'root' | 'domain' | 'item' | 'coins' | 'product'; item?: MindmapItem; product?: MindmapProduct }
type MindmapTopicElement = HTMLElement & { nodeObj?: NodeObj<MindmapNodeMeta> }

function itemKey(item: MindmapItem) { return `${item.source_type}:${item.source_id}` }

function labelFor(item: MindmapItem) {
  if (item.source_type === 'learning_objective') return `Objective · ${item.title}`
  if (item.source_type === 'learning_kr') return `KR · ${item.title}`
  return item.title
}

function itemNode(item: MindmapItem, color: string): NodeObj<MindmapNodeMeta> {
  const childItems = (item.children || []).map(child => itemNode(child, color))
  const rewardNodes: NodeObj<MindmapNodeMeta>[] = []
  if (item.reward) {
    rewardNodes.push({
      id: `${itemKey(item)}:coins`,
      topic: item.reward.status === 'unconfigured' ? '【金币】未配置' : `【金币】+${item.reward.coins ?? 0} / -${item.reward.penalty ?? 0}`,
      branchColor: color,
      style: { background: '#fff4d5', color: '#805300', border: '1px solid #e6b44a', fontSize: '13px', fontWeight: '600' },
      metadata: { kind: 'coins', item },
    })
  }
  item.items.forEach(product => rewardNodes.push({
    id: `${itemKey(item)}:product:${product.id}`,
    topic: `【物品奖励】${product.icon || '礼物'} ${product.title}${product.source_status === 'source_missing' ? ' · 来源已不存在' : ''}`,
    branchColor: color,
    style: { background: '#e8f7f2', color: '#176354', border: '1px solid #72b6a4', fontSize: '13px', fontWeight: '600' },
    metadata: { kind: 'product', product, item },
  }))
  const children = [...childItems, ...rewardNodes]
  const isLearningGroup = item.source_type === 'learning_objective' || item.source_type === 'learning_kr'
  return {
    id: itemKey(item),
    topic: labelFor(item),
    expanded: children.length > 0 && !isLearningGroup,
    branchColor: color,
    style: { background: '#ffffff', color: '#233137', border: `1px solid ${color}`, fontSize: '14px', fontWeight: '600' },
    metadata: { kind: 'item', item },
    children,
  }
}

function createMindmapData(domains: Array<{ key: string; title: string; items: MindmapItem[] }>): MindElixirData {
  return {
    nodeData: {
      id: 'management-plan',
      topic: '管理方案',
      expanded: true,
      style: { background: '#c9644d', color: '#ffffff', border: '1px solid #a94c39', fontSize: '24px', fontWeight: '700' },
      metadata: { kind: 'root' },
      children: domains.map(domain => ({
        id: `domain:${domain.key}`,
        topic: domainTitles[domain.key] || domain.title,
        expanded: false,
        branchColor: domainColors[domain.key],
        style: { background: domainColors[domain.key], color: '#ffffff', border: '1px solid transparent', fontSize: '17px', fontWeight: '700' },
        metadata: { kind: 'domain' },
        children: domain.items.map(item => itemNode(item, domainColors[domain.key])),
      })),
    },
  }
}

const mindmapTheme = {
  name: '管理方案',
  palette: MINDMAP_DOMAIN_ORDER.map(key => domainColors[key]),
  cssVar: {
    '--node-gap-x': '20px', '--node-gap-y': '12px', '--main-gap-x': '28px', '--main-gap-y': '18px',
    '--main-color': '#64748b', '--main-bgcolor': '#ffffff', '--main-bgcolor-transparent': 'rgba(255, 255, 255, 0.92)',
    '--main-border': '1px solid #94a3b8', '--color': '#233137', '--bgcolor': 'transparent', '--selected': '#0f766e',
    '--accent-color': '#0f766e', '--root-color': '#ffffff', '--root-bgcolor': '#c9644d', '--root-border-color': '#a94c39',
    '--root-radius': '8px', '--main-radius': '6px', '--topic-padding': '7px 12px', '--panel-color': '#233137',
    '--panel-bgcolor': '#ffffff', '--panel-border-color': '#d6dde0', '--map-padding': '48px',
  },
}

export function ManagementPlanMindmap({ runtime, onNavigate }: Props) {
  const { snapshot, tree, loading, error, refresh } = useManagementPlanMindmap(runtime)
  const mapRef = useRef<HTMLDivElement>(null)
  const mindRef = useRef<MindElixir | null>(null)
  const [renderError, setRenderError] = useState('')
  const openItem = useCallback((item: MindmapItem) => {
    const route = routeFor[item.source_type]
    if (!route || item.status === 'source_missing') return
    onNavigate({ tab: route })
  }, [onNavigate])

  const openReward = useCallback((item: MindmapItem, product?: MindmapProduct) => {
    const route = product ? 'rewards' : routeFor[item.source_type]
    if (!route || item.status === 'source_missing' || (product && !product.editable)) return
    const fingerprint = product
      ? `product:${product.id}:${product.title}:${product.price}:${product.description || ''}`
      : `coins:${item.source_type}:${item.source_id}:${item.reward?.coins ?? ''}:${item.reward?.penalty ?? ''}`
    onNavigate({ tab: route, returnContext: { sourceType: item.source_type, sourceId: item.source_id, productId: product?.id, fingerprint } })
  }, [onNavigate])

  const handleSelection = useCallback((node: NodeObj) => {
    const meta = node.metadata as MindmapNodeMeta | undefined
    if (!meta) return
    if (meta.kind === 'coins' && meta.item) {
      if (meta.item.reward?.editable) openReward(meta.item)
      else openItem(meta.item)
    } else if (meta.kind === 'product' && meta.product) {
      if (meta.product.editable && meta.item) openReward(meta.item, meta.product)
      else if (meta.item) openItem(meta.item)
    } else if (meta.kind === 'item' && meta.item) openItem(meta.item)
  }, [openItem, openReward])

  const domains = useMemo(() => MINDMAP_DOMAIN_ORDER
    .map(key => (tree?.domains || []).find(domain => domain.key === key))
    .filter((domain): domain is NonNullable<typeof domain> => Boolean(domain)), [tree])
  const data = useMemo(() => createMindmapData(domains), [domains])
  const legacyProducts = useMemo(() => (tree?.domains || []).filter(domain => domain.key === 'reward_item').flatMap(domain => domain.items.flatMap(item => item.items)), [tree])
  const unboundProducts = useMemo(() => [...(tree?.unboundProducts || []), ...legacyProducts]
    .filter((product, index, products) => products.findIndex(candidate => candidate.id === product.id) === index), [legacyProducts, tree])
  const focusRootNode = useCallback(() => {
    const root = mindRef.current?.findEle('management-plan') as HTMLElement | null | undefined
    root?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' })
  }, [])

  useEffect(() => {
    const target = mapRef.current
    if (!target || !tree) return
    target.replaceChildren()
    setRenderError('')
    const mind = new MindElixir({ el: target, direction: MindElixir.RIGHT, editable: false, contextMenu: false, toolBar: false, keypress: false, allowUndo: false, overflowHidden: true, compact: false, theme: mindmapTheme })
    const initError = mind.init(data)
    if (initError) { setRenderError('导图初始化失败，请刷新后重试'); return () => mind.destroy() }
    mindRef.current = mind
    target.tabIndex = 0
    mind.container.style.overflow = 'auto'
    mind.container.style.touchAction = 'pan-x pan-y'
    mind.container.style.overscrollBehavior = 'contain'
    const keepExpandedNodeVisible = (node: NodeObj) => {
      const element = mind.findEle(node.id)
      requestAnimationFrame(() => element.scrollIntoView({ block: 'nearest', inline: 'nearest' }))
    }
    const navigateFromTopic = (event: MouseEvent) => {
      if (event.button !== 0) return
      const eventTarget = event.target as Element | null
      if (eventTarget?.closest('me-epd')) return
      const topic = eventTarget?.closest('me-tpc') as MindmapTopicElement | null
      if (!topic || !target.contains(topic) || !topic.nodeObj) return
      handleSelection(topic.nodeObj)
    }
    const expandFromControl = (event: MouseEvent) => {
      const expander = (event.target as Element | null)?.closest('me-epd')
      if (!expander || !target.contains(expander)) return
      const topic = expander.previousElementSibling as MindmapTopicElement | null
      if (!topic?.nodeObj) return
      event.preventDefault()
      event.stopImmediatePropagation()
      mind.expandNode(topic as Parameters<typeof mind.expandNode>[0])
    }
    let pan: { pointerId: number; x: number; y: number; left: number; top: number } | null = null
    const stopPanning = () => {
      if (!pan) return
      if (target.hasPointerCapture(pan.pointerId)) target.releasePointerCapture(pan.pointerId)
      pan = null
      target.style.cursor = ''
      mind.container.style.cursor = ''
    }
    const startPanning = (event: PointerEvent) => {
      if (event.button !== 2) return
      event.preventDefault()
      pan = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: mind.container.scrollLeft, top: mind.container.scrollTop }
      target.setPointerCapture(event.pointerId)
      target.focus({ preventScroll: true })
      target.style.cursor = 'grabbing'
      mind.container.style.cursor = 'grabbing'
    }
    const panView = (event: PointerEvent) => {
      if (!pan || event.pointerId !== pan.pointerId) return
      event.preventDefault()
      mind.container.scrollLeft = pan.left - (event.clientX - pan.x)
      mind.container.scrollTop = pan.top - (event.clientY - pan.y)
    }
    const preventMapContextMenu = (event: MouseEvent) => event.preventDefault()
    const navigateByKeyboard = (event: KeyboardEvent) => {
      const distance = event.shiftKey ? 320 : 120
      const delta = ({ ArrowLeft: [-distance, 0], ArrowRight: [distance, 0], ArrowUp: [0, -distance], ArrowDown: [0, distance] } as Record<string, [number, number]>)[event.key]
      if (delta) {
        event.preventDefault()
        mind.container.scrollLeft += delta[0]
        mind.container.scrollTop += delta[1]
      } else if (event.key === 'Home') {
        event.preventDefault()
        const root = mind.findEle('management-plan') as HTMLElement | null
        root?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' })
      }
    }
    mind.bus.addListener('expandNode', keepExpandedNodeVisible)
    target.addEventListener('pointerdown', startPanning, true)
    target.addEventListener('pointermove', panView, true)
    target.addEventListener('pointerup', stopPanning, true)
    target.addEventListener('pointercancel', stopPanning, true)
    target.addEventListener('click', expandFromControl, true)
    target.addEventListener('click', navigateFromTopic)
    target.addEventListener('contextmenu', preventMapContextMenu)
    target.addEventListener('keydown', navigateByKeyboard)
    window.addEventListener('blur', stopPanning)
    return () => {
      mind.bus.removeListener('expandNode', keepExpandedNodeVisible)
      target.removeEventListener('pointerdown', startPanning, true)
      target.removeEventListener('pointermove', panView, true)
      target.removeEventListener('pointerup', stopPanning, true)
      target.removeEventListener('pointercancel', stopPanning, true)
      target.removeEventListener('click', expandFromControl, true)
      target.removeEventListener('click', navigateFromTopic)
      target.removeEventListener('contextmenu', preventMapContextMenu)
      target.removeEventListener('keydown', navigateByKeyboard)
      window.removeEventListener('blur', stopPanning)
      if (mindRef.current === mind) mindRef.current = null
      mind.destroy()
    }
  }, [data, handleSelection, tree])

  const { exportBundle } = useManagementBundle(runtime)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importedBundle, setImportedBundle] = useState<any>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleExport = async () => {
    try {
      await exportBundle()
    } catch (err) {
      setRenderError('导出失败: ' + String(err))
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const bundle = JSON.parse(event.target?.result as string)
        setImportedBundle(bundle)
        setImportModalOpen(true)
      } catch (err) {
        setRenderError('解析 JSON 文件失败: ' + String(err))
      }
      // Reset input
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
    reader.onerror = () => {
      setRenderError('读取文件失败')
    }
    reader.readAsText(file)
  }

  const handleImportSuccess = () => {
    setImportModalOpen(false)
    setImportedBundle(null)
    void refresh()
  }

  if (loading && !snapshot) return <p className="py-10 text-center text-sm text-gray-500">正在读取当前数据库配置…</p>
  if (error && !snapshot) return <div className="space-y-3 py-10 text-center"><p className="text-sm text-red-600">{error}</p><button type="button" onClick={() => void refresh()} className="rounded-lg border px-3 py-2 text-sm">重试</button></div>

  return <div className="space-y-3" aria-label="当前数据库配置导图">
    <p className="rounded-lg bg-teal-50 px-3 py-2 text-xs text-teal-800 dark:bg-teal-950/30 dark:text-teal-200">当前为只读导图；可导出完整 JSON，导入会先预检，并仅应用分类、任务、习惯和学习目标变更。完整导图编辑器尚未开放。</p>
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
      <span>当前数据库配置{snapshot?.refreshed_at ? ` · ${snapshot.refreshed_at}` : ''}</span>
      <div className="flex items-center gap-2">
        <button type="button" onClick={handleExport} className="rounded-lg border px-2 py-1 text-[#0f766e] border-[#0f766e] hover:bg-teal-50">导出 JSON</button>
        <button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-lg border px-2 py-1 bg-[#0f766e] text-white hover:bg-[#0d6159]">导入 JSON</button>
        <input type="file" accept=".json" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
        
        <div className="w-px h-4 bg-gray-300 mx-1"></div>
        
        <button type="button" onClick={focusRootNode} title="回到根节点" aria-label="回到根节点" className="flex h-7 w-7 items-center justify-center rounded-md border text-sm hover:bg-gray-50 disabled:opacity-50 dark:hover:bg-gray-800">⌂</button>
        <button type="button" onClick={() => void refresh()} className="rounded-lg border px-2 py-1 hover:bg-gray-50 dark:hover:bg-gray-800">刷新</button>
      </div>
    </div>
    {(error || renderError) && <p className="rounded-lg bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-200">{error || renderError}</p>}
    <div ref={mapRef} className="h-[min(68dvh,760px)] min-h-[480px] w-full overflow-hidden rounded-lg border bg-white outline-none focus-visible:ring-2 focus-visible:ring-teal-600 dark:bg-gray-950" aria-label="可折叠管理方案思维导图" />
    {unboundProducts.length > 0 && <div className="flex flex-wrap items-center gap-2 border-t pt-3 text-xs"><span className="font-semibold text-gray-600 dark:text-gray-300">可兑换物品</span>{unboundProducts.map(product => <button type="button" key={product.id} disabled={!product.editable} onClick={() => onNavigate({ tab: 'rewards', returnContext: { sourceType: 'reward_item', sourceId: product.id, productId: product.id, fingerprint: `product:${product.id}:${product.title}:${product.price}:${product.description || ''}` } })} className="rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-left font-medium text-emerald-900 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-100">【物品】{product.icon || '礼物'} {product.title} · {product.price} 金币</button>)}</div>}
    
    <ManagementBundleImportModal 
      runtime={runtime} 
      isOpen={importModalOpen} 
      bundle={importedBundle} 
      onClose={() => setImportModalOpen(false)} 
      onSuccess={handleImportSuccess} 
    />
  </div>
}
