import type { ExerciseItem as Item } from '@models/ExercisePlanSampleDataInitializer'
import type { ExerciseState } from '../../hooks/useExercise'
import { PressableCheckRow } from './PressableCheckRow'
import { formatScore } from '../../utils/exerciseScore'

export const startExerciseItemFocus = (event: { stopPropagation: () => void }, start: (title: string) => Promise<boolean>, title: string) => {
  event.stopPropagation()
  void start(title)
}

export function ExerciseItem({
  item,
  state,
  color,
  onState,
}: {
  item: Item
  state?: ExerciseState
  color: string
  onState: (s: number) => void
}) {
  const done = state?.status === 1
  const skip = state?.status === -1
  const tags = [item.s, item.floor && '地面', item.core && '核心', item.hang && '悬挂', item.stairs && '爬楼', item.isNew && '新增'].filter(Boolean)

  return (
    <PressableCheckRow className={`${done ? 'done' : ''} ${skip ? 'skip' : ''}`} onTap={() => onState(done ? 0 : 1)} onLong={() => onState(skip ? 0 : -1)}>
      <i className={`ex-box ${done ? 'done' : skip ? 'skip' : ''}`} style={done ? { borderColor: color, background: color } : {}}>
        {done ? '✓' : skip ? '✗' : ''}
      </i>
      <div className="ex-row-main">
        <span className={done ? 'struck' : ''}>{item.name}</span>
        <span className="ex-sets" style={{ color, background: `${color}18` }}>{item.sets}</span>
        {tags.map(x => <span className="ex-tag" key={String(x)}>{x}</span>)}
        <small>💪 {item.intensity}</small>
        {item.prog && <small className="progress">📈 进阶：{item.prog}</small>}
        {state?.max_points != null && <span className="ex-score-meta"><em>{formatScore(done ? state.earned_points : 0)}/{formatScore(state.max_points)} 分{done && state.difficulty ? ` · ${state.difficulty}` : ''}</em>{done && state?.completed_time && <em>✓ 打卡 {state.completed_time}</em>}</span>}
        {skip && <b>✗ 已标记跳过（长按可取消）</b>}
      </div>
    </PressableCheckRow>
  )
}
