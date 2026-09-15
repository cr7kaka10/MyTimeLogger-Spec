export type VersionChange = { server_version?: number; table_name?: string; record_id?: unknown }
export type FailureIdentity = { table: string; recordId: string }

const clientTable = (table: string) => table.startsWith('server_') ? table.slice(7) : table
const identity = (table: string, recordId: unknown) => `${clientTable(table)}:${String(recordId ?? '')}`

export function contiguousSuccessVersion(previous: number, changes: VersionChange[], failures: FailureIdentity[]): number {
  const blocked = new Set(failures.map(failure => identity(failure.table, failure.recordId)))
  let cursor = previous; let matchedFailure = blocked.size === 0
  for (const change of [...changes].sort((a, b) => Number(a.server_version) - Number(b.server_version))) {
    if (blocked.has(identity(String(change.table_name || ''), change.record_id))) { matchedFailure = true; break }
    if (typeof change.server_version === 'number') cursor = change.server_version
  }
  return matchedFailure ? cursor : previous
}

export function pullCursorDecision(
  previous: number | null | undefined,
  toVersion: unknown,
  options: { versioned: boolean; snapshot: boolean; succeeded: boolean },
): { previous: number | null | undefined; next: number | null | undefined; advanced: boolean } {
  const target = typeof toVersion === 'number' && Number.isFinite(toVersion) ? toVersion : null
  const accepted = options.versioned && options.succeeded && target !== null
  const next = accepted ? target : previous
  return { previous, next, advanced: accepted && typeof previous === 'number' && target! > previous }
}

export class SyncFailureGate {
  private failure: { fingerprint: string; version: number; attempts: number; retryAt: number } | null = null

  canAttempt(fingerprint: string, version: number, now = Date.now()): { allowed: boolean; retryAt?: number } {
    if (!this.failure || this.failure.fingerprint !== fingerprint || this.failure.version !== version) {
      this.failure = null; return { allowed: true }
    }
    return this.failure.retryAt <= now ? { allowed: true } : { allowed: false, retryAt: this.failure.retryAt }
  }

  fail(fingerprint: string, version: number, now = Date.now()): number {
    const attempts = this.failure?.fingerprint === fingerprint && this.failure.version === version ? this.failure.attempts + 1 : 1
    const retryAt = now + Math.min(60_000 * (2 ** (attempts - 1)), 15 * 60_000)
    this.failure = { fingerprint, version, attempts, retryAt }; return retryAt
  }

  succeed(): void { this.failure = null }
}
