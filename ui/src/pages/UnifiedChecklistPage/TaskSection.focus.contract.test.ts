import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./TaskSection.tsx', import.meta.url)), 'utf8')

assert(source.includes("from '../../components/common/BottomSheet'"), 'unmatched task focus must use a visible category picker')
assert(source.includes('focusPickerTask'), 'task focus picker state must retain the selected task')
assert(source.includes('aria-label="选择专注分类"'), 'category picker must be accessible')
assert(!source.includes('const choice = prompt('), 'task focus must not depend on the native prompt')
assert(source.includes("result.status === 'blocked'"), 'blocked focus must report its reason')
assert(source.includes("result.status === 'unavailable'"), 'unavailable focus must report its reason')
assert(source.includes('updateActiveTaskId(task.id)') && source.includes("onNavigate('timer')"), 'only successful focus may activate a task and navigate')

console.log('TaskSection focus contract passed')
