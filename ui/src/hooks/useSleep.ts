// ui/src/hooks/useSleep.ts
import { useCallback, useEffect, useMemo, useState } from 'react'
import { requireActiveEnvironmentRuntimeConfig } from '@core/EnvironmentProfiles'
import type { SleepData } from '../types'
import { getDatabase, syncAfterDateSwitch, syncChangeNow, type SyncChangeResult, type SyncNowOptions } from '../db'
import { formatBeijingDate } from '@core/BeijingTime'
import { formatPlatformNetworkError, platformFetch, platformUploadMultipart } from '../platform/fetch'
import { useSyncRefresh } from './useEventRefresh'

const formatSleepApiError = (payload: any, fallback: string): string => {
  const detail = payload?.detail ?? payload
  if (detail?.error_code === 'date_mismatch') {
    const actual = detail.actual_date || '未知'
    const expected = detail.expected_date || '未知'
    return detail.message || `日期不匹配！截图日期是 ${actual}，而当前处理日期是 ${expected}。请确认是否选错了图。`
  }
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return fallback
}

const readSleepApiError = async (res: { text: () => Promise<string> }, fallback: string): Promise<string> => {
  const text = await res.text()
  if (!text) return fallback
  try {
    return formatSleepApiError(JSON.parse(text), fallback)
  } catch {
    return fallback
  }
}

const formatSleepTransportError = (error: any, fallback: string): string => {
  const message = String(error?.message || '')
  if (message === 'SLEEP_FILE_READ_FAILED') return '无法读取所选图片，请重新选择'
  if (/failed to fetch|network|load failed|timeout|timed out|abort|cleartext|ECONN/i.test(message)) return formatPlatformNetworkError(error)
  return message || fallback
}

export interface UseSleepReturn {
  sleepData: SleepData | null
  sleepHistory: SleepData[]
  selectedDate: string
  setSelectedDate: (d: string) => void
  saveDiary: (type: 'morning' | 'evening', text: string) => Promise<void>
  pickImage: (file: File) => Promise<void>
  runAnalysis: () => void
  runFullAnalysis: () => void
  forceRefresh: () => void
  isAnalyzing: boolean
  statusMessage: string
  uploadMessage: string
}

export const saveSleepDiaryAndSync = async (
  db: any,
  date: string,
  type: 'morning' | 'evening',
  text: string,
  requestSync: (changeId: string, options: SyncNowOptions) => Promise<SyncChangeResult> = syncChangeNow,
): Promise<{ state: 'confirmed' | 'delivered' | 'pending' | 'rejected'; reason?: string; changeId: string }> => {
  const { changeId } = db.saveSleepDiary(date, type, text)
  try {
    const result = await requestSync(changeId, {
      reason: `sleep-${type}-diary-save`,
      ledgerExpectation: {
        sourceType: `sleep_${type}_diary_reward`,
        targetDate: date,
        exists: Boolean(text.trim()),
      },
    })
    if (result.delivery === 'rejected') return { state: 'rejected', reason: result.reason, changeId }
    if (result.delivery === 'accepted' || result.delivery === 'duplicate') {
      return { state: result.ledgerConfirmed ? 'confirmed' : 'delivered', changeId }
    }
    return { state: 'pending', reason: result.reason, changeId }
  } catch {
    return { state: 'pending', changeId }
  }
}

export const isDiaryRewardLocallyConfirmed = (
  db: any, date: string, type: 'morning' | 'evening', exists: boolean, changeId: string,
): boolean => {
  const delivery = db.allRaw('SELECT status FROM sync_outbox WHERE change_id=? LIMIT 1', [changeId])[0]
  if (delivery?.status !== 'synced') return false
  const reward = db.allRaw('SELECT id FROM reward_ledger WHERE source_type=? AND target_date=? LIMIT 1',
    [`sleep_${type}_diary_reward`, date])[0]
  const settlement = db.allRaw('SELECT * FROM sleep_score_settlements WHERE sleep_date=? ORDER BY updated_at DESC LIMIT 1', [date])[0]
  const rewardStatus = settlement?.[`${type}_diary_reward_status`]
  return Boolean(reward) === exists && rewardStatus === (exists ? 'completed' : 'pending')
}

export const useSleep = (): UseSleepReturn => {
  const [selectedDate, setSelectedDate] = useState(() => formatBeijingDate())
  const [sleepData, setSleepData] = useState<SleepData | null>(null)
  const [sleepHistory, setSleepHistory] = useState<SleepData[]>([])
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [uploadMessage, setUploadMessage] = useState('')
  const [pendingDiary, setPendingDiary] = useState<{
    date: string; type: 'morning' | 'evening'; exists: boolean; changeId: string
  } | null>(null)
  const syncRefresh = useSyncRefresh()

  useEffect(() => {
    if (!pendingDiary || pendingDiary.date !== selectedDate) return
    let current = true
    getDatabase().then(db => {
      if (!current || !isDiaryRewardLocallyConfirmed(db, pendingDiary.date, pendingDiary.type, pendingDiary.exists, pendingDiary.changeId)) return
      setStatusMessage(`${pendingDiary.type === 'morning' ? '晨间' : '晚间'}日记已同步，奖励状态已刷新`)
      setPendingDiary(null)
    }).catch(error => console.warn('[useSleep] diary reward confirmation read failed:', error))
    return () => { current = false }
  }, [pendingDiary, selectedDate, syncRefresh])

  useEffect(() => {
    let current = true
    setUploadMessage('')
    getDatabase().then(db => {
      if (!current) return
      const data = db.getSleepData(selectedDate)
      const settlement = db.allRaw('SELECT * FROM sleep_score_settlements WHERE sleep_date=? ORDER BY updated_at DESC LIMIT 1', [selectedDate])[0]
      setSleepData(data ? { ...data, score_settlement: settlement } : settlement ? { date: selectedDate, score_settlement: settlement } : null)
      setSleepHistory(db.getSleepHistory() ?? [])
    }).catch(error => console.warn('[useSleep] local sleep read failed:', error))
    return () => { current = false }
  }, [selectedDate, refreshTrigger, syncRefresh])

  const saveDiary = useCallback(async (type: 'morning' | 'evening', text: string) => {
    const db = await getDatabase()
    setStatusMessage(text.trim() ? '日记已本地保存，正在同步奖励状态...' : '日记已保存')
    const result = await saveSleepDiaryAndSync(db, selectedDate, type, text)
    setRefreshTrigger(prev => prev + 1)
    if (result.state === 'confirmed') {
      setPendingDiary(null)
      setStatusMessage(`${type === 'morning' ? '晨间' : '晚间'}日记已同步，奖励状态已刷新`)
    } else if (result.state === 'delivered') {
      setPendingDiary({ date: selectedDate, type, exists: Boolean(text.trim()), changeId: result.changeId })
      setStatusMessage(`${type === 'morning' ? '晨间' : '晚间'}日记已送达，奖励确认中`)
    } else if (result.state === 'rejected') {
      setPendingDiary(null)
      setStatusMessage(`日记同步被拒绝：${result.reason || '服务端未接受本次保存'}`)
    } else {
      setPendingDiary({ date: selectedDate, type, exists: Boolean(text.trim()), changeId: result.changeId })
      setStatusMessage('日记已本地保存，奖励等待服务端确认')
    }
  }, [selectedDate])

  const changeSelectedDate = useCallback((date: string) => {
    setSleepData(null)
    setSelectedDate(date)
    setPendingDiary(null)
    setStatusMessage('')
    setUploadMessage('')
    syncAfterDateSwitch('sleep', date)
      .then(() => setRefreshTrigger(prev => prev + 1))
      .catch(error => console.warn('[useSleep] date switch sync failed:', error))
  }, [])

  const pollJobStatus = useCallback((baseUrl: string, token: string, requestId: string, date: string) => {
    setIsAnalyzing(true)
    setStatusMessage('正在分析中...')
    const interval = setInterval(async () => {
      try {
        const res = await platformFetch(`${baseUrl.replace(/\/$/, '')}/status/${requestId}`, {
          headers: {
            Authorization: `Bearer ${token}`,
            'X-Auth-Token': token
          }
        })
        if (!res.ok) throw new Error('服务端状态查询失败')
        const job = await res.json()
        if (job.status === 'uploaded') {
          clearInterval(interval)
          setIsAnalyzing(false)
          setStatusMessage('OCR 已识别')
          setUploadMessage('截图日期校验通过')
        } else if (job.status === 'done' || job.status === 'reused') {
          clearInterval(interval)
          const db = await getDatabase()
          const result = job.result || job.sleep_data || {}
          const resultDate = result.date || result.sleep_date || date
          db.saveSleepData(resultDate, result)
          await syncAfterDateSwitch('sleep', resultDate).catch(error => console.warn('[useSleep] report completion sync failed:', error))
          setIsAnalyzing(false)
          setStatusMessage('')
          setRefreshTrigger(prev => prev + 1)
        } else if (job.status === 'error') {
          clearInterval(interval)
          setIsAnalyzing(false)
          setStatusMessage(`分析失败: ${job.error || '未知错误'}`)
          alert(`分析失败: ${job.error || '未知错误'}`)
        } else {
          setStatusMessage(`分析进度: ${job.status === 'running' ? '分析中' : '排队中'}...`)
        }
      } catch (err: any) {
        clearInterval(interval)
        setIsAnalyzing(false)
        const message = formatSleepTransportError(err, '服务端状态查询失败')
        setStatusMessage(`获取状态出错: ${message}`)
        alert(`获取状态出错: ${message}`)
      }
    }, 2000)
  }, [])

  const pickImage = useCallback(async (file: File) => {
    const db = await getDatabase()
    let runtime
    try {
      runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'sleep.upload')
    } catch (err: any) {
      alert(err.message || '请先在设置中配置并登录当前环境')
      return
    }
    const baseUrl = runtime.serverUrl
    const token = runtime.authToken

      setIsAnalyzing(true)
      setStatusMessage('正在上传图片...')
      setUploadMessage('')

      try {
        const uploadUrl = `${baseUrl.replace(/\/$/, '')}/upload?analyze=false&date=${encodeURIComponent(selectedDate)}`
        const res = await platformUploadMultipart(uploadUrl, file, {
          headers: {
            Authorization: `Bearer ${token}`,
            'X-Auth-Token': token
          }
        })
        if (!res.ok) {
          throw new Error(await readSleepApiError(res, 'Upload failed'))
        }
        const data = await res.json()
        if (data.status === 'ok' && data.request_id) {
          pollJobStatus(baseUrl, token, data.request_id, selectedDate)
        } else {
          throw new Error('服务端未返回上传任务编号')
        }
      } catch (err: any) {
        setIsAnalyzing(false)
        setStatusMessage('')
        const message = formatSleepTransportError(err, '上传失败')
        const prefix = message.includes('日期不匹配') ? '分析失败' : '上传失败'
        alert(`${prefix}: ${message}`)
      }
  }, [selectedDate, pollJobStatus])

  const requestReport = useCallback(async (full: boolean, force: boolean, statusText: string, errorPrefix: string) => {
    const db = await getDatabase()
    let runtime
    try {
      runtime = requireActiveEnvironmentRuntimeConfig(db.getAllConfig(), 'sleep.analysis')
    } catch (err: any) {
      alert(err.message || '请先在设置中配置并登录当前环境')
      return
    }
    const baseUrl = runtime.serverUrl
    const token = runtime.authToken

    setIsAnalyzing(true)
    setUploadMessage('')
    setStatusMessage(statusText)
    try {
      const res = await platformFetch(`${baseUrl.replace(/\/$/, '')}/generate_report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          'X-Auth-Token': token
        },
        body: JSON.stringify({
          date: selectedDate,
          full,
          force
        })
      })
      if (!res.ok) {
        throw new Error(await readSleepApiError(res, 'Request failed'))
      }
      const data = await res.json()
      if (data.status === 'ok' && data.request_id) {
        pollJobStatus(baseUrl, token, data.request_id, selectedDate)
      } else {
        throw new Error(data.detail || 'Analysis request failed')
      }
    } catch (err: any) {
      setIsAnalyzing(false)
      setStatusMessage('')
      alert(`${errorPrefix}: ${formatSleepTransportError(err, '请求失败')}`)
    }
  }, [selectedDate, pollJobStatus])

  const runAnalysis = useCallback(async () => {
    await requestReport(false, false, '正在请求睡眠分析...', '分析失败')
  }, [requestReport])

  const runFullAnalysis = useCallback(async () => {
    await requestReport(true, false, '正在请求完整分析...', '分析失败')
  }, [requestReport])

  const forceRefresh = useCallback(async () => {
    await requestReport(true, true, '正在强制获取 aTimeLogger 并重新生成报告...', '刷新失败')
  }, [requestReport])

  return useMemo(
    () => ({
      sleepData,
      sleepHistory,
      selectedDate,
      setSelectedDate: changeSelectedDate,
      saveDiary,
      pickImage,
      runAnalysis,
      runFullAnalysis,
      forceRefresh,
      isAnalyzing,
      statusMessage,
      uploadMessage,
    }),
    [sleepData, sleepHistory, selectedDate, changeSelectedDate, saveDiary, pickImage, runAnalysis, runFullAnalysis, forceRefresh, isAnalyzing, statusMessage, uploadMessage],
  )
}
