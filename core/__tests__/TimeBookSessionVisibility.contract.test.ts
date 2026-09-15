import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const timeBookSource = readFileSync(new URL('../../ui/src/hooks/useTimeBook.ts', import.meta.url), 'utf8')
const dbSource = readFileSync(new URL('../../ui/src/db.ts', import.meta.url), 'utf8')

describe('TimeBook session visibility contract', () => {
  it('uses the dedicated local-first session pull on TimeBook entry', () => {
    const entryEffect = timeBookSource.slice(
      timeBookSource.indexOf("useEffect(() => {\n    if (!isActive) return"),
      timeBookSource.indexOf('\n  const saveDiary', timeBookSource.indexOf("useEffect(() => {\n    if (!isActive) return")),
    )

    expect(entryEffect).toContain('runLocalFirstRefresh(loadLocal')
    expect(entryEffect).toContain('pullTimeBookSessionVisibility()')
    expect(entryEffect).not.toContain("syncNow({ reason: 'timebook_enter' })")
  })

  it('keeps the dedicated pull free of push, timer reads, and third-party refreshes', () => {
    const start = dbSource.indexOf('export async function pullTimeBookSessionVisibility')
    const end = dbSource.indexOf('\n/** 仅推送 Outbox', start)
    const sessionPull = dbSource.slice(start, end)

    expect(sessionPull).toContain('_syncWorker.pullSessionVisibility')
    expect(sessionPull).not.toContain('flushNow')
    expect(sessionPull).not.toContain('refreshCurrentTimerState')
    expect(sessionPull).not.toContain('refreshTickTick')
  })
})
