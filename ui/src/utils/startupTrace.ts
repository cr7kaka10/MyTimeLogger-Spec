import { detectPlatformRuntime } from '../platform/runtime'

const startedAt = performance.now()

/** 只记录阶段与单调时钟耗时，不记录账号或业务数据。 */
export function markAndroidStartup(stage: string): void {
  if (detectPlatformRuntime() !== 'capacitor-android') return
  console.info('[android-startup]', stage, Math.round(performance.now() - startedAt), 'ms')
}
