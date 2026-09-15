import { memo, useMemo, useState } from 'react'
import { ATM_ICON_ENTRIES, ATM_ICON_GROUP_BY_NAME, type AtmIconGroup } from '../../assets/atmIconManifest'
import { CategoryIcon } from '../common/CategoryIcon'

const SEARCH_ALIASES: Record<string, string[]> = {
  家庭: ['fam_'], 运动: ['sp_'], 饮食: ['ec_', 'hpcd_'], 吃饭: ['ec_', 'hpcd_'],
  生活: ['hpcd_'], 工作: ['st_'], 营销: ['fs_'], 医疗: ['mi_'], 交通: ['tt_'],
}

export const CategoryIconPicker = memo(({ icon, color, onChange }: { icon: string; color: string; onChange: (icon: string) => void }) => {
  const atmName = icon.startsWith('atm:') ? icon.slice(4) : ''
  const [tab, setTab] = useState<AtmIconGroup>(ATM_ICON_GROUP_BY_NAME.get(atmName) || 'free')
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase()
    const aliases = SEARCH_ALIASES[term] || []
    return ATM_ICON_ENTRIES.filter(entry => entry.group === tab && (!term || entry.name.includes(term) || aliases.some(prefix => entry.name.startsWith(prefix))))
  }, [tab, query])
  const chooseTab = (next: AtmIconGroup) => { setTab(next); setQuery('') }
  const buttonClass = (value: string) => `flex h-10 w-10 items-center justify-center rounded-lg transition ${icon === value ? 'bg-blue-50 ring-2 ring-blue-500' : 'hover:bg-gray-100'}`

  return <div className="space-y-2">
    <div className="grid grid-cols-2 gap-2">{(['free', 'premium'] as AtmIconGroup[]).map(value =>
      <button key={value} type="button" onClick={() => chooseTab(value)} className={`rounded-lg px-2 py-2 text-xs font-semibold ${tab === value ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'}`}>{value === 'free' ? 'Free' : 'Premium'}</button>)}</div>
    <input value={query} onChange={event => setQuery(event.target.value)} aria-label={`搜索 ${tab} 图标`} placeholder="搜索编号或大类，如 cat_96、家庭、运动" className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs outline-none focus:border-blue-400" />
    <div className="grid max-h-52 grid-cols-7 gap-1 overflow-y-auto rounded-xl border border-gray-100 bg-gray-50/50 p-2">
      {filtered.map(entry => { const value = `atm:${entry.name}`; return <button key={entry.name} type="button" aria-label={entry.name} title={entry.name} onClick={() => onChange(value)} className={buttonClass(value)}><CategoryIcon icon={value} color={color} className="h-7 w-7" /></button> })}
      {!filtered.length && <div className="col-span-7 py-6 text-center text-xs text-gray-400">没有匹配图标</div>}
    </div>
  </div>
})

CategoryIconPicker.displayName = 'CategoryIconPicker'
