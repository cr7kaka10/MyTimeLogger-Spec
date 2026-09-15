import { mapLearningTaskCategories } from './learningCategoryMapping'

const categories = [{ id: 16, name: '输入' }, { id: 17, name: '输出' }]
const mapped = mapLearningTaskCategories([{ tasks: [{ group_name: '输入' }, { group_name: '输出' }] }], categories)
if (mapped[0].tasks[0].category_id !== 16 || mapped[0].tasks[1].category_id !== 17) throw new Error('must map account category IDs')
for (const [krs, rows] of [[[{ tasks: [{}] }], categories], [[{ tasks: [{ group_name: '输入' }] }], categories.slice(0, 1)]]) {
  try { mapLearningTaskCategories(krs as any[], rows as any[]); throw new Error('invalid import accepted') }
  catch (error) { if (!String(error).includes('分类')) throw error }
}
console.log('learning category mapping contracts passed')
