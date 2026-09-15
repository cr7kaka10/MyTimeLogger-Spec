// ui/src/components/Categories/CategoryManager.tsx
import { memo, useCallback, useEffect, useState } from 'react'
import type { CategoryFormData } from '../../types'
import { getDatabase } from '../../db'
import { BottomSheet } from '../common/BottomSheet'
import { CategoryIcon } from '../common/CategoryIcon'
import { CategoryIconPicker } from './CategoryIconPicker'
import { hexToRgb, rgbToHex } from '@core/CategoryIconKey'

const COLORS = ['#5E81AC', '#A3BE8C', '#D08770', '#EBCB8B', '#B48EAD', '#BF616A', '#81A1C1', '#8FBCBB']

interface Props {
  onClose: () => void
}

export const CategoryManager = memo(({ onClose }: Props) => {
  const [categories, setCategories] = useState<any[]>([])
  const [editing, setEditing] = useState<CategoryFormData | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    getDatabase().then((db: any) => setCategories(db.getCategories()))
  }, [refresh])

  const handleSave = useCallback(async (data: CategoryFormData) => {
    const db = await getDatabase()
    if (data.id) {
      db.updateCategory(data.id, data as any)
    } else {
      db.addCategory(data.name, data.icon, data.color, data.group_name)
    }
    setRefresh(prev => prev + 1); setEditing(null); setShowAdd(false)
  }, [])

  const handleDelete = useCallback(async (id: number) => {
    const db = await getDatabase()
    db.deleteCategory(id)
    setRefresh(prev => prev + 1)
  }, [])

  return (
    <div className="min-h-full space-y-4 bg-[#FAFAFA] p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">分类管理</h1>
          <div className="mt-2 text-sm text-gray-400">{categories.length} 个分类</div>
        </div>
        <button onClick={onClose} className="text-sm text-blue-600 font-semibold">← 返回设置</button>
      </header>

      <button onClick={() => setShowAdd(true)} className="h-12 w-full rounded-xl bg-blue-500 text-base font-semibold text-white active:bg-blue-600">+ 新增分类</button>

      <div className="space-y-2">
        {categories.map(cat => (
          <div key={cat.id} className="flex items-center gap-3 rounded-xl border border-gray-100 bg-white p-3">
            <CategoryIcon icon={cat.icon} color={cat.color} className="h-8 w-8" />
            <span className="flex-1 font-semibold text-gray-900">{cat.name}</span>
            
            {/* 序号输入框（纯文本，无上下箭头） */}
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              value={cat.sort_order}
              onChange={async (e) => {
                const newOrder = parseInt(e.target.value, 10)
                if (isNaN(newOrder) || newOrder < 1 || newOrder > categories.length) {
                  alert(`序号必须在 1~${categories.length} 之间`)
                  e.target.value = cat.sort_order.toString()
                  return
                }
                const db = await getDatabase()
                db.updateCategory(cat.id, { sort_order: newOrder })
                setRefresh(prev => prev + 1)
                // 触发全局事件通知其他组件刷新分类列表
                window.dispatchEvent(new CustomEvent('categories-updated'))
              }}
              className="w-16 rounded-lg border border-gray-200 px-2 py-1 text-center text-sm outline-none focus:border-blue-400"
            />
            
            <span className="text-xs rounded-full bg-gray-100 px-2 py-0.5 text-gray-500">{cat.group_name}</span>
            <button onClick={() => setEditing({ id: cat.id, name: cat.name, icon: cat.icon, color: cat.color, group_name: cat.group_name, sort_order: cat.sort_order })}
              className="h-8 w-8 rounded-lg text-gray-400 active:bg-gray-100">✏️</button>
            <button onClick={() => handleDelete(cat.id)}
              className="h-8 w-8 rounded-lg text-gray-400 active:bg-red-50 active:text-red-500">🗑</button>
          </div>
        ))}
      </div>

      {/* 新增/编辑 Sheet */}
      {(showAdd || editing) && (
        <BottomSheet open onClose={() => { setShowAdd(false); setEditing(null) }}>
          <CategoryForm data={editing} onSave={handleSave} onClose={() => { setShowAdd(false); setEditing(null) }} />
        </BottomSheet>
      )}
    </div>
  )
})

// 内联分类表单
const CategoryForm = memo(({ data, onSave, onClose }: { data: CategoryFormData | null; onSave: (d: CategoryFormData) => void; onClose: () => void }) => {
  const [name, setName] = useState(data?.name || '')
  const [icon, setIcon] = useState(data?.icon?.startsWith('atm:') ? data.icon : 'atm:cat_96')
  const [color, setColor] = useState(data?.color || COLORS[0])
  const rgb = hexToRgb(color) ?? [0, 0, 0]
  const updateChannel = (index: number, raw: string) => {
    const next = [...rgb] as [number, number, number]
    next[index] = Number(raw)
    const hex = rgbToHex(...next)
    if (hex) setColor(hex)
  }

  return (
    <div className="space-y-4 p-4 font-sans">
      <h3 className="text-lg font-bold text-gray-900">{data?.id ? '编辑分类' : '新增分类'}</h3>

      <div>
        <span className="mb-1.5 block pl-1 text-xs font-semibold text-gray-400">分类名称</span>
        <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="分类名称" className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-sm outline-none focus:border-blue-400" />
      </div>

      <CategoryIconPicker icon={icon} color={color} onChange={setIcon} />

      <div>
        <span className="text-xs font-semibold text-gray-400 pl-1 block mb-1.5">选择颜色</span>
        <div className="flex flex-wrap gap-2">{COLORS.map(c => (
          <button key={c} type="button" onClick={() => setColor(c)} className={`h-7 w-7 rounded-full transition-all duration-200 ${color === c ? 'ring-2 ring-offset-2 ring-blue-500 scale-110' : 'hover:scale-105'}`} style={{ backgroundColor: c }} />
        ))}</div>
        <div className="mt-3 grid grid-cols-[1.4fr_repeat(3,1fr)] gap-2">
          <input aria-label="Hex 颜色" value={color} onChange={e => setColor(e.target.value.toUpperCase())} className="rounded-lg border border-gray-200 px-2 py-2 text-center text-xs" />
          {(['R', 'G', 'B'] as const).map((label, index) => <input key={label} aria-label={`${label} 通道`} type="number" min="0" max="255" value={rgb[index]} onChange={e => updateChannel(index, e.target.value)} className="min-w-0 rounded-lg border border-gray-200 px-1 py-2 text-center text-xs" />)}
        </div>
      </div>

      <button onClick={() => onSave({ id: data?.id, name: name.trim(), icon, color, group_name: data?.group_name || (['输入', '输出'].includes(name.trim()) ? name.trim() : '生活') })}
        disabled={!name.trim() || !hexToRgb(color)} className="h-12 w-full rounded-xl bg-blue-600 text-base font-semibold text-white active:bg-blue-700 disabled:opacity-50 transition-all shadow-md shadow-blue-100">保存</button>
    </div>
  )
})

CategoryForm.displayName = 'CategoryForm'
CategoryManager.displayName = 'CategoryManager'
