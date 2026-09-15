import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { LoginPage, normalizeServerUrl } from './LoginPage'

declare const test: (name: string, body: () => void) => void
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

test('Android login input contract and empty first-run credentials', () => {
  assert(normalizeServerUrl('192.168.1.80:8000') === 'http://192.168.1.80:8000', 'LAN address must gain the HTTP scheme')
  const html = renderToStaticMarkup(<LoginPage
    environment="development" serverUrl="http://10.0.2.2:8000" defaultUsername=""
    savedLoginReady={false} checkingSavedLogin={false}
    onLogin={async () => ({ success: false })} onServerUrlChange={async () => undefined}
    onAuthenticated={() => undefined}
  />)
  const username = html.match(/<input[^>]*name="username"[^>]*>/)?.[0] || ''
  const password = html.match(/<input[^>]*name="password"[^>]*>/)?.[0] || ''
  assert(/type="text"/i.test(username) && /inputmode="email"/i.test(username), 'username must request the standard key keyboard without email validation')
  assert(/autocomplete="username"/i.test(username) && /enterkeyhint="next"/i.test(username), 'username must expose username/next semantics')
  assert(/autocapitalize="none"/i.test(username) && /autocorrect="off"/i.test(username) && /spellcheck="false"/i.test(username), 'username must disable capitalization, correction, and spellcheck')
  assert(/value=""/i.test(username), 'first-run username must be empty')
  assert(/type="password"/i.test(password) && /value=""/i.test(password), 'first-run password must be empty and masked')
  assert(html.includes('aria-label="显示密码"'), 'password visibility control must remain available')
  assert(html.includes('保持登录') && !html.includes('记住登录'), 'login page must describe persistent sessions instead of saving a password')
  assert(!/Gboard|手写|username-ime-help/i.test(html), 'login page must not show handwriting or keyboard-switch guidance')
  assert(html.includes('10.0.2.2:8000'), 'Android development endpoint must remain on port 8000')
})

console.log('LoginPage input contract tests passed')
