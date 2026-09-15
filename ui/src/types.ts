// ui/src/types.ts
export type TimerState =
  | 'stopped'
  | 'studying'
  | 'countup_studying'
  | 'short_breaking'
  | 'long_breaking'
  | 'long_break_finished'

export interface Category {
  id: number
  name: string
  icon: string
  color: string
  group_name: string
  sort_order: number
}

export interface SessionRecord {
  id: number | string
  start_time: string
  end_time: string
  net_duration_minutes: number
  net_duration_seconds?: number | null
  date: string
  day_of_week: string
  pause_count: number
  pause_reasons?: string
  session_summary: string
  category_id: number | null
  category_name?: string
  category_color?: string
  category_icon?: string
}

export interface Habit {
  id: number | string
  name: string
  icon: string
  difficulty: string
  is_active: number
  sort_order: number
  repeat_rule?: string | null
  category_id?: number | null
}

export interface HabitCheckin {
  id: number | string
  habit_id: number | string
  checkin_date: string
  status: number
}

export interface Goal {
  id: number | string
  title: string
  category_id: number | null
  metric: string
  target_value: number
  period: string
  reward_coins: number
  penalty_coins: number
  operator: string
  is_active: number
  reward_id?: string | number | null
  category_ids?: number[]
}

export interface Reward {
  id: number | string
  title: string
  icon: string
  price: number
  redemption_mode?: 'coins' | 'task' | 'goal' | 'pending_binding' | 'custom_spend'
  description: string
  is_active: number
  unlock_task_id?: string | null
  unlock_task_title?: string | null
  unlock_source_type?: 'checklist_task' | 'habit' | 'learning_task' | 'learning_objective' | 'exercise_checkin' | 'goal' | null
  unlock_source_id?: string | null
  inventory_mode?: 'unlimited' | 'daily' | 'monthly'
  inventory_limit?: number | null
  unlock_required_count?: number
  fulfillment_mode?: 'immediate' | 'fragment'
  fragment_target_count?: number
  fragment_rule_version?: number
  fragment_progress_units?: number
  inventory_used?: number
}

export interface RewardFragment {
  id: string
  reward_id: string
  source_type: string
  source_id: string
  completion_event_key: string
  rule_version: number
  issued_at: string
  expires_at: string
  status: 'active' | 'consumed' | 'expired' | 'revoked'
  compose_batch_id?: string | null
}

export interface RewardSourceBinding {
  id: string
  reward_id: string
  source_type: SourceRewardType
  source_id: string
  created_at: string
  updated_at: string
}

export interface FragmentProgress {
  active: number
  target: number
  activeUnits?: number
  targetUnits?: number
  percent?: number
  inventoryUsed?: number
  inventoryLimit?: number | null
  inventoryLimitReached?: boolean
  earliestExpiresAt?: string | null
}

export type SourceRewardType = 'checklist_task' | 'habit' | 'learning_task' | 'learning_objective'

export interface SourceRewardSummaryData {
  sourceType: SourceRewardType
  sourceId: string
  coins: number
  penalty: number
  itemReward: Reward | null
  itemRewards?: Reward[]
  fragmentProgress?: Record<string, FragmentProgress>
}

export interface SleepData {
  date: string
  sleep_score?: number
  total_sleep_min?: number
  deep_sleep_min?: number
  light_sleep_min?: number
  rem_sleep_min?: number
  sleep_start?: string
  sleep_end?: string
  analysis_report?: string
  analysis_html?: string
  official_advice?: string
  morning_diary?: string
  evening_diary?: string
  awake_count?: number
  deep_sleep_ratio?: number
  light_sleep_ratio?: number
  rem_sleep_ratio?: number
  sleep_continuity?: number
  breathing_score?: number
  sleep_cycles?: number
  awake_min?: number
  fall_asleep_min?: number
  wake_up_min?: number
  atm_sleep_start?: string
  atm_sleep_end?: string
  source?: string
  synced_at?: string
  sync_status?: string
  sync_error?: string
  report_status?: number
  full_report_state?: 'generated' | 'insufficient_time_records' | 'no_main_sleep'
  tracked_duration_seconds?: number
  score_settlement?: SleepScoreSettlement
}

export interface SleepScoreSettlement {
  sleep_date: string; score_total: number; reward_amount: number; cycle_penalty: number; net_amount: number
  settlement_status: string; missing_fields: string; score_breakdown: string; rule_version: string
  report_completed_at?: string | null; completion_reward_amount?: number; is_all_complete?: boolean | number
  deep_sleep_penalty?: number; no_sleep_penalty?: number
  completion_reason?: string | null
  morning_diary_reward_amount?: number; evening_diary_reward_amount?: number
  diary_completion_status?: string; diary_completion_reward_amount?: number; diary_completion_reason?: string | null
  bedtime_coin_status?: string | null; bedtime_coin_amount?: number; bedtime_coin_reason?: string | null
  bedtime_coin_rule_version?: string | null
}

export type SleepAutoScoreState = 'no_report' | 'scoring' | 'unavailable' | 'scored'

export interface ExerciseScoreSettlement {
  business_date: string; plan_version: string; score_total: number; coin_amount: number
  score_snapshot?: string | Record<string, unknown> | null; category_scores?: string | null
  is_all_complete?: boolean | number; completion_reward_amount?: number; completion_reason?: string | null
}

export interface SystemSettings {
  server_url: string
  auth_token: string
  study_time_min: number
  study_time_max: number
  short_break_duration: number
  long_break_duration: number
  long_break_threshold: number
  input_output_countdown_min: number
  sync_interval: number
  statistics_start_date: string
  last_sync_at: string
  // aTimeLogger 备份同步
  atimelogger_enabled?: boolean
  atimelogger_username?: string
  atimelogger_password?: string
  atimelogger_owner_username?: string
  atimelogger_token?: string
  atimelogger_refresh_token?: string
  atimelogger_device_id?: string
  atimelogger_auth_required?: boolean
  atimelogger_type_map?: string
  atimelogger_unmatched_categories?: string
  // 睡眠同步
  sleep_sync_enabled?: boolean
  sleep_sync_interval?: number
  // AI 模型
  ai_text_model?: string
  ai_text_api_key?: string
  ai_text_endpoint?: string
  ai_vision_model?: string
  ai_vision_api_key?: string
  ai_vision_endpoint?: string
  // 快捷键
  shortcut_toggle_timer?: string
  shortcut_minimize?: string
  shortcut_toggle_todo?: string
  // 音频设置
  audio_start?: string
  audio_end?: string
  audio_microBreak?: string
  audio_endMicroBreak?: string
  audio_startLongBreak?: string
  audio_coin?: string
  // 高级
  music_folder?: string
  // 流水格式配置
  ledger_format_habit_success?: string
  ledger_format_habit_makeup?: string
  ledger_format_habit_fail?: string
  ledger_format_task_success?: string
  ledger_format_task_fail?: string
}

// ======================== 背包 ========================

export interface BackpackItem {
  id: number | string
  icon: string
  title: string
  created_at: string
  memo?: string
  description?: string
  source_label?: string
  unlock_task_title?: string
  is_used: boolean
  used_at?: string | null
}

export interface BackpackFragment {
  id: string
  reward_id: string
  title: string
  icon: string
  description?: string
  current_count: number
  target_count: number
  earliest_expires_at: string
  rule_version: number
  progress_percent?: number
  inventory_used?: number
  inventory_limit?: number | null
  inventory_limit_reached?: boolean
}

export interface BackpackEvent {
  id: string
  ledger_id: string
  event_type: 'acquired' | 'used' | 'discarded' | 'revoked' | 'fragment_acquired' | 'fragment_expired' | 'fragment_revoked' | 'fragment_composed'
  created_at: string
  item_title: string
  quantity: number
  detail?: string | null
}

// ======================== 清单 / TickTick ========================

export interface TaskItem {
  id: string
  title: string
  priority: number          // 0=无, 1=低, 3=中, 5=高
  status: number            // 0=活跃, 2=已完成
  tags: string[]
  due_date: string
  due_date_full: string
  is_overdue: boolean
  reward_coins?: number
  penalty_coins?: number
  project_id?: string
  start_date?: string | null
  provider_due_date?: string | null
  time_zone?: string
  is_all_day?: boolean
  repeat_flag?: string
}

export interface TickTickHabit {
  id: string                // TickTick habit ID
  name: string
  status: number            // 0=正常, 1=归档
  sortOrder: number
  goal?: number
  unit?: string
}

export interface TickTickCheckin {
  habitId: string
  stamp: string             // YYYYMMDD
  status: number            // 0=完成, 2=未完成
  value: number
}

// ======================== 金币 ========================

export interface ExternalReward {
  id: string                // "habit_{habitId}_{stamp}" 或 "task_{taskId}"
  item_type: string
  item_name: string
  coins: number
  status: number            // 0=待领取, 1=已领取
}

export interface LedgerEntry {
  id: number | string
  amount: number
  source_type: string
  source_id?: number | string
  description?: string
  target_date?: string
  occurred_at?: string | null
  created_at?: string
  display_title?: string
}

export type LedgerFilter = 'all' | 'income' | 'expense' | 'reward'

// ======================== 时间书编辑 ========================

export interface SessionEditData {
  id?: number | string
  start_time: string
  end_time: string
  net_duration_minutes: number
  net_duration_seconds?: number
  date: string
  category_id: number | null
  session_summary: string
}

// ======================== 目标编辑 ========================

export interface GoalFormData {
  id?: number | string
  title: string
  category_id: number | null
  category_ids: number[]
  metric: 'duration' | 'count'
  target_value: number
  period: 'daily' | 'weekly' | 'monthly' | 'per_session'
  operator: '>=' | '<='
  reward_coins: number
  penalty_coins: number
}

// ======================== 分类编辑 ========================

export interface CategoryFormData {
  id?: number
  name: string
  icon: string
  color: string
  group_name: string
  sort_order?: number
}

// ======================== 习惯编辑 ========================

export interface HabitFormData {
  id?: number | string
  title: string
  icon: string
  difficulty: 'trivial' | 'easy' | 'medium' | 'hard'
}

// ======================== 枚举类型 ========================

export type HabitSection = 'habits' | 'goals' | 'rewards'
// 注意：'habits' tab 已移除，统一使用 'checklist' tab
export type MainTab = 'timer' | 'timebook' | 'goals' | 'checklist' | 'sleep' | 'settings' | 'rewards' | 'backpack' | 'exercise' | 'learning'
