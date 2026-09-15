// ui/src/utils/audio.ts

export type AudioCue =
  | 'coin'
  | 'start'
  | 'end'
  | 'break'
  | 'pause'
  | 'finish'
  | 'victory'
  | 'microBreak'
  | 'endMicroBreak'
  | 'startLongBreak'
  | 'endLongBreak'

// 静态 import 让 Vite 在构建时正确处理资源路径，
// Electron file:// 协议、浏览器 http://、Android WebView 都能正常工作
import startStudySrc from '../../../assets/audio/start_study.mp3'
import startShortBreakSrc from '../../../assets/audio/start_short_break.mp3'
import endShortBreakSrc from '../../../assets/audio/end_short_break.mp3'
import startLongBreakSrc from '../../../assets/audio/start_long_break.mp3'
import endLongBreakSrc from '../../../assets/audio/end_long_break.mp3'
import victorySrc from '../../../assets/audio/victory.mp3'

export const AVAILABLE_AUDIO_FILES: Record<string, string> = {
  'start_study': startStudySrc,
  'start_short_break': startShortBreakSrc,
  'end_short_break': endShortBreakSrc,
  'start_long_break': startLongBreakSrc,
  'end_long_break': endLongBreakSrc,
  'victory': victorySrc,
}

const DEFAULT_AUDIO_FILES: Record<AudioCue, string> = {
  start: 'start_study',
  microBreak: 'start_short_break',
  endMicroBreak: 'end_short_break',
  pause: 'start_short_break',
  break: 'start_short_break',
  startLongBreak: 'start_long_break',
  endLongBreak: 'end_long_break',
  victory: 'victory',
  coin: 'victory',
  finish: 'end_long_break',
  end: 'end_long_break',
}

export const AUDIO_SETTING_DEFAULTS = {
  audio_start: 'start_study',
  audio_microBreak: 'start_short_break',
  audio_endMicroBreak: 'end_short_break',
  audio_startLongBreak: 'start_long_break',
  audio_end: 'end_long_break',
  audio_coin: 'victory',
} as const
export type AudioSettingKey = keyof typeof AUDIO_SETTING_DEFAULTS

export const normalizeAudioSettingValue = (key: AudioSettingKey, value: unknown): string => {
  if (value === 'none') return 'none'
  return typeof value === 'string' && AVAILABLE_AUDIO_FILES[value]
    ? value : AUDIO_SETTING_DEFAULTS[key]
}

export const audioConfigFromSettings = (cfg: Record<string, any>): Partial<Record<AudioCue, string>> => {
  const start = normalizeAudioSettingValue('audio_start', cfg.audio_start)
  const micro = normalizeAudioSettingValue('audio_microBreak', cfg.audio_microBreak)
  const endMicro = normalizeAudioSettingValue('audio_endMicroBreak', cfg.audio_endMicroBreak)
  const startLong = normalizeAudioSettingValue('audio_startLongBreak', cfg.audio_startLongBreak)
  const end = normalizeAudioSettingValue('audio_end', cfg.audio_end)
  const coin = normalizeAudioSettingValue('audio_coin', cfg.audio_coin)
  return { start, microBreak: micro, pause: micro, break: micro, endMicroBreak: endMicro,
    startLongBreak: startLong, endLongBreak: end, end, finish: end, coin, victory: coin }
}

let audioFiles: Partial<Record<AudioCue, string>> = { ...DEFAULT_AUDIO_FILES }

export function syncAudioConfig(cfg: Partial<Record<AudioCue, string>>) {
  for (const [cue, value] of Object.entries(cfg) as [AudioCue, string | undefined][]) {
    if (value !== undefined) audioFiles[cue] = value === 'none' || AVAILABLE_AUDIO_FILES[value]
      ? value : DEFAULT_AUDIO_FILES[cue]
  }
}

function playFileCue(type: AudioCue): void {
  const srcKey = audioFiles[type]
  if (!srcKey || srcKey === 'none') {
    return
  }

  const src = AVAILABLE_AUDIO_FILES[srcKey]
  if (!src) {
    return
  }

  try {
    const audio = new Audio(src)
    audio.volume = 0.8
    void audio.play().catch((err) => {
      console.warn(`Audio cue playback failed: ${type}`, err)
    })
  } catch (err) {
    console.error('Audio cue playback failed:', err)
  }
}

export function playAudioCue(type: AudioCue) {
  playFileCue(type)
}
