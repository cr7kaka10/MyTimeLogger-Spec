import { calcScore, exerciseItemPoints, scheduleItemScore } from './exerciseScore'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }

const plan: any = {
  version: 'v1', exercisePoints: 40,
  exercisePlan: { 周一: { gym: [{ s: '无氧', sets: '3×15次' }, { s: '有氧', sets: '25分钟' }], rain: [{ s: '无氧', sets: '3×15次' }] } },
  weekdayScore: [[0, 5, '检验'], [1, 10, '工作'], [1, 1.25, '守时', '10:30'], [2, 10, '工作'], [2, 1.25, '守时', '12:20'], [3, 10, '工作'], [3, 1.25, '守时', '15:10'], [4, 10, '工作'], [4, 1.25, '守时', '17:00'], [5, 5, '拉伸'], [6, 5, '拉伸']],
  saturdayScore: [], sundayScore: [], categoryOrder: ['运动', '工作', '拉伸', '检验', '守时'],
}

const score = calcScore('周一', '2026-08-24', false, {}, plan)
const maxima = Object.fromEntries(Object.entries(score.cats).map(([key, value]: any) => [key, value.m]))
assert(score.total === 0, 'unfinished weekday score must be zero')
assert(JSON.stringify(maxima) === JSON.stringify({ 检验: 5, 工作: 40, 守时: 5, 拉伸: 10, 运动: 40 }), 'weekday dimensions must be 40/40/10/5/5')
assert(Object.values(score.cats).reduce((sum: number, value: any) => sum + value.m, 0) === 100, 'weekday maximum must total 100')

const completed = scheduleItemScore('周一', '2026-08-24', 1, { status: 1, completed_time: '10:40' }, plan)
const unfinished = scheduleItemScore('周一', '2026-08-24', 1, { status: 0 }, plan)
assert(completed.earned === 10.75 && completed.max === 11.25, '10-minute late work item must score 10.75/11.25')
assert(unfinished.earned === 0 && unfinished.max === 11.25, 'unfinished work item must score 0/11.25')

const points = exerciseItemPoints(plan.exercisePlan.周一.gym, 40)
assert(points.reduce((sum, value) => sum + value, 0) === 40, 'exercise item maximums must total 40')
assert(points[1] >= points[0], 'higher difficulty must not score below lower difficulty')

const v2 = { ...plan, version: 'v2' }
const v2Late = scheduleItemScore('周一', '2026-08-24', 1, { status: 1, completed_time: '11:01' }, v2)
assert(v2Late.earned === 10.13 && v2Late.max === 11.25, 'v2 late timing keeps 0.1 floor')

console.log('exercise score contract passed')
