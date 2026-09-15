import { useCallback, useState } from 'react'
import { getDatabase } from '../db'

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export function useAiChat() {
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const checkConfig = useCallback(async () => {
    const db = await getDatabase()
    let endpoint = db.getConfig('ai_text_endpoint')
    let apiKey = db.getConfig('ai_text_api_key')
    let model = db.getConfig('ai_text_model') || 'glm-4-flash'

    if (!apiKey) {
      endpoint = db.getConfig('ai_vision_endpoint')
      apiKey = db.getConfig('ai_vision_api_key')
      model = db.getConfig('ai_vision_model') || 'glm-4v-flash'
    }

    if (!endpoint || !apiKey) {
      throw new Error('未配置 AI 接口，请前往设置配置 endpoint 和 api_key')
    }

    return { endpoint, apiKey, model }
  }, [])

  const sendMessage = useCallback(async (messages: ChatMessage[]) => {
    setIsGenerating(true)
    setError(null)
    try {
      const { endpoint, apiKey, model } = await checkConfig()

      const url = endpoint.endsWith('/chat/completions') ? endpoint : `${endpoint}/chat/completions`

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model,
          messages,
        }),
      })

      if (!response.ok) {
        throw new Error(`AI 请求失败: ${response.status} ${response.statusText}`)
      }

      const data = await response.json()
      if (data.choices && data.choices.length > 0) {
        return data.choices[0].message.content as string
      }
      throw new Error('AI 返回的数据格式不正确')
    } catch (err: any) {
      console.error('AI Chat Error:', err)
      setError(err.message || '未知错误')
      return null
    } finally {
      setIsGenerating(false)
    }
  }, [checkConfig])

  return {
    sendMessage,
    isGenerating,
    error,
    clearError: () => setError(null),
  }
}
