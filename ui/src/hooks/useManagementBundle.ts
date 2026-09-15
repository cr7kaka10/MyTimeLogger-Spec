import { useCallback } from 'react'
import { Capacitor } from '@capacitor/core'
import { Filesystem, Directory, Encoding } from '@capacitor/filesystem'
import { Share } from '@capacitor/share'
import { platformFetch } from '../platform/fetch'
import type { ManagementPlanRuntime } from './useManagementPlan'

export function useManagementBundle(runtime: ManagementPlanRuntime) {
  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${runtime.authToken}`,
        'X-Auth-Token': runtime.authToken,
        'Content-Type': 'application/json',
        ...(init.headers || {})
      }
    })
    
    const textData = await response.text()
    
    if (init.headers && (init.headers as Record<string, string>)['Accept'] === 'application/octet-stream') {
      if (!response.ok) throw new Error('导出方案失败')
      return textData
    }
    
    let body = null
    try {
      body = textData ? JSON.parse(textData) : null
    } catch (e) {
      // ignore JSON parse error
    }
    
    if (!response.ok) throw new Error(body?.detail?.message || body?.detail || '请求方案数据失败')
    return body
  }, [runtime.authToken, runtime.serverUrl])

  const exportBundle = useCallback(async () => {
    console.log('[exportBundle] Started export bundle process')
    try {
      const response = await platformFetch(`${runtime.serverUrl.replace(/\/$/, '')}/api/v1/management-plan/export`, {
        headers: { Authorization: `Bearer ${runtime.authToken}`, 'X-Auth-Token': runtime.authToken }
      })
      console.log('[exportBundle] Fetch response received:', response.status, response.ok)
      if (!response.ok) throw new Error('导出失败 (HTTP ' + response.status + ')')
      const textData = await response.text()
      console.log('[exportBundle] Text data received, length:', textData?.length)
      const fileName = `management-plan-bundle-${new Date().toISOString().split('T')[0]}.json`

      if (Capacitor.isNativePlatform()) {
        console.log('[exportBundle] Native platform detected, saving to filesystem...')
        const writeResult = await Filesystem.writeFile({
          path: fileName,
          data: textData,
          directory: Directory.Cache,
          encoding: Encoding.UTF8
        })
        console.log('[exportBundle] File written to:', writeResult.uri)

        await Share.share({
          title: '导出管理方案',
          text: '这是我的 MyTimeLogger 管理方案数据',
          url: writeResult.uri,
          dialogTitle: '分享管理方案'
        })
        console.log('[exportBundle] Native share completed')
      } else {
        console.log('[exportBundle] Web platform detected, triggering download...')
        const blob = new Blob([textData], { type: 'application/json' })
        const url = window.URL.createObjectURL(blob)
        console.log('[exportBundle] Blob URL created:', url)
        const a = document.createElement('a')
        a.href = url
        a.download = fileName
        document.body.appendChild(a)
        a.click()
        console.log('[exportBundle] Download link clicked')
        setTimeout(() => {
          window.URL.revokeObjectURL(url)
          document.body.removeChild(a)
          console.log('[exportBundle] Cleanup completed')
        }, 1000)
      }
    } catch (error) {
      console.error('[exportBundle] Error occurred:', error)
      throw error
    }
  }, [runtime.authToken, runtime.serverUrl])

  const previewBundle = useCallback((payload: { bundle: any, mode: 'merge' | 'synchronize' }) => {
    return request('/api/v1/management-plan/import/preview', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }, [request])

  const applyBundle = useCallback((payload: { bundle: any, mode: string, idempotency_key: string }) => {
    return request('/api/v1/management-plan/import/apply', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }, [request])

  return { exportBundle, previewBundle, applyBundle }
}
