import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { HabitActions } from './HabitActions'
import { HabitEditor } from './HabitEditor'
import { LocalHabitHistory } from './LocalHabitHistory'

const assert = (ok: unknown, message: string) => { if (!ok) throw new Error(message) }
const habit = { id: 'local_test', name: '<阅读>', icon: '📖', color: '', category_id: null,
  sort_order: 0, is_active: 0, difficulty: 'easy', source: 'local' }
const view = (fields = {}) => renderToStaticMarkup(createElement(HabitActions, { habit: { ...habit, ...fields }, onClose() {} }))
const local = view()
assert(local.includes('编辑') && local.includes('删除（保留历史）'), 'active local habits expose management')
assert(local.includes('&lt;阅读&gt;') && !local.includes('<阅读>'), 'habit names are escaped')
const mirror = view({ source: 'ticktick' })
assert(mirror.includes('请在滴答清单操作') && !mirror.includes('删除（保留历史）'), 'mirror lifecycle is read-only')
assert(!view({ is_active: 1 }).includes('删除（保留历史）'), 'archived local history is read-only')
const edit = renderToStaticMarkup(createElement(HabitEditor, { habit, busy: false, message: '', onClose() {}, onSave: async () => true }))
assert(edit.includes('value="&lt;阅读&gt;"') && edit.includes('编辑本地习惯'), 'editor loads existing name')
assert(renderToStaticMarkup(createElement(LocalHabitHistory)).includes('已删除的本地习惯'), 'history entry does not depend on active rows')
console.log('habit management rendering: 6 assertions passed (not device E2E)')
