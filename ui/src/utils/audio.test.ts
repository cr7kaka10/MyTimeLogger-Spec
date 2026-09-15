import {
  AUDIO_SETTING_DEFAULTS,
  audioConfigFromSettings,
  normalizeAudioSettingValue,
  playAudioCue,
  syncAudioConfig,
} from './audio'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const saved = {
  audio_start: 'victory',
  audio_microBreak: 'end_long_break',
  audio_endMicroBreak: 'start_study',
  audio_startLongBreak: 'end_short_break',
  audio_end: 'start_long_break',
  audio_coin: 'none',
}
const normalized = audioConfigFromSettings(saved)
assert(normalized.start === saved.audio_start, 'valid start key must survive normalization')
assert(normalized.microBreak === saved.audio_microBreak, 'valid micro-break key must survive normalization')
assert(normalized.endMicroBreak === saved.audio_endMicroBreak, 'valid end-micro key must survive normalization')
assert(normalized.startLongBreak === saved.audio_startLongBreak, 'valid long-break key must survive normalization')
assert(normalized.endLongBreak === saved.audio_end, 'valid end key must survive normalization')
assert(normalized.victory === 'none', 'none must survive normalization')
for (const key of Object.keys(AUDIO_SETTING_DEFAULTS) as (keyof typeof AUDIO_SETTING_DEFAULTS)[]) {
  assert(normalizeAudioSettingValue(key, undefined) === AUDIO_SETTING_DEFAULTS[key], `${key} missing fallback`)
  assert(normalizeAudioSettingValue(key, 'invalid-file') === AUDIO_SETTING_DEFAULTS[key], `${key} invalid fallback`)
}
let audioObjects = 0
;(globalThis as any).Audio = class { constructor() { audioObjects += 1 } }
syncAudioConfig({ start: 'none' })
playAudioCue('start')
assert(audioObjects === 0, 'none must not create an Audio object')
console.log('audio normalization tests passed')
