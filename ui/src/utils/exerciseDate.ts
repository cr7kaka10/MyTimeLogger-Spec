import type { PlanDay } from '@models/ExercisePlanSampleDataInitializer'
const Z='Asia/Shanghai', MAP:Record<number,PlanDay>={1:'周一',2:'周二',3:'周三',4:'周四',5:'周五',6:'六',0:'日'}
const parts=(d=new Date())=>Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:Z,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23',weekday:'short'}).formatToParts(d).map(x=>[x.type,x.value]))
export const todayTab=(d=new Date())=>MAP[{Sun:0,Mon:1,Tue:2,Wed:3,Thu:4,Fri:5,Sat:6}[parts(d).weekday] ?? 1]
export const planDayForDate=(value:string)=>todayTab(new Date(`${value}T12:00:00+08:00`))
export const dateForTab=(tab:PlanDay,d=new Date())=>{const p=parts(d), base=new Date(`${p.year}-${p.month}-${p.day}T12:00:00+08:00`),dow={周一:1,周二:2,周三:3,周四:4,周五:5,六:6,日:0}[todayTab(d)],fromMon=dow===0?6:dow-1,off={周一:0,周二:1,周三:2,周四:3,周五:4,六:5,日:6}[tab];base.setUTCDate(base.getUTCDate()-fromMon+off);return new Intl.DateTimeFormat('en-CA',{timeZone:Z,year:'numeric',month:'2-digit',day:'2-digit'}).format(base)}
export const beijingTime=(d=new Date())=>{const p=parts(d);return `${p.hour}:${p.minute}`}
export const beijingDateHour=(d=new Date())=>{const p=parts(d);return {date:`${p.year}-${p.month}-${p.day}`,hour:Number(p.hour)}}
export const weekOfYear=(value:Date|string=new Date())=>{const d=typeof value==='string'?new Date(`${value}T12:00:00+08:00`):value,p=parts(d),year=Number(p.year),month=Number(p.month),day=Number(p.day),start=Date.UTC(year,0,1),current=Date.UTC(year,month-1,day),mondayOffset=(new Date(start).getUTCDay()+6)%7;return Math.floor((Math.floor((current-start)/86400000)+mondayOffset)/7)+1}

