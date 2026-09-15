/** LWW 冲突仲裁器 — 从 app/core/sync_resolver.py 逐行翻译 */

export enum SyncAction {
  PULL = 'pull',   // 服务端数据更新，覆盖本地
  PUSH = 'push',   // 本地数据更新，推送到服务端
  SKIP = 'skip',   // 完全相同，无需操作
}

export function resolve(
  local: Record<string, any> | null,
  server: Record<string, any> | null,
  hasPendingOutbox = false,
): SyncAction {
  if (!local && server) return SyncAction.PULL
  if (local && !server) return hasPendingOutbox ? SyncAction.PUSH : SyncAction.SKIP
  if (!local && !server) return SyncAction.SKIP
  if (hasPendingOutbox) return SyncAction.PUSH
  return SyncAction.PULL
}
