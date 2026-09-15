import { useEffect, useRef, useState } from 'react'
import type { EnvironmentName } from '@core/EnvironmentProfiles'
import { platformFetch } from '../../platform'

type Props = {
  environment: EnvironmentName
  serverUrl: string
  defaultUsername: string
  savedLoginReady: boolean
  checkingSavedLogin: boolean
  onLogin: (username: string, password: string, environment: EnvironmentName) => Promise<{ success: boolean; error?: string; activated?: boolean }>
  onServerUrlChange: (serverUrl: string) => Promise<void>
  onAuthenticated: (accountActivated?: boolean) => void
}

export const resolveSavedUsername = (current: string, incoming: string, edited: boolean) =>
  edited ? current : incoming || ''

const readBody = async (response: { text: () => Promise<string> }) => {
  const text = await response.text()
  if (!text) return {}
  try { return JSON.parse(text) } catch { return { detail: text } }
}

const SAVED_PASSWORD_MASK = '••••••••'
export const normalizeServerUrl = (value: string) => {
  const trimmed = value.trim().replace(/\/+$/, '')
  if (!trimmed || /^https?:\/\//i.test(trimmed)) return trimmed
  return `http://${trimmed}`
}
export const formatAuthenticationFailure = (error: string | undefined, serverUrl: string) =>
  error === '账号或密码错误'
    ? `账号或密码错误（HTTP 401，服务端：${serverUrl}）。若这是全新服务端，请切换到“注册”。`
    : error || '登录失败'

export const formatLoginRequestError = (error: any) => {
  const message = String(error?.message || '')
  if (/abort|timeout|timed out/i.test(message)) return '请求超时，请检查服务端是否正在运行'
  if (/cleartext/i.test(message)) return 'Android 阻止了明文 HTTP，请更新 Debug APK 或改用 HTTPS'
  if (/failed to fetch|network|connect|refused|unreachable/i.test(message)) return '无法连接服务端，请确认手机与电脑在同一局域网、服务端监听 0.0.0.0:8000，并检查 Windows 防火墙'
  return message || '请求失败'
}

export function LoginPage({ environment, serverUrl, defaultUsername, savedLoginReady, checkingSavedLogin, onLogin, onServerUrlChange, onAuthenticated }: Props) {
  const [serverAddress, setServerAddress] = useState(serverUrl)
  const [username, setUsername] = useState(defaultUsername || '')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const usernameEditedRef = useRef(false)
  const passwordRef = useRef<HTMLInputElement>(null)
  const base = normalizeServerUrl(serverAddress)

  useEffect(() => setServerAddress(serverUrl), [serverUrl])

  useEffect(() => {
    setUsername(current => resolveSavedUsername(current, defaultUsername, usernameEditedRef.current))
  }, [defaultUsername])

  useEffect(() => {
    if (mode === 'login' && savedLoginReady) {
      setPassword(current => current || SAVED_PASSWORD_MASK)
      return
    }
    setPassword(current => current === SAVED_PASSWORD_MASK ? '' : current)
  }, [mode, savedLoginReady])

  const submit = async () => {
    const usingSavedLogin = mode === 'login' && savedLoginReady && (!password || password === SAVED_PASSWORD_MASK)
    if (usingSavedLogin) {
      setMessage('已使用保存的登录进入')
      onAuthenticated(false)
      return
    }
    if (!base || !username.trim() || !password) {
      setMessage(savedLoginReady ? '请输入密码重新登录，或清空密码直接使用保存的登录' : '缺少服务端地址、账号或密码')
      return
    }
    setBusy(true)
    setMessage(mode === 'login' ? '正在登录...' : '正在注册...')
    try {
      await onServerUrlChange(base)
      if (mode === 'register') {
        const response = await platformFetch(`${base}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: username.trim(), password }),
          timeoutMs: 5000,
        } as any)
        if (!response.ok) {
          const body = await readBody(response)
          throw new Error(body.detail || `注册失败 (${response.status})`)
        }
      }
      const result = await onLogin(username.trim(), password, environment)
      if (result.success) {
        setPassword('')
        setMessage('登录成功')
        onAuthenticated(Boolean(result.activated))
      } else {
        setMessage(formatAuthenticationFailure(result.error, base))
      }
    } catch (error: any) {
      setMessage(formatLoginRequestError(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="theme-page !bg-transparent relative flex min-h-[100dvh] w-full max-w-full items-start justify-center overflow-x-hidden overflow-y-auto pb-[env(safe-area-inset-bottom)] pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))] pt-[env(safe-area-inset-top)] md:min-h-screen md:items-center md:overflow-hidden md:px-0">


      <section className="relative my-3 grid w-full max-w-[860px] overflow-hidden rounded-[28px] border border-white/80 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.12)] md:my-0 md:grid-cols-[0.95fr_1.05fr]">
        <div className="hidden min-h-[520px] flex-col justify-between bg-[#1e3a5f] p-8 text-white md:flex">
          <div>
            <div className="mb-8 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/14 text-2xl">⏱</div>
            <h1 className="text-3xl font-bold leading-tight">MyTimeLogger</h1>
            <p className="mt-4 max-w-[260px] text-sm leading-6 text-blue-100">登录后同步你的计时、清单、学习和运动数据。</p>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="h-24 rounded-2xl bg-white/10 p-3">
              <div className="text-2xl">✓</div>
              <div className="mt-5 text-xs text-blue-100">清单同步</div>
            </div>
            <div className="h-24 rounded-2xl bg-white/10 p-3">
              <div className="text-2xl">⌁</div>
              <div className="mt-5 text-xs text-blue-100">计时备份</div>
            </div>
            <div className="h-24 rounded-2xl bg-white/10 p-3">
              <div className="text-2xl">◇</div>
              <div className="mt-5 text-xs text-blue-100">安全配置</div>
            </div>
          </div>
        </div>

        <div className="px-6 py-8 sm:px-10 md:py-12">
          <div className="mb-8 md:hidden">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-2xl text-white">⏱</div>
            <h1 className="text-3xl font-bold text-gray-950">MyTimeLogger</h1>
          </div>
          <div className="mb-8 hidden md:block">
            <h2 className="text-2xl font-bold text-gray-950">{mode === 'login' ? '欢迎回来' : '创建账号'}</h2>
            <p className="mt-2 text-sm text-gray-500">{savedLoginReady ? '已找到保存的登录，点击登录进入。' : '连接服务端后开始同步你的个人时间数据。'}</p>
          </div>
          <div className="mb-6 grid rounded-2xl bg-gray-100 p-1">
            <div className="grid grid-cols-2 gap-1">
              <button type="button" onClick={() => setMode('login')} className={`h-11 rounded-xl text-sm font-semibold transition ${mode === 'login' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500'}`}>登录</button>
              <button type="button" onClick={() => setMode('register')} className={`h-11 rounded-xl text-sm font-semibold transition ${mode === 'register' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500'}`}>注册</button>
            </div>
          </div>
          <label className="mb-4 block">
            <span className="mb-2 block text-sm font-medium text-gray-700">服务端地址</span>
            <input value={serverAddress} placeholder="http://127.0.0.1:8000" onChange={event => setServerAddress(event.target.value)} className="h-12 w-full rounded-2xl border border-gray-200 bg-gray-50 px-4 text-gray-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" />
          </label>
          <label className="mb-4 block">
            <span className="mb-2 block text-sm font-medium text-gray-700">账号</span>
            <input name="username" type="text" inputMode="email" autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false} enterKeyHint="next" value={username} placeholder="账号" onChange={event => { usernameEditedRef.current = true; setUsername(event.target.value) }} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); passwordRef.current?.focus() } }} className="h-12 w-full rounded-2xl border border-gray-200 bg-gray-50 px-4 text-gray-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" />
          </label>
          <label className="mb-5 block">
            <span className="mb-2 block text-sm font-medium text-gray-700">密码</span>
            <div className="relative">
              <input ref={passwordRef} name="password" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} value={password} placeholder="密码" onFocus={() => { if (password === SAVED_PASSWORD_MASK) setPassword('') }} onChange={event => setPassword(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') submit() }} className="h-12 w-full rounded-2xl border border-gray-200 bg-gray-50 px-4 pr-16 text-gray-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" />
              <button type="button" aria-label={showPassword ? '隐藏密码' : '显示密码'} aria-pressed={showPassword} onClick={() => setShowPassword(current => !current)} className="absolute inset-y-0 right-3 text-sm font-medium text-blue-700">{showPassword ? '隐藏' : '显示'}</button>
            </div>
          </label>
          <p className="mb-6 rounded-2xl bg-gray-50 px-4 py-3 text-sm font-medium text-gray-600">保持登录：登录后将持续保持登录，直到你在设置中手动退出。</p>
          <button type="button" disabled={busy} onClick={submit} className="h-12 w-full rounded-2xl bg-blue-600 text-sm font-bold text-white shadow-[0_12px_30px_rgba(37,99,235,0.28)] transition hover:bg-blue-700 active:translate-y-px disabled:opacity-60">
            {busy || checkingSavedLogin ? '请稍候...' : mode === 'login' ? '登录' : '注册并登录'}
          </button>
          {message && <p className="mt-5 rounded-2xl bg-gray-50 px-4 py-3 text-center text-sm text-gray-500">{message}</p>}
        </div>
      </section>
    </div>
  )
}
