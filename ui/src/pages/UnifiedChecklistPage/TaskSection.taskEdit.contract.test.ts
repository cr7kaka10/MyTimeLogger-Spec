import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const test = (name: string, body: () => void) => { body(); console.log(`passed: ${name}`) }
const source = readFileSync(fileURLToPath(new URL('./TaskSection.tsx', import.meta.url)), 'utf8')

test('active checklist task section opens the full task edit dialog', () => {
  if (!source.includes("TaskEditDialog") || !source.includes('onUpdateTask')) throw new Error('active checklist must use the full task edit command')
  if (!source.includes('setEditingTask(task)')) throw new Error('right-click update must open the task edit dialog')
  if (source.includes('onUpdateTitle')) throw new Error('active checklist must not retain the title-only update path')
  if (!source.includes('已完成任务需在滴答清单调整') || !source.includes('重复任务需在滴答清单调整')) throw new Error('completed and repeating tasks need stable edit restrictions')
})

test('checklist task details and edit dialog share authoritative rewards', () => {
  const dialog = readFileSync(fileURLToPath(new URL('../../components/Checklist/TaskEditDialog.tsx', import.meta.url)), 'utf8')
  if (!source.includes('SourceRewardSummary') || !source.includes('sourceType="checklist_task"')) throw new Error('task cards must show the source reward summary')
  if ((source.match(/sourceType="checklist_task"/g) ?? []).length < 2) throw new Error('active and completed task cards must both show rewards')
  if (!dialog.includes('金币奖励') || !dialog.includes('物品奖励') || !dialog.includes('SourceRewardEditor')) throw new Error('task editor must expose both reward rows')
  if (!dialog.includes('await sourceReward.saveCoins(coins)') || !dialog.includes("result?.status !== 'confirmed'")) throw new Error('task fields and coins must save sequentially before close')
})
