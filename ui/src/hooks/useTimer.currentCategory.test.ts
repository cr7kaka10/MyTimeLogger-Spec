import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { parseAtmIconName } from '@core/CategoryIconKey'
import { ATM_ICON_NAMES } from '../assets/atmIconManifest'
import { resolveCurrentTimerCategory } from './currentTimerCategory'

const activity = {
  id: 19,
  name: '活动',
  icon: 'atm:sp_068',
  color: '#E372C7',
  group_name: '生活',
  sort_order: 19,
}

const beforeCategories = resolveCurrentTimerCategory([], activity.id, activity.name)
assert(beforeCategories && beforeCategories.icon === '' && beforeCategories.color === '', '分类尚未到达时必须保持最小安全对象')

const afterCategories = resolveCurrentTimerCategory([activity], activity.id, activity.name)
assert.deepEqual(afterCategories, activity, '分类到达后必须回填完整图标和颜色')

const recovered = resolveCurrentTimerCategory([activity], 47, activity.name)
assert.deepEqual(recovered, activity, '权威 ID 尚未对齐但名称唯一时必须只读恢复完整视觉元数据')

  const ambiguous = resolveCurrentTimerCategory([activity, { ...activity, id: 47 }], 48, activity.name)
assert.equal(ambiguous?.icon, '', '同名分类不唯一时不得猜测任意分类')

const unknown = resolveCurrentTimerCategory([], 404, '已删除分类')
assert(unknown?.id === 404 && unknown.name === '已删除分类' && unknown.icon === '', '未知分类必须保留安全占位数据')

const invalidIcon = resolveCurrentTimerCategory([{ ...activity, icon: 'atm:missing' }], activity.id, activity.name)
assert.equal(parseAtmIconName(invalidIcon?.icon, ATM_ICON_NAMES), null, '非法图标键必须继续交给既有安全占位符处理')

const hook = readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8')
assert(hook.includes('resolveCurrentTimerCategory(categoriesRef.current, authoritative.category_id, authoritative.category_name)'), '权威计时回填必须读取最新分类引用')
const refreshStart = hook.indexOf('  useEffect(() => {\n    const authoritative = currentTimerCoordinatorRef.current?.snapshot()')
const refreshEffect = hook.slice(refreshStart, refreshStart + 400)
assert(refreshStart >= 0 && !refreshEffect.includes('.refresh(') && !refreshEffect.includes('.command('), '分类补全只能更新显示，不得发起计时命令或同步请求')

console.log('useTimer current category tests passed')
