import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./RewardsPage.tsx', import.meta.url), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

assert(source.includes('inputMode="decimal"') && source.includes('type="text"'), 'custom spend uses a direct decimal text input')
assert(source.includes("value.replace(/[^\\d.]/g, '')") && source.includes("slice(0, 2)"), 'custom spend keeps only a two-decimal monetary value')
assert(!source.includes('type="number" min="0.01" step="0.01"'), 'custom spend does not render browser increment controls')
assert(source.includes('await buyReward(selectedReward.id, amount, customSpendNote.trim())') && source.includes('setPurchaseError(reason?.message'), 'a rejected purchase remains in the sheet and exposes a retryable error')
assert(source.includes('customSpendInputRef.current?.focus()') && source.includes('value={customSpend}'), 'a failed custom spend preserves and refocuses the entered amount')
assert(source.includes('customSpendNote') && source.includes('placeholder="具体买了什么（必填）"') && source.includes('maxLength={120}'), 'custom spend requires a bounded purchase note below the amount')
assert(source.includes('await buyReward(selectedReward.id, amount, customSpendNote.trim())') && source.includes('setCustomSpendNote(\'\')'), 'the purchase note is submitted and clears only after success')
console.log('custom spend input contracts passed')
