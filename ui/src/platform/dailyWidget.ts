import { getCurrentTimerClient, getDatabase, syncChecklistNow, syncNow } from '../db'
import { projectHabits, shanghaiDay } from './dailyWidgetProjection'

type Command = { kind: 'habit' | 'task'; action?: 'complete' | 'fail'; id: string; date: string; commandId: string; userId?: string }
export type DailyWidgetHabitJournalIntent = { commandId: string; habitId: string; date: string; userId: string }
type Host = Window & { MTLDailyWidget?: { ready(): void; pause(): void; publish(value: string): boolean; refresh(): void; ack(id: string, result: string): void } }
const host = () => window as Host
const inFlight = new Set<string>()
const journalIntents: DailyWidgetHabitJournalIntent[] = []
const awaitingSync = new Map<string, Command>()
const seenJournals = new Set<string>()
export const pendingDailyWidgetHabitJournals = () => [...journalIntents]
export function dismissDailyWidgetHabitJournal(commandId: string) {
  const index = journalIntents.findIndex(item => item.commandId === commandId)
  if (index >= 0) journalIntents.splice(index, 1)
}
function offerHabitJournal(command: Command) {
  if (!command.userId || seenJournals.has(command.commandId) || command.date !== shanghaiDay()) return
  seenJournals.add(command.commandId)
  journalIntents.push({ commandId: command.commandId, habitId: command.id, date: command.date, userId: command.userId })
  window.dispatchEvent(new Event('mtl:daily-widget-habit-journal'))
}
async function resolveAwaitingJournals() {
  if (!awaitingSync.size) return
  const db = await getDatabase()
  for (const [id, command] of awaitingSync) {
    if (command.date !== shanghaiDay()) { awaitingSync.delete(id); continue }
    const checkins = db.getTodayCheckins(command.date) as Array<{ habit_id: string | number; status: number }>
    if (checkins.some(row => String(row.habit_id) === command.id && Number(row.status) === 2)) {
      awaitingSync.delete(id); offerHabitJournal(command)
    }
  }
}
export async function publishDailyWidget(isCurrent = () => true) {
  if (!host().MTLDailyWidget) return
  const db = await getDatabase()
  if (!isCurrent()) return
  const habits = db.getHabits() as Array<{ id: string | number; repeat_rule?: string | null }>
  host().MTLDailyWidget?.publish(JSON.stringify({ version: 1, days: projectHabits(habits, shanghaiDay()) }))
}

export async function applyDailyWidgetCommand(command: Command): Promise<'applied' | 'pending_sync' | 'failed'> {
  const action = command.action ?? 'complete'
  if (!['habit', 'task'].includes(command.kind) || !['complete', 'fail'].includes(action)
    || (command.kind === 'task' && action !== 'complete') || !command.id || command.date !== shanghaiDay()) return 'failed'
  const db = await getDatabase()
  if (command.kind === 'habit') {
    const client = getCurrentTimerClient()
    if (!client) return 'failed'
    const checkins = db.getTodayCheckins(command.date) as Array<{ habit_id: string | number; status: number }>
    const desired = action === 'fail' ? 1 : 2
    const current = checkins.find(row => String(row.habit_id) === command.id)
    if (Number(current?.status) === desired) return 'applied'
    if (Number(current?.status) === 2 && action === 'fail') return 'failed'
    const response = await client.commandHabitCheckin({ habit_id: command.id, date: command.date, desired_status: desired, idempotency_key: command.commandId })
    if (!response.ok || response.data?.status !== 'confirmed') return 'failed'
    const synced = await syncNow({ reason: 'daily-widget-habit' }).then(result => result.ok).catch(() => false)
    if (desired === 2 && command.userId) {
      if (synced) offerHabitJournal(command)
      else awaitingSync.set(command.commandId, command)
    }
    return synced ? 'applied' : 'pending_sync'
  }
  const task = db.getChecklistTasks().find((row: Record<string, any>) => String(row.id) === command.id)
  if (!task) return 'failed'
  if (Number(task.status) === 2) return 'applied'
  if (Number(task.status) !== 0) return 'failed'
  const reward = db.getItemReward('task', command.id, 0.1)
  db.completeTask(command.id, String(task.title), reward.reward)
  window.dispatchEvent(new Event('mtl:daily-widget-task-complete'))
  window.dispatchEvent(new Event('balance-updated'))
  try { return (await syncChecklistNow({ reason: 'daily-widget-task' })).ok ? 'applied' : 'pending_sync' }
  catch { return 'pending_sync' }
}

export function attachDailyWidget(authenticated: boolean): () => void {
  if (!host().MTLDailyWidget || !authenticated) return () => {}
  let active = true
  const refresh = () => { void publishDailyWidget(() => active).catch(() => {}) }
  const consume = (event: Event) => {
    const value = (event as CustomEvent<Command>).detail
    if (!value || !/^[A-Za-z0-9._:-]{1,128}$/.test(value.commandId) || !/^[A-Za-z0-9._:-]{1,128}$/.test(value.id)) return
    if (inFlight.has(value.commandId)) return
    inFlight.add(value.commandId)
    void applyDailyWidgetCommand(value).catch(() => 'failed' as const).then(result => {
      inFlight.delete(value.commandId)
      host().MTLDailyWidget?.ack(value.commandId, result)
      refresh()
    })
  }
  window.addEventListener('mtl:daily-widget-command', consume)
  const onSync = () => { refresh(); void resolveAwaitingJournals().catch(() => {}) }
  window.addEventListener('sync-pull-complete', onSync)
  window.addEventListener('focus', refresh)
  window.addEventListener('local-habits-updated', refresh)
  window.addEventListener('mtl:daily-widget-runtime-changed', refresh)
  const interval = window.setInterval(refresh, 300_000)
  host().MTLDailyWidget?.ready()
  refresh()
  return () => {
    active = false
    host().MTLDailyWidget?.pause()
    window.removeEventListener('mtl:daily-widget-command', consume)
    window.removeEventListener('sync-pull-complete', onSync)
    window.removeEventListener('focus', refresh)
    window.removeEventListener('local-habits-updated', refresh)
    window.removeEventListener('mtl:daily-widget-runtime-changed', refresh)
    window.clearInterval(interval)
  }
}
