import type { SleepData } from '../types'

/** 日记单独保存也会创建睡眠日期行；默认 source 不能证明已上传截图。 */
export const hasSleepSourceEvidence = (data?: SleepData | null): boolean => Boolean(data && (
  data.source && data.source !== 'screenshot_ocr'
  || [data.sleep_score, data.total_sleep_min, data.deep_sleep_min, data.sleep_cycles,
    data.awake_min, data.awake_count].some(value => value !== null && value !== undefined)
  || Boolean(data.sleep_start || data.sleep_end || data.analysis_report?.trim() || data.analysis_html?.trim())
))
