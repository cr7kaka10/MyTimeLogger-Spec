export interface RewardRebuildFailureView {
  code: string
  message: string
  stage: string
  causes: string[]
  recovery: string
  suggestions: string[]
  traceId: string
  jobId: string
  occurredAt: string
  copyText: string
}

const text = (value: unknown, fallback = '', limit = 240) => {
  const result = typeof value === 'string' || typeof value === 'number' ? String(value).trim() : ''
  return (result || fallback)
    .replace(/Bearer\s+[^\s]+/gi, 'Bearer [secret]')
    .replace(/https?:\/\/[^\s]+/gi, '[url]')
    .replace(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g, '[account]')
    .replace(/[A-Z]:\\[^\s]+/gi, '[path]')
    .slice(0, limit)
}

const stageNames: Record<string, string> = {
  capability_check: '服务端能力检查', preview: '重建预览', job_create: '创建作业',
  ticktick_reset: '清理旧清单投影', provider_pull: '重新拉取滴答清单',
  candidate_build: '重新计算奖励', candidate_validate: '核对候选账',
  publish: '发布新账', restore: '恢复旧账', job_poll: '查询重建进度',
  client_sync: '本地同步', unknown: '未知阶段',
}

const causeLine = (cause: unknown) => {
  const item = cause && typeof cause === 'object' ? cause as Record<string, unknown> : {}
  const chain = text(item.chain, 'unknown', 32)
  const message = text(item.message_zh, text(item.code, '未知分链异常'))
  const counts = ['expected', 'actual', 'missing']
    .map(key => item[key] === undefined || item[key] === null ? '' : `${key}=${text(item[key], '', 24)}`)
    .filter(Boolean).join('，')
  return `${chain}：${message}${counts ? `（${counts}）` : ''}`
}

export const parseRewardRebuildFailure = (
  job: unknown,
  fallback: { traceId: string, jobId?: string, stage?: string, message?: string },
): RewardRebuildFailureView => {
  const record = job && typeof job === 'object' ? job as Record<string, any> : {}
  const report = record.failure_report && typeof record.failure_report === 'object'
    ? record.failure_report as Record<string, any> : {}
  const code = text(report.code, text(record.error, 'unknown_error'))
  const message = text(report.message_zh, fallback.message || `重建失败：${code}`)
  const rawStage = text(report.failed_stage, fallback.stage || 'unknown', 48)
  const stage = stageNames[rawStage] || rawStage
  const causes = (Array.isArray(report.causes) ? report.causes : []).slice(0, 20).map(causeLine)
  const recoveryRecord = report.recovery && typeof report.recovery === 'object' ? report.recovery : {}
  const recovery = recoveryRecord.status === 'restored'
    ? recoveryRecord.verified === true ? '旧账已恢复并核对通过' : '旧账已恢复，但核对未通过'
    : recoveryRecord.status === 'failed' ? '旧账恢复失败，请勿再次操作并复制诊断信息'
      : '本次失败发生在发布前，无需恢复旧账'
  const suggestions = (Array.isArray(report.suggestions) ? report.suggestions : [])
    .slice(0, 8).map((item: unknown) => text(item)).filter(Boolean)
  const traceId = text(report.trace_id, text(record.trace_id, fallback.traceId), 128)
  const jobId = text(report.job_id, text(record.id, fallback.jobId || ''), 128)
  const occurredAt = text(report.occurred_at, new Date().toLocaleString('zh-CN', { hour12: false }), 40)
  const lines = [
    '金币流水重建失败诊断', `诊断编号：${traceId}`, jobId ? `作业编号：${jobId}` : '',
    `错误码：${code}`, `失败阶段：${stage}`, `时间：${occurredAt}`, `原因数量：${causes.length}`,
    ...causes.map(item => `- ${item}`), `恢复结果：${recovery}`,
    ...suggestions.map(item => `建议：${item}`),
  ].filter(Boolean)
  return { code, message, stage, causes, recovery, suggestions, traceId, jobId, occurredAt, copyText: lines.join('\n') }
}

export const logRewardRebuildStage = (fields: {
  requestId: string, traceId?: string, jobId?: string, stage: string,
  outcome: 'start' | 'success' | 'failure', httpStatus?: number, errorType?: string,
}) => {
  const payload = { ...fields, traceId: fields.traceId || fields.requestId }
  if (fields.outcome === 'failure') console.error('[reward-rebuild-stage]', payload)
  else console.info('[reward-rebuild-stage]', payload)
}

export const rewardRebuildHeader = (headers: Record<string, string>, name: string) => {
  const match = Object.entries(headers || {}).find(([key]) => key.toLowerCase() === name.toLowerCase())
  return match?.[1] || ''
}
