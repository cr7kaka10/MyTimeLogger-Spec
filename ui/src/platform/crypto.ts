import { getElectronApi, isElectron } from './electron'

// 简单的 Web 端降级加密（仅防君子，防不防得住看造化，因为真正的安全在 Electron safeStorage）
// 这里用简单的 Base64 加上一点混淆
const fallbackEncrypt = (text: string): string => {
  if (!text) return text
  try {
    const b64 = btoa(encodeURIComponent(text))
    return 'WEB_ENC:' + b64
  } catch {
    return text
  }
}

const fallbackDecrypt = (text: string): string => {
  if (!text || !text.startsWith('WEB_ENC:')) return text
  try {
    const b64 = text.substring(8)
    return decodeURIComponent(atob(b64))
  } catch {
    return text
  }
}

export const encryptString = (text: string): string => {
  if (!text) return text
  if (isElectron()) {
    const api = getElectronApi()
    if (api?.encryptStringSync) {
      return api.encryptStringSync(text)
    }
  }
  return fallbackEncrypt(text)
}

export const decryptString = (encryptedText: string): string => {
  if (!encryptedText) return encryptedText
  if (isElectron() && encryptedText.startsWith('ENC:')) {
    const api = getElectronApi()
    if (api?.decryptStringSync) {
      return api.decryptStringSync(encryptedText)
    }
  }
  return fallbackDecrypt(encryptedText)
}
