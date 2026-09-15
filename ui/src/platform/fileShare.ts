import { Directory, Encoding, Filesystem } from '@capacitor/filesystem'
import { Share } from '@capacitor/share'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'

type FilesystemPort = Pick<typeof Filesystem, 'writeFile' | 'deleteFile'>
type SharePort = Pick<typeof Share, 'share'>
export interface TextFileShareOptions { mimeType?: string; dialogTitle?: string }

export async function shareTextFile(filename: string, content: string, options: TextFileShareOptions = {}, runtime: PlatformRuntime = detectPlatformRuntime(), filesystem: FilesystemPort = Filesystem, share: SharePort = Share): Promise<void> {
  if (runtime === 'capacitor-android') {
    const path = `exports/${filename}`
    const saved = await filesystem.writeFile({ path, data: content, directory: Directory.Cache, encoding: Encoding.UTF8, recursive: true })
    try { await share.share({ title: filename, files: [saved.uri], dialogTitle: options.dialogTitle || '分享配置' }) }
    finally { await filesystem.deleteFile({ path, directory: Directory.Cache }).catch(() => {}) }
    return
  }
  const url = URL.createObjectURL(new Blob([content], { type: options.mimeType || 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove()
  URL.revokeObjectURL(url)
}
