import React, { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { useAiChat, ChatMessage } from '../../hooks/useAiChat'
import { LearningObjective } from '../../hooks/useLearning'
import { buildLearningDecompositionPrompt } from './learningDecompositionSkill'
import { parseLearningPlanJson } from './learningPlanParser'

interface AiCopilotDrawerProps {
  objective: LearningObjective
  onClose: () => void
  onAcceptJson: (json: string) => void
}

export const AiCopilotDrawer: React.FC<AiCopilotDrawerProps> = ({ objective, onClose, onAcceptJson }) => {
  const { sendMessage, isGenerating, error, clearError } = useAiChat()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [acceptError, setAcceptError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 初始启动时，注入系统提示词并发起首轮推荐
  useEffect(() => {
    const initChat = async () => {
      // 检测用户是否填写了持续时长
      const hasDuration = objective.duration && objective.duration > 0
      
      const systemPromptContent = buildLearningDecompositionPrompt(objective.duration)
      const sysMsg: ChatMessage = {
        role: 'system',
        content: systemPromptContent
      }
      
      // 构建用户首轮消息，包含完整上下文
      const baseline = objective.baseline || '从零开始'
      const targetDescription = objective.target_description || '掌握核心技能'
      const duration = objective.duration
      
      let userPrompt = `我有一个学习目标：${objective.title}\n`
      if (hasDuration && duration) {
        userPrompt += `持续时长：${duration} 天\n`
      }
      userPrompt += `当前现状：${baseline}\n`
      userPrompt += `期望达到：${targetDescription}\n\n`
      
      if (!hasDuration) {
        userPrompt += `请帮我：\n1. 推荐 3~6 个符合 OKR 规范的 KR（Key Results）\n2. 为每个 KR 拆解出多个 1.5 小时内能完成的最小执行单元任务\n3. 根据所有任务总时长（任务数 × 1.5h），按每天 6h 上限计算，向上取整并留 20% buffer，推荐合理的持续天数\n\n请踏踏实实地拆解任务，不要眼高手低。`
      } else if (duration) {
        userPrompt += `约束条件：\n- 我每天最多有 4 个 1.5 小时（共 6 小时）可以用于学习\n- 持续时长 ${duration} 天，意味着总共有 ${duration * 6}h 可用\n- 每个最小执行单元任务应该在 1.5 小时内完成\n\n请帮我：\n1. 推荐 3~6 个符合 OKR 规范的 KR（Key Results）\n2. 为每个 KR 拆解出多个 1.5 小时内能完成的最小执行单元任务\n3. 任务总数不应超过 ${Math.floor(duration * 4)} 个任务\n\n请踏踏实实地拆解任务，不要眼高手低。`
      }
      
      const userMsg: ChatMessage = {
        role: 'user',
        content: userPrompt
      }

      setMessages([sysMsg, userMsg])
      const res = await sendMessage([sysMsg, userMsg])
      if (res) {
        setMessages(prev => [...prev, { role: 'assistant', content: res }])
      }
    }
    initChat()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // 仅挂载时执行

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isGenerating])

  const handleSend = async () => {
    if (!inputValue.trim() || isGenerating) return
    const newMsg: ChatMessage = { role: 'user', content: inputValue.trim() }
    const newMsgs = [...messages, newMsg]
    setMessages(newMsgs)
    setInputValue('')
    
    const res = await sendMessage(newMsgs)
    if (res) {
      setMessages(prev => [...prev, { role: 'assistant', content: res }])
    }
  }

  // 尝试从文本中提取出 json
  const extractJson = (text: string) => {
    const jsonMatch = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/)
    if (jsonMatch) return jsonMatch[1]
    
    // 如果没有包裹，且看起来像 json，也尝试
    if (text.trim().startsWith('{') && text.trim().endsWith('}')) {
      return text.trim()
    }
    return null
  }

  // 从展示给用户的文本中剔除掉底层的 JSON 代码块，避免辣眼睛
  const stripJsonForDisplay = (text: string) => {
    return text.replace(/```(?:json)?\s*[\s\S]*?\s*```/g, '').trim()
  }

  const handleAccept = (content: string) => {
    const jsonText = extractJson(content)
    if (!jsonText) {
      alert('未能在回答中找到 JSON 格式内容！')
      return
    }
    try {
      const plan = parseLearningPlanJson(jsonText)
      setAcceptError('')
      onAcceptJson(JSON.stringify(plan))
      onClose()
    } catch (cause) {
      setAcceptError(cause instanceof Error ? cause.message : 'AI 方案分类校验失败')
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex h-screen h-[100dvh] w-full max-w-[24rem] transform flex-col bg-white shadow-2xl transition-transform duration-300">
      <div className="px-4 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/80 backdrop-blur">
        <div>
          <h3 className="font-bold text-gray-800 flex items-center gap-2">
            <span>✨</span> AI Copilot
          </h3>
          <p className="text-xs text-gray-500 mt-0.5 truncate max-w-[200px]" title={objective.title}>
            目标: {objective.title}
          </p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 bg-white shadow-sm border border-gray-100 rounded p-1">
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50/30">
        {messages.filter(m => m.role !== 'system').map((msg, i) => (
          <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
              msg.role === 'user' 
                ? 'bg-blue-500 text-white shadow-md shadow-blue-500/20' 
                : 'bg-white border border-gray-200 text-gray-800 shadow-sm'
            }`}>
              {msg.role === 'user' ? (
                <div className="whitespace-pre-wrap">{msg.content}</div>
              ) : (
                <div className="react-markdown-container space-y-2 leading-relaxed [&>h1]:font-bold [&>h1]:text-lg [&>h2]:font-bold [&>h2]:text-base [&>h3]:font-bold [&>ul]:list-disc [&>ul]:pl-4 [&>ol]:list-decimal [&>ol]:pl-4 [&>p>strong]:font-bold [&>p>strong]:text-gray-900">
                  <ReactMarkdown>{stripJsonForDisplay(msg.content)}</ReactMarkdown>
                </div>
              )}
              
              {msg.role === 'assistant' && extractJson(msg.content) && (
                <div className="mt-3 pt-3 border-t border-gray-100/50 flex justify-end">
                  <button 
                    onClick={() => handleAccept(msg.content)}
                    className="text-xs font-medium bg-blue-50 hover:bg-blue-100 text-blue-600 px-3 py-1.5 rounded-lg transition-colors border border-blue-200"
                  >
                    🚀 一键采纳方案
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
        {isGenerating && (
          <div className="flex items-start">
            <div className="bg-white border border-gray-200 rounded-2xl px-4 py-2.5 text-sm text-gray-400 shadow-sm flex items-center gap-2">
              <span className="animate-pulse">✨ AI 正在思考中...</span>
            </div>
          </div>
        )}
        {error && (
          <div className="bg-red-50 text-red-600 border border-red-100 p-3 rounded-lg text-sm">
            <div className="flex justify-between items-start">
              <span>{error}</span>
              <button onClick={clearError} className="opacity-50 hover:opacity-100">✕</button>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-gray-100 bg-white">
        {acceptError && <div className="mb-2 rounded-lg border border-red-100 bg-red-50 p-2 text-sm text-red-600">{acceptError}</div>}
        <div className="flex gap-2">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder="提出修改意见..."
            className="flex-1 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:bg-white resize-none shadow-sm transition-all"
            rows={2}
          />
          <button 
            onClick={handleSend}
            disabled={!inputValue.trim() || isGenerating}
            className="bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-xl px-4 font-medium transition-all shadow-md self-end h-[42px]"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  )
}
