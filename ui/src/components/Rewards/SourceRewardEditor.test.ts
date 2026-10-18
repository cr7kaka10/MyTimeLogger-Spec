import { readFileSync } from 'node:fs'

const editor = readFileSync(new URL('./SourceRewardEditor.tsx', import.meta.url), 'utf8')
const sheet = readFileSync(new URL('./RewardAddSheet.tsx', import.meta.url), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
assert(!sheet.includes('绑定解锁任务') && !sheet.includes('绑定解锁目标'), 'product sheet must not expose source bindings')
assert(editor.includes("item.redemption_mode === 'task' && item.fulfillment_mode === 'fragment'"), 'only completion reward products are selectable')
assert(editor.includes('source.bindItem(item.id)'), 'sources bind products through the dedicated source binding API')
assert(editor.includes('itemRewards.map'), 'all sources can retain multiple reward products')
assert(editor.includes('source.unbindItem(item.id)'), 'each item reward can be removed without deleting the item')
assert(editor.includes('<RewardAddSheet'), 'item creation and editing reuse the store sheet')
assert(editor.includes('activePieces') && editor.includes('targetPieces'), 'count fragments render as exact piece progress')
assert(editor.includes('本周期') && editor.includes('expiresAt'), 'period usage and clearing time are visible')
assert(editor.includes("measureMode === 'percent'"), 'legacy percentage fragments remain renderable')
assert(editor.includes('历史百分比') && editor.includes('setSheetReward(item)'), 'legacy products expose their mode and an explicit edit path')
assert(editor.includes('data.convert_fragment_to_count === true'), 'confirmed conversion reaches the update API')
console.log('source reward editor contracts passed')
