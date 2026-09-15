export function exerciseStatusPresentation(status?: number) {
  if (status === 1) return { className: 'done', label: '已完成', mark: '✓' }
  if (status === -1) return { className: 'skip', label: '已跳过', mark: '✗' }
  return { className: '', label: '未打卡', mark: '' }
}
