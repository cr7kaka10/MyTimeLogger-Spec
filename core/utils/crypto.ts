// 简单的 Web 端降级加密
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
  const api = typeof window !== 'undefined' ? (window as any).electronAPI : null
  if (api && api.encryptStringSync) {
    return api.encryptStringSync(text)
  }
  return fallbackEncrypt(text)
}

export const decryptString = (encryptedText: string): string => {
  if (!encryptedText) return encryptedText
  if (encryptedText.startsWith('ENC:')) {
    const api = typeof window !== 'undefined' ? (window as any).electronAPI : null
    if (api && api.decryptStringSync) {
      return api.decryptStringSync(encryptedText)
    }
  }
  return fallbackDecrypt(encryptedText)
}
