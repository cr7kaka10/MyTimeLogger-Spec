import { describe, expect, it } from 'vitest'
import { elapsedWholeSeconds, formatClockTime, formatDurationHms, formatHoursMinutes, resolveSessionDurationSeconds } from '../core/displayFormat'
import { deriveProfileConnectionStatus, environmentActivationWrites, environmentKey, migrateEnvironmentConfig, readEnvironmentProfile } from '../core/EnvironmentProfiles'
import { exerciseStatusPresentation } from '../core/ExerciseStatus'
import { runLocalFirstRefresh } from '../core/LocalFirstRefresh'
import { SerialTaskQueue } from '../core/SerialTaskQueue'
import { statusControlClass } from '../core/StatusControl'
import { recordOnlyTimeline } from '../core/RecordTimeline'
import { DEFAULT_CATEGORY_ATM_ICONS, hexToRgb, isAtmIconKey, parseAtmIconName, rgbToHex } from '../core/CategoryIconKey'

describe('客户端展示与环境档案', () => {
  it('标准分类映射是15个唯一 ATM key', () => {
    expect(Object.keys(DEFAULT_CATEGORY_ATM_ICONS)).toHaveLength(15)
    expect(new Set(Object.values(DEFAULT_CATEGORY_ATM_ICONS)).size).toBe(15)
    expect(Object.values(DEFAULT_CATEGORY_ATM_ICONS).every(key => isAtmIconKey(key))).toBe(true)
  })
  it('ATM 图标键限制为受控资源名与清单成员', () => {
    const allowed = new Set(['cat_96', 'fam_021'])
    expect(parseAtmIconName('atm:cat_96', allowed)).toBe('cat_96')
    expect(isAtmIconKey('atm:fam_021', allowed)).toBe(true)
    expect(isAtmIconKey('atm:cat_97', allowed)).toBe(false)
    expect(isAtmIconKey('atm:../cat_96', allowed)).toBe(false)
    expect(isAtmIconKey('https://example.com/icon.png', allowed)).toBe(false)
    expect(isAtmIconKey('atm:flat_001', new Set(['flat_001']))).toBe(true)
    expect(isAtmIconKey('atm:swift_colored_kitchen_001', new Set(['swift_colored_kitchen_001']))).toBe(true)
  })
  it('RGB 与 Hex 精确双向转换并拒绝非法值', () => {
    expect(rgbToHex(255, 0, 128)).toBe('#FF0080')
    expect(hexToRgb('#ff0080')).toEqual([255, 0, 128])
    expect(rgbToHex(256, 0, 0)).toBeNull()
    expect(hexToRgb('red')).toBeNull()
  })
  it('总时长只显示整数小时分钟', () => {
    expect(formatHoursMinutes(83.385)).toBe('1h 23min')
    expect(formatHoursMinutes(Number.NaN)).toBe('0h 0min')
  })

  it('时间书按秒显示并兼容历史记录', () => {
    expect(formatClockTime('2026-06-23 15:53:11')).toBe('15:53:11')
    expect(formatDurationHms(71)).toBe('00:01:11')
    expect(formatDurationHms(3661)).toBe('01:01:01')
    expect(resolveSessionDurationSeconds({ net_duration_seconds: 71, start_time: '2026-06-23 00:00:00', end_time: '2026-06-23 00:09:00' })).toBe(540)
    expect(resolveSessionDurationSeconds({ start_time: '2026-06-23 15:53:11', end_time: '2026-06-23 15:54:22', net_duration_minutes: 9 })).toBe(71)
  })

  it('环境连接状态只属于已启用且配置完整的环境', () => {
    expect(deriveProfileConnectionStatus({ serverUrl: '', authToken: '' }, false, 'connected')).toBe('unconfigured')
    expect(deriveProfileConnectionStatus({ serverUrl: 'http://server', authToken: 'token' }, false, 'connected')).toBe('inactive')
    expect(deriveProfileConnectionStatus({ serverUrl: 'http://server', authToken: 'token' }, true, 'unauthorized')).toBe('unauthorized')
    expect(deriveProfileConnectionStatus({ serverUrl: 'http://server', authToken: 'token' }, true, 'connected')).toBe('connected')
  })

  it('运动三态输出语义化标记', () => {
    expect(exerciseStatusPresentation(1)).toMatchObject({ className: 'done', mark: '✓', label: '已完成' })
    expect(exerciseStatusPresentation(-1)).toMatchObject({ className: 'skip', mark: '✗', label: '已跳过' })
    expect(exerciseStatusPresentation()).toMatchObject({ className: '', mark: '', label: '未打卡' })
  })

  it('清单与运动共享圆形状态样式', () => {
    expect(statusControlClass('success')).toContain('rounded-full')
    expect(statusControlClass('success')).toContain('bg-green-500')
    expect(statusControlClass('failure')).toContain('bg-red-500')
    expect(statusControlClass('idle')).toContain('bg-gray-100')
  })

  it('时间书本地先读且同步失败后仍重读', async () => {
    const calls: string[] = []
    const error = await runLocalFirstRefresh(async () => { calls.push('load') }, async () => {
      calls.push('sync'); throw new Error('offline')
    })
    expect(calls).toEqual(['load', 'sync', 'load'])
    expect(error).toBe('offline')
  })

  it('时间书按时间稳定倒序且不修改原数组', () => {
    const source = [
      { id: 1, start_time: '2026-06-23 08:00:00', end_time: '2026-06-23 08:10:00' },
      { id: 2, start_time: 'bad-time', end_time: 'bad-time' },
      { id: 3, start_time: '2026-06-23 09:00:00', end_time: '2026-06-23 09:10:00' },
      { id: 4, start_time: '2026-06-23 09:00:00', end_time: '2026-06-23 09:11:00' },
    ]
    expect(recordOnlyTimeline(source).map(item => item.id)).toEqual([4, 3, 1, 2])
    expect(source.map(item => item.id)).toEqual([1, 2, 3, 4])
    expect(recordOnlyTimeline(source).map(item => item.id)).toEqual([4, 3, 1, 2])
  })

  it('实时显示按完整经过秒向下取整', () => {
    expect(elapsedWholeSeconds(999)).toBe(0)
    expect(elapsedWholeSeconds(1000)).toBe(1)
    expect(elapsedWholeSeconds(71900)).toBe(71)
  })

  it('远端切换任务保持点击顺序', async () => {
    const queue = new SerialTaskQueue(), calls: string[] = []
    await Promise.all([
      queue.enqueue(async () => { calls.push('stop-family'); await Promise.resolve(); calls.push('start-food') }),
      queue.enqueue(async () => { calls.push('stop-food'); calls.push('start-car') }),
    ])
    expect(calls).toEqual(['stop-family', 'start-food', 'stop-food', 'start-car'])
  })

  it('时间书只返回真实记录且不生成空闲行', () => {
    const sessions = [{ id: 1, end: '13:47' }, { id: 2, start: '15:14' }]
    expect(recordOnlyTimeline(sessions)).toEqual([sessions[1], sessions[0]])
    expect(recordOnlyTimeline(sessions)).toHaveLength(2)
  })

  it('把旧配置只迁移到开发环境', () => {
    const writes = migrateEnvironmentConfig({ server_url: 'http://dev', auth_token: 'dev-token' })
    expect(writes.active_environment).toBe('development')
    expect(writes[environmentKey('development', 'auth_token')]).toBe('dev-token')
    expect(writes[environmentKey('testing', 'auth_token')]).toBeUndefined()
    expect(writes[environmentKey('production', 'auth_token')]).toBeUndefined()
  })

  it('分别读取三个环境且不串用凭据', () => {
    const cfg = {
      [environmentKey('testing', 'server_url')]: 'https://test',
      [environmentKey('testing', 'username')]: 'tester',
      [environmentKey('testing', 'auth_token')]: 'test-token',
      [environmentKey('production', 'auth_token')]: 'prod-token',
    }
    expect(readEnvironmentProfile(cfg, 'testing')).toEqual({ serverUrl: 'https://test', username: 'tester', authToken: 'test-token' })
    expect(readEnvironmentProfile(cfg, 'production')).toEqual({ serverUrl: '', username: '', authToken: 'prod-token' })
  })

  it('环境启用写入唯一活动环境且缺失配置不产生写入', () => {
    expect(environmentActivationWrites('testing', { serverUrl: 'https://test', authToken: 'token' }))
      .toEqual({ active_environment: 'testing' })
    expect(() => environmentActivationWrites('production', { serverUrl: '', authToken: '' })).toThrow('尚未配置')
  })
})
