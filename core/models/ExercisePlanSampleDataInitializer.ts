export type PlanDay = '周一'|'周二'|'周三'|'周四'|'周五'|'六'|'日'
export const EXERCISE_PLAN_VERSION = 'v0'
export const EXERCISE_PLAN_TITLE = '每日打卡表'
export type Section = '无氧'|'有氧'|'回家后'
export interface DietRule { time:string; content:string; note:string; ruleKey?:string }
export interface ScheduleItem { time:string; item:string; note:string; accent:'diet'|'study'|'sleep'|'stretch'|'default' }
export interface ExerciseItem { name:string; sets:string; intensity:string; s:Section; core?:number; isNew?:number; hang?:number; stairs?:number; floor?:number; prog?:string; scoreScope?:'training'; scorePoints?:number; optional?:number }
export interface ExerciseDay { label:string; color:string; gym:ExerciseItem[]; rain:ExerciseItem[] }
export type ScoreRule=[number,number,string,string?]
export interface ExercisePlanDefinition {
  version:string
  title:string
  sourceName:string
  diet:DietRule[]
  dietRulesValid?:boolean
  weekdaySchedule:ScheduleItem[]
  restSchedule:ScheduleItem[]
  sundayExtra:ScheduleItem
  exercisePlan:Record<Exclude<PlanDay,'六'|'日'>,ExerciseDay> & Partial<Record<'六'|'日',ExerciseDay>>
  progress:{when:string;text:string}[]
  weekdayScore:ScoreRule[]
  saturdayScore:ScoreRule[]
  sundayScore:ScoreRule[]
  categoryOrder:string[]
  exercisePoints:number
}

export const DAYS:PlanDay[]=['周一','周二','周三','周四','周五','六','日']
export const REST_DAYS:PlanDay[]=['六','日']
export const DIET_RULES:DietRule[]=[
  {time:'早饭',content:'妈妈做的主食 + 1–2个鸡蛋',note:'正常吃，主食吃一半就够'},
  {time:'午饭',content:'外卖：1荤 + 1素 + 半份饭或面',note:'荤菜选清蒸/白切/卤，避开红烧糖醋干锅'},
  {time:'晚饭',content:'2个水煮蛋（饿了加一杯牛奶）',note:'⚠️ 这顿不吃主食——最关键的一条'},
]
export const WDAY_SCHED:ScheduleItem[]=[
  {time:'7:30',item:'⚖️ 起床后空腹称体重、体脂并记录',note:'每天记，看2–3周趋势，不纠结单天涨跌',accent:'sleep'},
  {time:'7:30–8:00',item:'🍳 早饭',note:'妈妈做的 + 1–2个鸡蛋，主食吃一半，8点前吃完',accent:'diet'}, {time:'9:00–10:30',item:'📖 学习 第1节',note:'1.5小时',accent:'study'},
  {time:'10:30–10:40',item:'🧘 颈肩拉伸 + 快走',note:'颈部慢转8圈+肩绕环前后各10次，然后快走5分钟，剩余时间上厕所休息',accent:'stretch'},
  {time:'10:50–12:20',item:'📖 学习 第2节',note:'1.5小时',accent:'study'},
  {time:'12:20–13:40',item:'🥡 午饭',note:'1荤+1素+半份饭/面，时间延长到80分钟',accent:'diet'},
  {time:'13:40–15:10',item:'📖 学习 第3节',note:'1.5小时',accent:'study'},
  {time:'15:10–15:20',item:'🦵 靠墙深蹲 + 压腿拉伸',note:'靠墙深蹲3×30秒，然后压腿每侧30秒×2，剩余时间上厕所休息',accent:'stretch'},
  {time:'15:30–17:00',item:'📖 学习 第4节',note:'1.5小时',accent:'study'},
  {time:'20:00–20:20',item:'🥚 晚饭',note:'2个水煮蛋（饿了加牛奶）',accent:'diet'},
  {time:'22:30',item:'😴 睡觉',note:'保证7–8小时',accent:'sleep'},
]
export const REST_SCHED:ScheduleItem[]=[
  {time:'起床后',item:'⚖️ 空腹称体重、体脂并记录',note:'每天记，看趋势',accent:'sleep'}, {time:'早饭',item:'🍳 正常吃早饭',note:'',accent:'diet'},
  {time:'上午',item:'自由安排',note:'',accent:'default'}, {time:'午饭',item:'🥡 正常吃午饭',note:'出去吃先喝汤垫底，荤菜选清蒸白灼',accent:'diet'},
  {time:'下午',item:'🚶 带娃户外活动30分钟+',note:'散步、骑车、玩耍都行',accent:'study'}, {time:'18:00',item:'🥚 晚饭',note:'少吃主食（比平时少一半）',accent:'diet'},
  {time:'22:30',item:'😴 睡觉',note:'',accent:'sleep'},
]
export const SUN_EXTRA:ScheduleItem={time:'周日晚',item:'📝 复盘本周完成情况',note:'记录完成率，写下下周要改进的一件事',accent:'default'}
const H:ExerciseItem={name:'直臂悬挂',sets:'3×10秒',intensity:'手臂伸直抓杠，脚离地，撑住不动；撑不到10秒记下秒数，下次争取多1秒',hang:1,s:'无氧',prog:'弯臂悬挂 → 离心引体 → 引体向上'}
const E=(name:string,sets:string,intensity:string,s:Section,flags:Partial<ExerciseItem>={}):ExerciseItem=>({name,sets,intensity,s,...flags})
export const EXERCISE_PLAN:Record<Exclude<PlanDay,'六'|'日'>,ExerciseDay>={
  周一:{label:'推·胸+肩+三头',color:'#e8523a',gym:[E('推胸训练器','3×15次','最后2–3次感觉费力','无氧'),E('俯卧撑','3×5次 / 跪姿3×8次','最后1–2次明显费力','无氧'),E('推肩训练器','3×15次','最后2–3次感觉费力','无氧'),E('窄距俯卧撑','3×8次','三头肌为主，最后1–2次明显费力','无氧',{isNew:1}),H,E('椭圆漫步机','1×20分钟','热身3分钟(频率55–65) → 中等强度14分钟(频率65–75) → 快蹬1分钟(频率85–90)+慢蹬2分钟(频率55–65)，全程不停只是变速','有氧'),E('爬楼梯','1次 24层','心跳140以上，只上不下，下楼坐电梯','回家后',{stairs:1}),E('卷腹','3×15次','腹部主动发力，不靠惯性','回家后',{core:1,floor:1}),E('平板支撑','3×30秒','全程收紧腹部和臀部，不塌腰','回家后',{core:1,floor:1})],rain:[E('俯卧撑','3×8次 / 跪姿3×15次','最后1–2次明显费力','无氧'),E('钻石俯卧撑','3×5次','三头肌为主，明显费力','无氧'),E('徒手深蹲','3×20次','后半段大腿有酸感','无氧'),E('开合跳','3×30秒','心跳逐渐升到108以上','有氧'),E('高抬腿','3×30秒','心跳125–140，喘但能坚持','有氧'),E('开合跳（收尾）','3×45秒','心跳108–125','有氧'),E('爬楼梯','1次 24层','楼道内爬楼，心跳140以上','回家后',{stairs:1}),E('卷腹','3×15次','腹部主动发力','回家后',{core:1,floor:1}),E('平板支撑','3×30秒','全程收紧不塌腰','回家后',{core:1,floor:1})]},
  周二:{label:'腿+核心',color:'#3ab85a',gym:[E('深蹲训练器','3×15次','最后2–3次大腿明显酸','无氧'),E('蹬腿训练器','3×15次','最后2–3次感觉费力，膝盖不锁死','无氧'),E('膝关节绕环放松','1×2分钟','双手扶膝缓慢绕圈，每个方向15秒+前后摆腿放松，无需器械','无氧'),H,E('太空漫步机','1×10分钟','心跳95–108，低强度，帮腿排乳酸','有氧'),E('椭圆漫步机（放松）','1×10分钟','频率55–65，低强度，帮腿排乳酸','有氧'),E('爬楼梯（减半）','1次 12层','腿天后减半，腿太累可跳过','回家后',{stairs:1}),E('仰卧举腿','3×10次','下腹明显发力，不借助摆腿惯性','回家后',{core:1,floor:1}),E('仰卧起坐','3×15次','起身时呼气，腹部收紧发力','回家后',{core:1,floor:1})],rain:[E('徒手深蹲','4×15次','后半段大腿酸感明显','无氧'),E('弓步蹲','3×左右各10次','最后几次腿部明显费力','无氧'),E('靠墙深蹲','3×撑45秒','后半段大腿明显酸','无氧'),E('高抬腿（热身）','3×30秒','心跳逐渐升到108次','有氧'),E('开合跳（收尾）','3×30秒','心跳95–108','有氧'),E('爬楼梯（减半）','1次 12层','腿天后减半','回家后',{stairs:1}),E('臀桥','3×20次','顶部夹紧臀部保持1秒','回家后',{core:1,floor:1}),E('仰卧起坐','3×15次','腹部收紧发力','回家后',{core:1,floor:1}),E('仰卧举腿','3×10次','下腹明显发力','回家后',{core:1,floor:1})]},
  周三:{label:'拉·背+二头',color:'#3a7ee8',gym:[E('高拉训练器（正握）','3×15次','最后2–3次感觉费力','无氧'),H,E('反握高拉','3×15次','掌心朝自己，刺激二头肌，最后2–3次费力','无氧',{isNew:1}),E('太空漫步机','1×10分钟','心跳95–108','有氧'),E('椭圆漫步机（有氧）','1×15分钟','热身2分钟(频率55–65) → 中等强度10分钟(频率65–75) → 快蹬1分钟(频率85–90)+慢蹬2分钟(频率55–65)，全程不停只是变速','有氧'),E('爬楼梯','1次 24层','心跳140以上，只上不下，下楼坐电梯','回家后',{stairs:1}),E('仰卧起坐','3×15次','起身时呼气，腹部收紧发力','回家后',{core:1,floor:1}),E('平板支撑','3×30秒','全程收紧腹部和臀部','回家后',{core:1,floor:1})],rain:[E('桌边反向划船','3×10次','最后2–3次背部明显发力','无氧'),E('宽距俯卧撑','3×8次','最后1–2次费力','无氧'),E('开合跳','3×30秒','心跳逐渐升到108以上','有氧'),E('高抬腿','3×30秒','心跳125–140','有氧'),E('波比跳','3×8次','心跳140以上，大口喘气','有氧'),E('开合跳（收尾）','3×45秒','心跳108–125','有氧'),E('爬楼梯','1次 24层','楼道内爬楼，心跳140以上','回家后',{stairs:1}),E('仰卧起坐','3×15次','腹部收紧发力','回家后',{core:1,floor:1}),E('平板支撑','3×30秒','全程收紧不塌腰','回家后',{core:1,floor:1})]},
  周四:{label:'纯有氧+核心',color:'#9b3ae8',gym:[H,E('推肩训练器','3×15次','最后2–3次感觉费力','无氧'),E('扭腰器','3×左右各20次','感受腹斜肌收缩，中等强度','无氧',{core:1}),E('站姿提膝','3×左右各15次','腹部保持收紧，轻中等','无氧',{core:1}),E('椭圆漫步机（间歇）','1×18分钟','热身3分钟(频率55–65) → [快蹬1分钟(频率85–90)+慢蹬2分钟(频率55–65)]×4轮(共12分钟) → 收尾3分钟(频率55–65)，全程不停，只是快慢交替蹬','有氧'),E('拉伸架','1×5分钟','每个部位微微感到拉扯即可','有氧'),E('爬楼梯','1次 24层','心跳140以上，只上不下，下楼坐电梯','回家后',{stairs:1}),E('仰卧起坐','3×15次','起身时呼气，腹部收紧发力','回家后',{core:1,floor:1}),E('平板支撑','3×40秒','全程收紧腹部和臀部，不塌腰','回家后',{core:1,floor:1})],rain:[E('开合跳（热身）','1×3分钟','心跳逐渐升至108','有氧'),E('高抬腿','3×45秒','心跳125–140','有氧'),E('波比跳','3×10次','心跳140以上，大口喘气','有氧'),E('原地跑','3×45秒','心跳125–140','有氧'),E('爬楼梯','1次 24层','楼道内爬楼，心跳140以上','回家后',{stairs:1}),E('仰卧起坐','3×15次','腹部收紧发力','回家后',{core:1,floor:1}),E('俄罗斯转体','3×左右各20次','腹部收紧，感受侧腰发力','回家后',{core:1,floor:1}),E('仰卧举腿','3×10次','下腹明显发力','回家后',{core:1,floor:1}),E('平板支撑','3×40秒','全程收紧不塌腰','回家后',{core:1,floor:1})]},
  周五:{label:'推+拉·上半身全',color:'#e8a63a',gym:[E('推胸训练器','3×15次','最后2–3次感觉费力','无氧'),E('高拉训练器（正握）','3×15次','最后2–3次感觉费力','无氧'),E('推肩训练器','3×15次','最后2–3次感觉费力','无氧'),H,E('太空漫步机','1×10分钟','心跳95–108','有氧'),E('椭圆漫步机（有氧）','1×15分钟','热身2分钟(频率55–65) → 中等强度10分钟(频率65–75) → 快蹬1分钟(频率85–90)+慢蹬2分钟(频率55–65)，全程不停只是变速','有氧'),E('爬楼梯','1次 24层','心跳140以上，只上不下，下楼坐电梯','回家后',{stairs:1}),E('卷腹','3×15次','腹部主动发力，不靠惯性','回家后',{core:1,floor:1}),E('平板支撑','3×40秒','全程收紧腹部和臀部','回家后',{core:1,floor:1})],rain:[E('俯卧撑','3×8次 / 跪姿3×15次','最后1–2次明显费力','无氧'),E('桌边反向划船','3×10次','最后2–3次背部明显发力','无氧'),E('钻石俯卧撑','3×5次','明显费力','无氧'),E('宽距俯卧撑','3×8次','最后1–2次费力','无氧'),E('开合跳（热身）','3×30秒','心跳逐渐升至108','有氧'),E('波比跳','3×8次','心跳140以上','有氧'),E('开合跳（收尾）','3×45秒','心跳108–125','有氧'),E('爬楼梯','1次 24层','楼道内爬楼，心跳140以上','回家后',{stairs:1}),E('卷腹','3×15次','腹部主动发力','回家后',{core:1,floor:1}),E('平板支撑','3×40秒','全程收紧不塌腰','回家后',{core:1,floor:1})]},
}
export const PROGRESS=[{when:'第3周',text:'俯卧撑→标准8次，直臂悬挂→稳定20秒，平板支撑→45秒'},{when:'悬挂20秒后',text:'进阶：弯臂悬挂 → 离心引体 → 引体向上'},{when:'第5周',text:'俯卧撑→标准15次，仰卧起坐→20次'},{when:'每4周',text:'力量动作次数+2次，椭圆时间+5分钟'}]
export const WD_SCORE:[number,number,string,string?][]=[[0,3,'作息'],[2,7,'工作'],[3,2,'拉伸'],[4,8,'工作'],[6,8,'工作'],[7,2,'拉伸'],[8,7,'工作']]
export const SAT_SCORE:[number,number,string,string?][]=[[0,10,'作息'],[1,5,'饮食'],[2,0,'-'],[3,20,'饮食'],[4,35,'活动'],[5,20,'饮食'],[6,10,'守时','22:30']]
export const SUN_SCORE:[number,number,string,string?][]=[[0,10,'作息'],[1,5,'饮食'],[2,0,'-'],[3,15,'饮食'],[4,30,'活动'],[5,15,'饮食'],[6,10,'守时','22:30'],[7,15,'作息']]
export const CAT_ORDER=['运动','学习','饮食','拉伸','作息','守时','活动']

export const V1_WDAY_SCHED:ScheduleItem[]=[
  {time:'7:30',item:'⚖️ 起床后空腹称体重、体脂并记录',note:'每天记，看2–3周趋势，不纠结单天涨跌',accent:'sleep'},
  {time:'9:00–10:30',item:'📖 工作 第1节',note:'1.5小时',accent:'study'},
  {time:'10:30–10:40',item:'🧘 颈肩拉伸 + 快走',note:'颈部慢转8圈+肩绕环前后各10次，然后快走5分钟，剩余时间上厕所休息',accent:'stretch'},
  {time:'10:50–12:20',item:'📖 工作 第2节',note:'1.5小时',accent:'study'},
  {time:'13:40–15:10',item:'📖 工作 第3节',note:'1.5小时',accent:'study'},
  {time:'15:10–15:20',item:'🦵 靠墙深蹲 + 压腿拉伸',note:'靠墙深蹲3×30秒，然后压腿每侧30秒×2，剩余时间上厕所休息',accent:'stretch'},
  {time:'15:30–17:00',item:'📖 工作 第4节',note:'1.5小时',accent:'study'},
]
export const V1_REST_SCHED:ScheduleItem[]=[
  {time:'起床后',item:'⚖️ 空腹称体重、体脂并记录',note:'每天记，看趋势',accent:'sleep'},
  {time:'上午',item:'自由安排',note:'',accent:'default'},
  {time:'下午',item:'🚶 带娃户外活动30分钟+',note:'散步、骑车、玩耍都行',accent:'study'},
]
export const V1_EXERCISE_PLAN:Record<Exclude<PlanDay,'六'|'日'>,ExerciseDay>={
  ...EXERCISE_PLAN,
  周二:{...EXERCISE_PLAN.周二,gym:[E('深蹲训练器','3×15次','最后2–3次大腿明显酸','无氧'),E('保加利亚分腿蹲','3×每侧12次','后脚搭长凳，前脚踏出一步下蹲，后膝接近地面；最后2–3次明显费力；蹬腿训练器有空时可替换','无氧'),E('膝关节绕环放松','1×2分钟','双手扶膝缓慢绕圈，每个方向15秒+前后摆腿放松，无需器械','无氧'),H,E('太空漫步机','1×10分钟','心跳95–108，低强度，帮腿排乳酸','有氧'),E('椭圆漫步机（放松）','1×10分钟','频率55–65，低强度，帮腿排乳酸','有氧'),E('爬楼梯（减半）','1次 12层','腿天后减半，腿太累可跳过','回家后',{stairs:1}),E('仰卧举腿','3×10次','下腹明显发力，不借助摆腿惯性','回家后',{core:1,floor:1}),E('仰卧起坐','3×15次','起身时呼气，腹部收紧发力','回家后',{core:1,floor:1})]},
}
export const V1_WD_SCORE:ScoreRule[]=[[0,3,'作息'],[1,7,'工作'],[2,2,'拉伸'],[3,8,'工作'],[4,8,'工作'],[5,2,'拉伸'],[6,7,'工作']]
export const V1_SAT_SCORE:ScoreRule[]=[[0,10,'作息'],[1,0,'-'],[2,90,'活动']]
export const V1_SUN_SCORE:ScoreRule[]=[[0,10,'作息'],[1,0,'-'],[2,75,'活动'],[3,15,'作息']]
export const V1_CAT_ORDER=['运动','工作','拉伸','作息','守时','活动']
export const V2_WD_SCORE:ScoreRule[]=[[0,5,'检验'],[1,10,'工作'],[1,1.25,'守时','10:30'],[2,5,'拉伸'],[3,10,'工作'],[3,1.25,'守时','12:20'],[4,10,'工作'],[4,1.25,'守时','15:10'],[5,5,'拉伸'],[6,10,'工作'],[6,1.25,'守时','17:00']]
export const V2_CAT_ORDER=['运动','工作','拉伸','检验','守时','活动']

export const EXERCISE_PLAN_DEFINITIONS:Record<string,ExercisePlanDefinition>={
  v0:{version:'v0',title:EXERCISE_PLAN_TITLE,sourceName:'每日打卡表.html',diet:DIET_RULES,weekdaySchedule:WDAY_SCHED,restSchedule:REST_SCHED,sundayExtra:SUN_EXTRA,exercisePlan:EXERCISE_PLAN,progress:PROGRESS,weekdayScore:WD_SCORE,saturdayScore:SAT_SCORE,sundayScore:SUN_SCORE,categoryOrder:CAT_ORDER,exercisePoints:63},
  v1:{version:'v1',title:EXERCISE_PLAN_TITLE,sourceName:'每日打卡表v1.html',diet:DIET_RULES,weekdaySchedule:V1_WDAY_SCHED,restSchedule:V1_REST_SCHED,sundayExtra:SUN_EXTRA,exercisePlan:V1_EXERCISE_PLAN,progress:PROGRESS,weekdayScore:V1_WD_SCORE,saturdayScore:V1_SAT_SCORE,sundayScore:V1_SUN_SCORE,categoryOrder:V1_CAT_ORDER,exercisePoints:63},
  v2:{version:'v2',title:EXERCISE_PLAN_TITLE,sourceName:'每日打卡表v2',diet:DIET_RULES,weekdaySchedule:V1_WDAY_SCHED,restSchedule:V1_REST_SCHED,sundayExtra:SUN_EXTRA,exercisePlan:V1_EXERCISE_PLAN,progress:PROGRESS,weekdayScore:V2_WD_SCORE,saturdayScore:V1_SAT_SCORE,sundayScore:V1_SUN_SCORE,categoryOrder:V2_CAT_ORDER,exercisePoints:40},
}

export function getExercisePlanDefinition(version:string):ExercisePlanDefinition{
  return EXERCISE_PLAN_DEFINITIONS[version] || EXERCISE_PLAN_DEFINITIONS.v0
}
