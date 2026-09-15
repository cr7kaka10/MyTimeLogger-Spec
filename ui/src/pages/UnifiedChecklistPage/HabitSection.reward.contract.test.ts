import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./HabitSection.tsx', import.meta.url)), 'utf8')

if (!source.includes('SourceRewardSummary') || !source.includes('sourceType="habit"')) {
  throw new Error('each habit must read its own authoritative reward summary')
}
if (!source.includes('SourceRewardEditor') || !source.includes('sourceId={rewardHabit.id}')) {
  throw new Error('habit reward updates must use the shared source editor')
}
if (!source.includes("onToggleCheckin(habit.id, selectedDateStr, 2)") || !source.includes("onToggleCheckin(habit.id, selectedDateStr, 1)")) {
  throw new Error('reward editing must not replace success or failure check-in actions')
}

console.log('habit reward contracts passed')
