import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { TabBar } from './TabBar'

declare const test: (name: string, body: () => void) => void
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

test('all bottom tabs use the same platform-independent SVG contract', () => {
  const html = renderToStaticMarkup(<TabBar activeTab="timer" onChange={() => undefined} />)
  const svgs = html.match(/<svg\b[^>]*>/g) || []
  assert(svgs.length === 7, `expected 7 SVG tab icons, received ${svgs.length}`)
  assert(svgs.every(svg => /stroke="currentColor"/.test(svg) && /viewBox="0 0 24 24"/.test(svg)), 'every icon must inherit currentColor and share the same viewBox')
  assert(!/[⏱📖📚☑🏋️🌙]/u.test(html), 'bottom tabs must not fall back to system Emoji')
  for (const label of ['计时', '时间书', '学习', '清单', '运动', '睡眠', '设置']) {
    assert(html.includes(`>${label}<`), `${label} must keep its accessible text label`)
  }
  assert((html.match(/aria-hidden="true"/g) || []).length === 7, 'decorative SVGs must not duplicate accessible labels')
  assert(html.includes('text-blue-600') && html.includes('text-gray-400'), 'active and inactive color contracts must remain')
})
