import React, { useState, useEffect } from 'react'
import type { ManagementPlanRuntime } from '../../hooks/useManagementPlan'
import { useManagementBundle } from '../../hooks/useManagementBundle'

interface Props {
  runtime: ManagementPlanRuntime
  isOpen: boolean
  bundle: any
  onClose: () => void
  onSuccess: () => void
}

export function ManagementBundleImportModal({ runtime, isOpen, bundle, onClose, onSuccess }: Props) {
  const { previewBundle, applyBundle } = useManagementBundle(runtime)
  const [mode, setMode] = useState<'merge' | 'synchronize'>('merge')
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<any>(null)
  
  // Use a ref to store a single idempotency key for this modal instance
  const [idempotencyKey] = useState(() => (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') ? globalThis.crypto.randomUUID() : `import-${Date.now()}-${Math.random().toString(36).slice(2)}`)

  useEffect(() => {
    if (!isOpen || !bundle) return
    
    let active = true
    const fetchPreview = async () => {
      setLoading(true)
      setError('')
      try {
        const res = await previewBundle({ bundle, mode })
        if (active) {
          setPreview(res)
        }
      } catch (err: any) {
        if (active) {
          setError(err.message || '获取预览失败')
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }
    
    fetchPreview()
    return () => { active = false }
  }, [isOpen, bundle, mode, previewBundle])

  const handleApply = async () => {
    setApplying(true)
    setError('')
    try {
      await applyBundle({ bundle, mode, idempotency_key: idempotencyKey })
      onSuccess()
    } catch (err: any) {
      setError(err.message || '应用失败')
    } finally {
      setApplying(false)
    }
  }

  if (!isOpen) return null

  const added = preview?.nodes?.filter((n: any) => n.action === 'add')?.length || 0
  const updated = preview?.nodes?.filter((n: any) => n.action === 'update')?.length || 0
  const archived = preview?.nodes?.filter((n: any) => n.action === 'archive')?.length || 0
  const matched = preview?.nodes?.filter((n: any) => n.action === 'match')?.length || 0

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-[600px] max-w-full">
        <h2 className="text-xl font-bold mb-4 text-gray-800">导入管理方案</h2>
        <p className="mb-4 rounded bg-teal-50 p-3 text-sm text-teal-800">先预检、后确认应用；当前仅支持分类、任务、习惯和学习目标。其他领域如有变更，整次导入会被拒绝，不会部分写入。</p>
        
        {/* Mode Selector */}
        <div className="flex gap-4 mb-6 border-b pb-4">
          <label className="flex items-center cursor-pointer">
            <input 
              type="radio" 
              name="import_mode" 
              className="mr-2"
              checked={mode === 'merge'} 
              onChange={() => setMode('merge')} 
              disabled={loading || applying}
            />
            <div>
              <div className="font-semibold text-gray-800">追加模式 (Merge)</div>
              <div className="text-sm text-gray-500">仅添加新项和更新差异，当前存在但不在此包中的数据将保持原样。</div>
            </div>
          </label>
          <label className="flex items-center cursor-pointer">
            <input 
              type="radio" 
              name="import_mode" 
              className="mr-2"
              checked={mode === 'synchronize'} 
              onChange={() => setMode('synchronize')} 
              disabled={loading || applying}
            />
            <div>
              <div className="font-semibold text-gray-800">同步模式 (Synchronize)</div>
              <div className="text-sm text-gray-500">在当前支持领域内同步差异；未支持领域有变化时不会应用。</div>
            </div>
          </label>
        </div>

        {/* Diff Preview */}
        <div className="bg-gray-50 p-4 rounded-md mb-6 min-h-[120px]">
          <h3 className="font-semibold text-gray-700 mb-2">变更预览</h3>
          {loading ? (
            <div className="text-gray-500 text-sm">正在计算差异...</div>
          ) : error ? (
            <div className="text-red-500 text-sm">{error}</div>
          ) : preview ? (
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-green-50 text-green-700 p-2 rounded">
                新增节点: <span className="font-bold">{added}</span>
              </div>
              <div className="bg-yellow-50 text-yellow-700 p-2 rounded">
                更新节点: <span className="font-bold">{updated}</span>
              </div>
              <div className="bg-red-50 text-red-700 p-2 rounded">
                归档节点: <span className="font-bold">{archived}</span>
              </div>
              <div className="bg-gray-100 text-gray-600 p-2 rounded">
                匹配无变化: <span className="font-bold">{matched}</span>
              </div>
            </div>
          ) : null}
          {preview?.unresolved_relations?.length > 0 && (
            <div className="mt-4 bg-orange-100 border border-orange-300 text-orange-800 p-3 rounded text-sm">
              <span className="font-bold">⚠️ 警告：</span> 该包中存在 {preview.unresolved_relations.length} 条无法解析的关系，导入后它们将呈现为未绑定状态。
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button 
            className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50"
            onClick={onClose}
            disabled={applying}
          >
            取消
          </button>
          <button 
            className="px-4 py-2 bg-[#0f766e] text-white rounded hover:bg-[#0d6159] disabled:opacity-50 flex items-center"
            onClick={handleApply}
            disabled={loading || applying || !!error || !preview}
          >
            {applying ? '正在应用...' : '确认应用'}
          </button>
        </div>
      </div>
    </div>
  )
}
