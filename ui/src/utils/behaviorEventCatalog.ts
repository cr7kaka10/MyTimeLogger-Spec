export const BEHAVIOR_EVENT_FIELDS = {
  'navigation.tab_opened': ['tab'], 'navigation.back': ['tab', 'surface'],
  'control.activated': ['surface', 'control', 'tab'], 'input.changed': ['surface', 'control', 'tab'],
  'auth.signed_in': [], 'auth.signed_out': [],
  'api.request_result': ['method', 'path', 'status', 'result', 'error_code'],
  'checklist.sync.completed': ['scope', 'task_stage', 'habit_sync', 'task_count', 'duration_ms', 'result', 'error_code'],
  'habit.provider_retirement.completed': ['boundary_version', 'candidate_count', 'retired_count', 'skipped_count', 'result', 'error_code'],
  'local_habit.mutation.completed': ['operation', 'has_reward_config', 'result', 'error_code'],
  'timer.focus_handoff.completed': ['from_group', 'to_group', 'same_group', 'state', 'revision', 'result', 'error_code'],
  'notification.schedule': ['notification_type', 'permission_state', 'reason', 'result', 'error_code'],
  'notification.cancel': ['notification_type', 'reason', 'result'],
  'notification.open': ['notification_type', 'result'],
  'sleep.automation.result': ['stage', 'result', 'reason', 'huaweiVersion', 'selectorType', 'attempt', 'durationMs'],
  'audit.outbox_trimmed': ['removed_count'],
} as const

export type BehaviorAction = keyof typeof BEHAVIOR_EVENT_FIELDS
export const isBehaviorAction = (value: string): value is BehaviorAction => value in BEHAVIOR_EVENT_FIELDS
