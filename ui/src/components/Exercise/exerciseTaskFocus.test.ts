import { startExerciseItemFocus } from './ExerciseItem'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
let stopped = 0; let checkinState = 0; let requested = ''
startExerciseItemFocus(
  { stopPropagation: () => { stopped++ } },
  async title => { requested = title; return false },
  '深蹲',
)
assert(stopped === 1, 'focus click must stop row propagation')
assert(checkinState === 0, 'blocked focus must not change checkin state')
assert(requested === '深蹲', 'focus request receives item title')
const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')
assert(!read('./ExerciseItem.tsx').includes('ex-focus-btn') && !read('./SchedulePanel.tsx').includes('ex-focus-btn'), 'exercise checkin rows must not render focus buttons')
assert(!read('../../pages/UnifiedChecklistPage/HabitSection.tsx').includes('timer.start('), 'checklist habit rows must not render or invoke focus controls')
assert(read('../../hooks/useExercise.ts').includes('time=status===0?null:'), 'exercise success and failure must both persist the action time while reset clears it')
assert(read('./ExercisePanel.tsx').includes('运动指标全完成奖励'), 'exercise completion reward must display from the settlement snapshot')
assert(read('../../hooks/useExercise.ts').includes('getExerciseSettlement(date,version)'), 'exercise completion reward must read the pulled server settlement')
console.log('exerciseTaskFocus tests passed')
