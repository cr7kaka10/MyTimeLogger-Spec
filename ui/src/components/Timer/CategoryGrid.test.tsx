import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { CategoryGrid } from './CategoryGrid'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const categories = [
  { id: 1, name: '输入', icon: 'book', color: '#f00', sort_order: 1 },
  { id: 2, name: '输出', icon: 'trophy', color: '#f00', sort_order: 2 },
  { id: 8, name: '娱乐', icon: 'game', color: '#00f', sort_order: 3 },
] as any
const render = (name: string | null, state: any) => renderToStaticMarkup(
  <CategoryGrid categories={categories} currentCategory={name ? categories.find((item: any) => item.name === name) : null} timerState={state} onStart={() => undefined} onSwitch={() => undefined} />,
)

const input = render('输入', 'studying')
assert((input.match(/disabled=""/g) || []).length === 2, 'input focus should disable two other cards')
assert((input.match(/aria-disabled="true"/g) || []).length === 2, 'disabled cards should expose aria-disabled')
assert(input.includes('grayscale'), 'disabled cards should be visibly grey')
const output = render('输出', 'studying')
assert((output.match(/disabled=""/g) || []).length === 2, 'output focus should disable two other cards')
assert(!render('娱乐', 'countup_studying').includes('disabled=""'), 'normal focus should keep grid enabled')
assert(!render('输入', 'stopped').includes('disabled=""'), 'stopped input should unlock grid')

const nineteenCategories = Array.from({ length: 19 }, (_, index) => ({
  id: index + 1,
  name: `分类${index + 1}`,
  icon: 'book',
  color: '#00f',
  sort_order: 19 - index,
  is_active: 1,
}))
nineteenCategories.push({ id: 20, name: '已停用', icon: 'book', color: '#00f', sort_order: 0, is_active: 0 })
const allCategories = renderToStaticMarkup(
  <CategoryGrid categories={nineteenCategories as any} currentCategory={null} timerState="stopped" onStart={() => undefined} onSwitch={() => undefined} />,
)
assert((allCategories.match(/分类\d+/g) || []).length === 19, 'all 19 active categories should render')
assert(!allCategories.includes('已停用'), 'inactive categories should not render')
const renderedNames = Array.from(allCategories.matchAll(/分类(\d+)/g), match => Number(match[1]))
assert(renderedNames[0] === 19 && renderedNames.at(-1) === 1, 'categories should use sort_order')
assert(allCategories.includes('grid-cols-5'), 'home grid must keep five equal-width columns on Android')
assert(!allCategories.includes('grid-cols-3'), 'home grid must not collapse to three columns')

console.log('CategoryGrid tests passed')
