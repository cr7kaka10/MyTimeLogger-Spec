const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const source = fs.readFileSync(new URL('./PageQuickActions.tsx', import.meta.url), 'utf8') as string

assert(source.includes("const noDrag = { WebkitAppRegion: 'no-drag' }"), 'quick actions must define a no-drag region')
assert(source.includes('<nav aria-label="页面快捷操作" style={noDrag}'), 'quick action nav must opt out of titlebar dragging')
assert(source.includes('onOpenManagementPlanHistory'), 'management plan history action must use its dedicated callback')
assert(source.includes('aria-label="管理方案历史"'), 'management plan history action must have an accurate accessible label')
assert(source.includes('onClick={() => onOpenManagementPlanHistory()}'), 'history action must not receive the click event as request text')
assert(!source.includes('aria-label="AI 管理方案"'), 'top action must not duplicate the homepage draft entry')

for (const [label, tab] of [['时间目标', 'goals'], ['我的背包', 'backpack'], ['奖励商店', 'rewards']] as const) {
  const button = new RegExp(`aria-label="${label}"[^\\n]*style=\\{noDrag\\}[^\\n]*onClick=\\{\\(\\) => onNavigate\\('${tab}'\\)\\}`)
  assert(button.test(source), `${label} must remain an accessible no-drag navigation button`)
}

for (const label of ['明暗切换', '我的金币']) {
  const button = new RegExp(`aria-label="${label}"[^\\n]*style=\\{noDrag\\}`)
  assert(button.test(source), `${label} must remain a no-drag button`)
}

console.log('PageQuickActions titlebar contracts passed')
