import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./SessionEditSheet.tsx', import.meta.url)), 'utf8')
const categoryIcon = readFileSync(fileURLToPath(new URL('../common/CategoryIcon.tsx', import.meta.url)), 'utf8')
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

assert(source.includes("import { CategoryIcon } from '../common/CategoryIcon'"), 'category picker must reuse the controlled CategoryIcon renderer')
assert(!source.includes('<select'), 'session category picker must not fall back to a native text-only select')
assert(source.includes('aria-haspopup="dialog"') && source.includes('role="radiogroup"') && source.includes('role="radio"'), 'category control must expose dialog and single-choice semantics')
assert(source.includes("[{ id: null, name: '无分类'"), 'picker must provide a dedicated uncategorized choice')
assert(source.includes('setCategoryId(category.id); setCategoryPickerOpen(false)'), 'choosing a category must update only the draft and close the picker')
assert(source.includes('onClose={() => setCategoryPickerOpen(false)}'), 'closing the picker without selection must preserve the draft')
assert(source.includes('aria-checked={checked}'), 'the current draft category must have an explicit selected state')
assert(source.includes('icon={category.icon} color={category.color}'), 'every category row must render its existing icon and color through CategoryIcon')
assert(source.includes('icon={selectedCategory?.icon}') && source.includes("selectedCategory?.name || '无分类'"), 'the field must show the selected icon and name')
assert(categoryIcon.includes('parseAtmIconName') && categoryIcon.includes('if (!atmName) return') && !categoryIcon.includes('fetch('), 'missing or unknown icons must use the shared safe fallback without network loading')

console.log('session category picker contracts passed')
