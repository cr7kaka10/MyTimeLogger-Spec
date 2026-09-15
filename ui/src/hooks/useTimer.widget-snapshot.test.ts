import { readFileSync } from 'node:fs'

const hook = readFileSync(new URL('./useTimer.ts', import.meta.url), 'utf8')

if (!hook.includes('const importWidgetSnapshot = async (): Promise<boolean>')) throw new Error('widget snapshots must be imported through a validated path')
if (!hook.includes('const restored = await restoreTimerSnapshot(activeEngine)')) throw new Error('widget snapshot import must use the existing validator')
if (!hook.includes("window.addEventListener('mtl:timer-widget-snapshot-changed', onWidgetSnapshotChanged)")) throw new Error('running App must react immediately to native widget success')
if (!hook.includes("window.addEventListener('focus', refresh)") || !hook.includes('void importWidgetSnapshot().finally')) throw new Error('foreground recovery must import native state before the normal refresh')

console.log('timer widget snapshot recovery contract passed')
