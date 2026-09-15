import { type ExercisePlanDefinition } from '@models/ExercisePlanSampleDataInitializer'

export function ExerciseReferencePanels({ planDefinition }: { planDefinition: ExercisePlanDefinition }) {
  return <><div className="ex-section">饮食原则</div><div className="ex-card">{planDefinition.diet.map(x => <div className="diet-row" key={x.time}><b>{x.time}</b><div>{x.content}<small>{x.note}</small></div></div>)}<div className="drink">💧 无糖茶/黑咖啡/气泡水随便喝　⚠️ 零卡可乐偶尔可以　❌ 果汁不喝</div></div><div className="ex-section">进阶节点</div><div className="ex-card">{planDefinition.progress.map(x => <div className="prog-row" key={x.when}><b>{x.when}</b><span>{x.text}</span></div>)}</div></>
}
