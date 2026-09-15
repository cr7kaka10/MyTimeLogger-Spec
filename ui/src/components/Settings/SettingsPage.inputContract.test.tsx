import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { renderToStaticMarkup } from 'react-dom/server'
import { SettingsPage } from './SettingsPage'

declare const test: (name: string, body: () => void) => void
const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const source = readFileSync(fileURLToPath(new URL('./SettingsPage.tsx', import.meta.url)), 'utf8')
const databaseSource = readFileSync(fileURLToPath(new URL('../../../../core/models/Database.ts', import.meta.url)), 'utf8')
const desktopSource = readFileSync(fileURLToPath(new URL('../../../../desktop/main.js', import.meta.url)), 'utf8')

test('aTimeLogger binding inputs request the standard keyboard without changing credentials', () => {
  assert(/name="atimelogger-username"[\s\S]{0,300}type="text"[\s\S]{0,300}inputMode="email"/.test(source), 'account must be visible text with the standard keyboard hint')
  assert(/autoComplete="username"/.test(source) && /enterKeyHint="next"/.test(source), 'account must expose username and Next semantics')
  assert(/autoCapitalize="none"/.test(source) && /autoCorrect="off"/.test(source) && /spellCheck=\{false\}/.test(source), 'account must disable capitalization, correction, and spellcheck')
  assert(/name="atimelogger-password"[\s\S]{0,300}type="password"/.test(source), 'password must remain a masked password input')
  assert(/autoComplete="current-password"/.test(source) && /enterKeyHint="done"/.test(source), 'password must expose current-password and Done semantics')
  assert(/atimeloggerPasswordRef\.current\?\.focus\(\)/.test(source), 'account Enter must focus the password input')
  assert(/event\.key === 'Enter'[\s\S]{0,180}bindAtimelogger\(\)/.test(source), 'password Enter must keep the existing bind action')
  assert(/name="atimelogger-username"[\s\S]{0,900}disabled=\{atimeloggerSaving\}[\s\S]{0,220}readOnly=\{false\}/.test(source), 'account must remain editable outside an active bind')
  assert(/name="atimelogger-password"[\s\S]{0,900}disabled=\{atimeloggerSaving\}[\s\S]{0,220}readOnly=\{false\}/.test(source), 'password must remain editable outside an active bind')
  assert(/username: atimeloggerUsername\.trim\(\)[\s\S]{0,80}password: atimeloggerPassword/.test(source), 'binding payload must keep the original account and password values')
  assert(/integrationStatus\?\.atimelogger\?\.authenticated/.test(source), 'login status must come from the server verification result')
  assert(!/const atimeloggerLocalReady/.test(source), 'local credentials must not imply a verified login')
  assert(/LOCAL_SYNC_CONFIG_KEYS[\s\S]{0,500}'atimelogger_config'/.test(databaseSource), 'provider credentials must not enter generic config sync')
  assert(!/Gboard|手写|切换键盘/.test(source), 'settings must not show keyboard-switch guidance')
  assert(/import \{[^}]*platformFetch[^}]*\} from '\.\.\/\.\.\/platform'/.test(source), 'provider binding must import the shared platform requester')
  assert(/platformFetch\(`\$\{base\}\/admin\/integration-config\/status`/.test(source), 'provider status GET must use platformFetch')
  assert(/platformFetch\(`\$\{base\}\/admin\/provider-bindings\/atimelogger`/.test(source), 'provider bind PUT must use platformFetch')
  assert(!/fetch\(`\$\{base\}\/admin\/(integration-config\/status|provider-bindings\/atimelogger)/.test(source), 'provider requests must not fall back to WebView fetch')
  assert(/formatPlatformNetworkError\(error\)/.test(source), 'provider bind must map raw network failures to actionable Chinese')
})

test('desktop hotkeys are fixed and settings only describe their mapping', () => {
  assert(/const TIMER_HOTKEY = 'Alt\+C'/.test(desktopSource) && /const VISIBILITY_HOTKEY = 'Alt\+X'/.test(desktopSource), 'desktop must define the two fixed global hotkeys')
  assert(!/shortcut_toggle_timer'\)/.test(desktopSource) && !/shortcut_minimize'\)/.test(desktopSource), 'desktop must not read historical custom hotkey values')
  assert(/切换计时[\s\S]{0,160}Alt\+C/.test(source) && /隐藏\/显示[\s\S]{0,160}Alt\+X/.test(source), 'settings must show the fixed mappings')
  assert(!/capturingKey|快捷键录入弹窗|快捷键未生效/.test(source), 'settings must not expose hotkey editing or registration feedback')
})

test('all six saved audio preferences render their selected options', () => {
  const values = {
    audio_start: 'victory',
    audio_microBreak: 'end_long_break',
    audio_endMicroBreak: 'start_study',
    audio_startLongBreak: 'end_short_break',
    audio_end: 'start_long_break',
    audio_coin: 'none',
  }
  const html = renderToStaticMarkup(<SettingsPage {...({
    settings: values,
    updateSetting: () => {},
    onOpenCategoryManager: () => {},
    exportConfig: () => {},
    importConfig: () => {},
    activeEnvironment: 'development',
    selectedEnvironment: 'development',
    selectedEnvironmentProfile: { serverUrl: '', username: '', authToken: '' },
  } as any)} />)
  const expected = [
    ['专注开始', values.audio_start],
    ['微休息开始', values.audio_microBreak],
    ['微休息结束', values.audio_endMicroBreak],
    ['长休息开始', values.audio_startLongBreak],
    ['长休息结束', values.audio_end],
    ['金币/胜利', values.audio_coin],
  ]
  for (const [label, value] of expected) {
    assert(new RegExp(`${label}[\\s\\S]{0,900}<option value="${value}" selected=""`).test(html), `${label} must select saved ${value}`)
  }
})

test('account sign-out requires confirmation and returns to login without deleting data', () => {
  const settingsSource = readFileSync(fileURLToPath(new URL('../../hooks/useSettings.ts', import.meta.url)), 'utf8')
  const appSource = readFileSync(fileURLToPath(new URL('../../App.tsx', import.meta.url)), 'utf8')
  assert(/showSignOutConfirm/.test(source) && /退出当前账号\？/.test(source), 'sign-out must require a dedicated confirmation dialog')
  assert(/setShowSignOutConfirm\(false\)[\s\S]{0,300}取消/.test(source), 'cancelling sign-out must only close confirmation')
  assert(/await logoutActiveSession\(\); onSignedOut\(\)/.test(source), 'confirmed sign-out must revoke the session before returning to login')
  assert(/auth\/logout/.test(settingsSource), 'manual sign-out must revoke the server session')
  assert(/environmentKey\(activeEnvironment, 'username'\), ''/.test(settingsSource), 'sign-out must clear the current account name')
  assert(/environmentKey\(activeEnvironment, 'verified_user_id'\), ''/.test(settingsSource), 'sign-out must clear the verified identity')
  assert(!/deleteDatabase|removeAccountStorage/.test(settingsSource), 'sign-out must not delete account data')
  assert(/onSignedOut=\{\(\) => setAuthenticated\(false\)\}/.test(appSource), 'App must return to login after sign-out')
})

test('service section stays compact while the guide retains provider explanations', () => {
  const serviceSection = source.slice(source.indexOf('服务连接'), source.indexOf('{/* 计时设置 */}'))
  assert(/label="aTimeLogger备份"/.test(serviceSection), 'aTimeLogger must use the compact backup label')
  assert(!/label="(滴答清单|大模型|S3 容灾备份)"/.test(serviceSection), 'private and deployment services must not be persistent rows')
  assert(serviceSection.indexOf('首次使用教程') < serviceSection.lastIndexOf('退出当前账号'), 'sign-out must be the final service action')
  assert(/滴答清单、aTimeLogger 和大模型均为当前登录用户的私有配置/.test(source), 'guide must retain private provider scope')
  assert(/S3 容灾备份由服务管理者统一配置/.test(source), 'guide must retain deployment backup ownership')
})

test('aTimeLogger action area never reserves a single fixed button slot', () => {
  assert(/grid-cols-\[148px_minmax\(0,1fr\)_max-content\]/.test(source), 'service row must size its final column for all visible actions')
  assert(/flex min-w-0 flex-wrap items-center justify-end gap-2/.test(source), 'status and actions must wrap instead of overflowing')
  assert(/flex flex-wrap justify-end gap-2 max-sm:justify-start/.test(source), 'retry and login buttons must remain complete on narrow screens')
})

test('checklist reset blocks an old server or a failed preview before confirmation', () => {
  assert(/platformFetch\(`\$\{base\}\/ping`, \{ headers: \{ 'X-Request-ID': requestId \} \}\)/.test(source), 'reset must check the running server capability first')
  assert(/!pingResponse\.ok \|\| !ping\?\.capabilities\?\.checklist_ticktick_reset/.test(source), 'missing reset capability must block the flow')
  assert(/服务端尚未升级或重启，暂不能重置清单数据/.test(source), 'old server must receive an actionable upgrade message')
  assert(/if \(!previewResponse\.ok\) return alert/.test(source), 'failed preview must stop before confirmation')
  assert(source.indexOf('if (!previewResponse.ok)') < source.indexOf('requestChecklistResetConfirmation(counts'), 'confirmation must follow a successful preview only')
  assert(/RESET TICKTICK USER/.test(source) && !/window\.prompt/.test(source), 'Electron confirmation must use an in-app phrase input')
  assert(/previewResponse\.status === 401 \|\| previewResponse\.status === 403/.test(source), 'expired reset authentication must be identified')
  assert(/const session = await verifyActiveSession\(\)/.test(source), 'reset authentication must verify the active session before clearing it')
  assert(/if \(session === 'invalid'\)[\s\S]{0,180}await clearActiveSession\(\)/.test(source), 'only confirmed invalid sessions may return reset flow to login')
  assert(/resetChecklistStartDate\(settings\.checklist_sync_start_date\)/.test(source), 'the current start date must be safely retryable after a failed reset')
  assert(/syncNow\(\{ reason: 'checklist-start-date-reset' \}\)/.test(source), 'a successful reset must immediately consume local tombstones')
  assert(/服务端能力检查|重置预览|服务端确认|本地数据收敛/.test(source), 'reset failures must retain the actual failing stage')
  assert(/'X-Request-ID': requestId/.test(source), 'reset requests must share a trace id with the server')
  assert(/flow_start|preview_start|preview_ready|confirm_start|local_pull_start|flow_finish/.test(source), 'reset stages must emit structured diagnostics')
})
