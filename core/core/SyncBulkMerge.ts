import { resolve, SyncAction } from './SyncResolver'

export type BulkMergeCandidate = {
  local: Record<string, any> | null
  server: Record<string, any>
  serverOwned?: boolean
  hasPendingOutbox?: boolean
}

export type BulkMergePlan = BulkMergeCandidate & { action: SyncAction }

export const planBulkMerge = (candidates: BulkMergeCandidate[]): BulkMergePlan[] =>
  candidates.map(candidate => ({
    ...candidate,
    action: candidate.serverOwned
      ? SyncAction.PULL
      : resolve(candidate.local, candidate.server, candidate.hasPendingOutbox),
  }))

export type SafeBulkOperation = { table?: string; recordId?: string; [key: string]: unknown }
export type SafeBulkFailure = { table: string; recordId: string; category: string; columns?: string[] }

const errorCategory = (error: unknown): string => {
  const nativeCategory = (error as { errorCategory?: unknown } | null)?.errorCategory
  if (typeof nativeCategory === 'string') return nativeCategory
  const message = error instanceof Error ? error.message.toLowerCase() : ''
  if (message.includes('constraint')) return 'constraint'
  if (message.includes('column') || message.includes('schema')) return 'schema'
  if (message.includes('locked') || message.includes('disk')) return 'storage'
  return 'sqlite_operation_failed'
}

export async function applyBulkWithIsolation<T extends SafeBulkOperation>(
  operations: T[], commit: (batch: T[]) => void | Promise<void>,
): Promise<{ applied: number; failures: SafeBulkFailure[] }> {
  if (operations.length === 0) return { applied: 0, failures: [] }
  try { await commit(operations); return { applied: operations.length, failures: [] } }
  catch (error) {
    if (operations.length === 1) return { applied: 0, failures: [{
      table: String(operations[0].table || 'unknown'), recordId: String(operations[0].recordId || ''), category: errorCategory(error),
    }] }
    const middle = Math.floor(operations.length / 2)
    const left = await applyBulkWithIsolation(operations.slice(0, middle), commit)
    const right = await applyBulkWithIsolation(operations.slice(middle), commit)
    return { applied: left.applied + right.applied, failures: [...left.failures, ...right.failures] }
  }
}
