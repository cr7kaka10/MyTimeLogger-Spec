import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { readFileSync } from 'node:fs'
import { HabitActions } from './HabitActions'
import { HabitEditor } from './HabitEditor'

const assert = (ok: unknown, message: string) => { if (!ok) throw new Error(message) }
const habit = { id: 'local_test', name: '<阅读>', icon: '📖', color: '', category_id: null,
  sort_order: 0, is_active: 0, difficulty: 'easy', source: 'local' }
const view = (fields = {}) => renderToStaticMarkup(createElement(HabitActions, {
  habit: { ...habit, ...fields }, onClose() {}, onEditReward() {},
}))
const local = view()
assert(local.includes('习惯管理') && local.includes('进行中'), 'sheet has a titled status header')
assert(local.includes('编辑习惯') && local.includes('奖励设置'), 'primary and secondary actions are named')
assert(local.includes('危险操作') && !local.includes('逻辑删除'), 'danger zone avoids internal lifecycle terms')
assert(local.includes('&lt;阅读&gt;') && !local.includes('<阅读>'), 'habit names are escaped')
const edit = renderToStaticMarkup(createElement(HabitEditor, { habit, categories: [{ id: 9, name: '健康' }], busy: false, message: '', onClose() {}, onSave: async () => true }))
assert(edit.includes('value="&lt;阅读&gt;"') && edit.includes('编辑本地习惯'), 'editor loads existing name')
assert(edit.includes('排期') && edit.includes('未分类') && edit.includes('健康'), 'editor exposes persisted schedule and active categories')
assert(!edit.includes('难度') && !local.includes('难度'), 'difficulty is absent from local habit UI')
const sectionSource = readFileSync(new URL('./HabitSection.tsx', import.meta.url), 'utf8')
const actionsSource = readFileSync(new URL('./HabitActions.tsx', import.meta.url), 'utf8')
const detailsSource = readFileSync(new URL('./HabitDetails.tsx', import.meta.url), 'utf8')
const sheetSource = readFileSync(new URL('../../components/common/BottomSheet.tsx', import.meta.url), 'utf8')
assert(!sectionSource.includes('LocalHabitHistory') && !sectionSource.includes('已删除的本地习惯'), 'history entry is absent without affecting creator')
assert(sectionSource.includes('新建原生习惯') && sectionSource.includes('＋习惯'), 'habit creator remains visible')
assert(['习惯概览', '奖励', '近期打卡'].every(label => detailsSource.includes(label)), 'details use named sections')
assert(['编辑习惯排期', '编辑习惯分类'].every(label => detailsSource.includes(label)), 'schedule and category summaries are keyboard buttons')
assert(detailsSource.includes('onEdit={onEditReward}') && actionsSource.includes("onEditHabit={() => setMode('edit')}"), 'summary cards use the existing editors')
assert(actionsSource.includes("onClick={() => setMode('delete')}") && actionsSource.match(/deleteHabit/g)?.length === 1, 'first delete action only enters confirmation')
assert(actionsSource.includes('onEditReward') && actionsSource.includes('从清单隐藏，保留历史'), 'reward handoff and delete copy are explicit')
assert([actionsSource, detailsSource, edit].every(value => value.includes('dark:')), 'sheet sections support dark theme')
assert(actionsSource.includes('focus-visible:') && sheetSource.includes("event.key === 'Escape'"), 'focus and keyboard close remain visible')
console.log('habit management rendering: 12 assertions passed (not device E2E)')
