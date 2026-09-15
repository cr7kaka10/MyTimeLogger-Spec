import { describe, expect, it } from 'vitest'
import {
  resolveLongBreakMinutes,
  resolveLongBreakSeconds,
  resolveInputOutputCountdownMinutes,
  resolveInputOutputCountdownSeconds,
  resolveStudyReminderRangeSeconds,
} from '../core/TimerSettings'

describe('TimerSettings', () => {
  it('输入/输出倒计时缺省为 90 分钟', () => {
    expect(resolveInputOutputCountdownMinutes(undefined)).toBe(90)
    expect(resolveInputOutputCountdownSeconds(undefined)).toBe(5400)
  })

  it('输入/输出倒计时支持 2 分钟测试档', () => {
    expect(resolveInputOutputCountdownMinutes(120)).toBe(2)
    expect(resolveInputOutputCountdownSeconds(120)).toBe(120)
    expect(resolveInputOutputCountdownMinutes(2)).toBe(2)
  })

  it('输入/输出旧 3 分钟测试档归一为 2 分钟', () => {
    expect(resolveInputOutputCountdownMinutes(180)).toBe(2)
    expect(resolveInputOutputCountdownSeconds(180)).toBe(120)
    expect(resolveInputOutputCountdownMinutes(3)).toBe(2)
  })

  it('输入/输出倒计时非法值回落 90 分钟', () => {
    expect(resolveInputOutputCountdownMinutes(240)).toBe(90)
    expect(resolveInputOutputCountdownSeconds('not-a-number')).toBe(5400)
  })

  it('长休息时长支持 1/5/10/20 分钟且默认 20 分钟', () => {
    expect(resolveLongBreakMinutes(undefined)).toBe(20)
    expect(resolveLongBreakSeconds(undefined)).toBe(1200)
    expect(resolveLongBreakSeconds(60)).toBe(60)
    expect(resolveLongBreakSeconds(300)).toBe(300)
    expect(resolveLongBreakSeconds(600)).toBe(600)
    expect(resolveLongBreakSeconds(1200)).toBe(1200)
    expect(resolveLongBreakMinutes(5)).toBe(5)
  })

  it('长休息非法值回落 20 分钟', () => {
    expect(resolveLongBreakMinutes(1800)).toBe(20)
    expect(resolveLongBreakSeconds('bad')).toBe(1200)
  })

  it('随机提醒支持 30~60 秒并归一旧 0~60 秒测试档', () => {
    expect(resolveStudyReminderRangeSeconds(30, 60)).toEqual({ min: 30, max: 60 })
    expect(resolveStudyReminderRangeSeconds(0, 60)).toEqual({ min: 30, max: 60 })
  })

  it('随机提醒非法范围回落 5~7 分钟', () => {
    expect(resolveStudyReminderRangeSeconds('bad', 60)).toEqual({ min: 300, max: 420 })
    expect(resolveStudyReminderRangeSeconds(90, 30)).toEqual({ min: 300, max: 420 })
  })
})
