import { buildLearningDecompositionPrompt, LEARNING_DECOMPOSITION_SKILL_VERSION } from './learningDecompositionSkill'
import { parseLearningPlanJson } from './learningPlanParser'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
for (const prompt of [buildLearningDecompositionPrompt(), buildLearningDecompositionPrompt(10)]) {
  assert(prompt.includes('每个task都必须显式包含 group_name'), 'group_name must be mandatory')
  assert(prompt.includes('只能是“输入”或“输出”'), 'only input/output may be generated')
}
assert(buildLearningDecompositionPrompt().includes('recommended_duration'), 'duration recommendation is required')
assert(buildLearningDecompositionPrompt(10).includes('不得超过 40 个'), 'fixed duration task limit is required')

assert(parseLearningPlanJson('{"krs":[{"tasks":[{"group_name":"输出"}]}]}').krs[0].tasks[0].group_name === '输出', 'valid output must survive')
for (const json of ['{"krs":[{"tasks":[{}]}]}', '{"krs":[{"tasks":[{"group_name":"生活"}]}]}']) {
  try { parseLearningPlanJson(json); throw new Error('invalid category was accepted') }
  catch (error) { assert(String(error).includes('分类无效'), 'error must locate invalid category') }
}
console.log(`${LEARNING_DECOMPOSITION_SKILL_VERSION} contracts passed`)
