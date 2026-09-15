import type { TimerMode } from './Timer'
import type { TimerState } from './LogicEngine'

export const LOGIC_SNAPSHOT_VERSION = 1 as const
export interface LogicSnapshot {
  version: typeof LOGIC_SNAPSHOT_VERSION
  capturedAtEpochMs: number
  state: TimerState
  isPaused: boolean
  category: { id: number | null; name: string; task: string }
  pause: { count: number; reasons: string[]; startedAtEpochMs: number | null }
  segments: Array<{ key: string; startEpochMs: number; endEpochMs: number | null; note: string }>
  session: { startedAtEpochMs: number | null; largeStartedAtEpochMs: number | null; durationSeconds: number; totalStudySeconds: number; currentCycleStudySeconds: number; netDurationSeconds: number }
  timing: { mode: TimerMode; elapsedMs: number; deadlineEpochMs: number | null }
}
export type LogicSnapshotValidation =
  | { ok: true; snapshot: LogicSnapshot }
  | { ok: false; reason: 'unknown-version' | 'missing-field' | 'invalid-deadline' }

export function validateLogicSnapshot(value: unknown): LogicSnapshotValidation {
  const snapshot = value as Partial<LogicSnapshot>
  if (!snapshot || typeof snapshot !== 'object' || !('version' in snapshot) || !snapshot.category || !snapshot.pause || !snapshot.segments || !snapshot.session || !snapshot.timing || !Number.isFinite(snapshot.capturedAtEpochMs) || typeof snapshot.state !== 'string' || typeof snapshot.isPaused !== 'boolean') return { ok: false, reason: 'missing-field' }
  if (snapshot.version !== LOGIC_SNAPSHOT_VERSION) return { ok: false, reason: 'unknown-version' }
  const { deadlineEpochMs } = snapshot.timing
  if (deadlineEpochMs !== null && (!Number.isFinite(deadlineEpochMs) || deadlineEpochMs <= 0)) return { ok: false, reason: 'invalid-deadline' }
  return { ok: true, snapshot: snapshot as LogicSnapshot }
}
