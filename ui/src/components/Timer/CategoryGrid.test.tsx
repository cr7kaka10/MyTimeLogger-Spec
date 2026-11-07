import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { CategoryGrid } from './CategoryGrid'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const categories = [
  { id: 1, name: '输入', icon: 'book', color: '#f00', sort_order: 1 },
  { id: 2, name: '输出', icon: 'trophy', color: '#f00', sort_order: 2 },
  { id: 8, name: '娱乐', icon: 'game', color: '#00f', sort_order: 3 },
  { id: 3, name: '副业生产', icon: 'tool', color: '#00f', sort_order: 4 },
  { id: 4, name: '副业研发', icon: 'lab', color: '#00f', sort_order: 5 },
  { id: 5, name: '副业营销', icon: 'money', color: '#00f', sort_order: 6 },
  { id: 6, name: '工作', icon: 'work', color: '#00f', sort_order: 7 },
] as any
const render = (name: string | null, state: any) => renderToStaticMarkup(
  <CategoryGrid categories={categories} currentCategory={name ? categories.find((item: any) => item.name === name) : null} timerState={state} onStart={() => undefined} onSwitch={() => undefined} />,
)

const input = render('输入', 'studying')
assert((input.match(/disabled=""/g) || []).length === 5, 'input focus should keep only input/output enabled')
assert((input.match(/aria-disabled="true"/g) || []).length === 5, 'disabled cards should expose aria-disabled')
assert(input.includes('grayscale'), 'disabled cards should be visibly grey')
const output = render('输出', 'studying')
assert((output.match(/disabled=""/g) || []).length === 5, 'output focus should keep only input/output enabled')
assert((render('副业研发', 'studying').match(/disabled=""/g) || []).length === 4, 'side-business focus should keep three peers enabled')
assert((render('工作', 'studying').match(/disabled=""/g) || []).length === 6, 'work focus should keep only work enabled')
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
