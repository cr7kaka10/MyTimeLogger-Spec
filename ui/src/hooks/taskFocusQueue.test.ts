import { decideTaskFocus, executeTaskFocus } from './taskFocusRouting'

const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
let started = 0; let retargeted = 0; let switched = 0
const actions = {
  started: () => { started++ },
  retargeted: () => { retargeted++ },
  switched: () => { switched++ },
}
const run = async () => {
  await executeTaskFocus(decideTaskFocus('studying', 1, '输入', 2, '输出'), actions)
  await executeTaskFocus(decideTaskFocus('studying', 2, '输出', 9, '工作'), actions)
  assert(switched === 1 && started + retargeted === 0, 'same-group handoff executes while cross-group stays blocked')
  await executeTaskFocus(decideTaskFocus('studying', 1, '输入', 1), actions)
  assert(retargeted === 1 && started === 0 && switched === 1, 'same category only retargets')
  await executeTaskFocus(decideTaskFocus('countup_studying', 8, '娱乐', 9), actions)
  assert(switched === 2, 'normal cross-category uses switch path')
  let queue = Promise.resolve()
  const enqueue = (result: ReturnType<typeof decideTaskFocus>) => {
    const job = queue.then(() => executeTaskFocus(result, actions))
    queue = job.then(() => undefined)
    return job
  }
  await Promise.all([enqueue(decideTaskFocus('stopped', null, '', 1)), enqueue(decideTaskFocus('short_breaking', 1, '输入', 1))])
  assert(started === 1 && retargeted === 2, 'queued decisions each execute exactly once')
  console.log('taskFocusQueue tests passed')
}
void run()
