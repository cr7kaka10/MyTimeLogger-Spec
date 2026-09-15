import { hasSleepSourceEvidence } from './sleepSourceStatus'

if (hasSleepSourceEvidence({ date: '2026-09-14', source: 'screenshot_ocr', sync_status: 'success', morning_diary: '晨记' })) {
  throw new Error('a synced diary-only row must not claim a screenshot upload')
}
if (!hasSleepSourceEvidence({ date: '2026-09-14', source: 'screenshot_ocr', sleep_score: 0 })) {
  throw new Error('OCR metrics, including zero, must identify a sleep source')
}
if (!hasSleepSourceEvidence({ date: '2026-09-14', source: 'huawei_official' })) {
  throw new Error('an explicit external sleep source must remain visible')
}

console.log('sleep source status contracts passed')
