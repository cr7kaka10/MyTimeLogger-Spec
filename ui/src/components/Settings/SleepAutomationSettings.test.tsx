import { renderToStaticMarkup } from 'react-dom/server'
import { canEnableSleepAutomation, SleepAutomationSettings, type SleepPermissions } from './SleepAutomationSettings'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const granted: SleepPermissions = { accessibility: true, notifications: true, media: true, battery: true }
const render = (consented: boolean, permissions = granted, status: any = { available: true, enabled: true, nextRunAt: '2026-10-02 08:40' }) => renderToStaticMarkup(<SleepAutomationSettings status={status} consented={consented} permissions={permissions} onConsent={() => {}} onToggle={() => {}} onAuthorize={() => {}} onTest={() => {}} onRetry={() => {}} onStop={() => {}} />)
const blocked = render(false, granted, { available: true, enabled: false })
assert(!canEnableSleepAutomation(false, granted) && /aria-label="睡眠自动化"[^>]*disabled/.test(blocked), 'consent must gate enablement')
assert(!/aria-label="睡眠自动化"[^>]*checked/.test(blocked), 'blocked automation must not remain checked')
assert(!canEnableSleepAutomation(true, { ...granted, accessibility: false }), 'every hard permission must be granted')
const waiting = render(true, { ...granted, accessibility: false })
assert(/aria-label="睡眠自动化"[^>]*checked/.test(waiting) && !/aria-label="睡眠自动化"[^>]*disabled/.test(waiting) && waiting.includes('已保留每日执行'), 'missing permission must preserve enabled intent and allow disable')
const missingPermission = render(true, { ...granted, accessibility: false }, { available: true, enabled: false })
assert(/aria-label="睡眠自动化"[^>]*disabled/.test(missingPermission) && missingPermission.includes('尚未授权：辅助功能控制'), 'missing permission must block first enable and name the blocker')
const ready = render(true)
assert(/aria-label="睡眠自动化"[^>]*checked/.test(ready), 'ready enabled automation must stay checked')
assert(/每天 08:40/.test(ready) && /2026-10-02 08:40/.test(ready), 'fixed schedule and next run must render')
for (const label of ['辅助功能控制', '通知提醒', '睡眠图片访问', '忽略电池优化']) assert(ready.includes(label), `${label} authorization entry must render`)
assert(ready.includes('保存睡眠图片并上传生成睡眠报告'), 'prominent disclosure must describe the data flow')
const history = render(true, granted, { available: true, enabled: true, stage: 'upload', reason: 'https://secret.example/token', history: Array.from({ length: 8 }, (_, index) => ({ stage: `stage_${index}`, result: 'failed', reason: index === 7 ? 'Bearer secret' : 'timeout' })) })
assert((history.match(/data-run=/g) || []).length === 7, 'history must show only seven runs')
assert(/立即测试/.test(history) && /重试/.test(history) && /停止/.test(history) && /手动保存睡眠图片/.test(history), 'diagnostic actions and manual fallback must render')
assert(!/secret\.example|Bearer secret/.test(history) && /已隐藏/.test(history), 'sensitive status content must be redacted')
console.log('sleep automation settings tests passed')
