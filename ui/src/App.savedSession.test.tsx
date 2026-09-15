import { resolveSavedSession } from './auth/sessionState'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
assert(resolveSavedSession('saved-token', 'checking').authenticated, 'saved Android token must enter the local workspace while checking')

const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const source = fs.readFileSync(new URL('./App.tsx', import.meta.url), 'utf8') as string
const settingsSource = fs.readFileSync(new URL('./hooks/useSettings.ts', import.meta.url), 'utf8') as string
assert(source.includes("detectPlatformRuntime() !== 'capacitor-android'"), 'automatic restoration must remain Android-only')
assert(source.includes('resolveSavedSession(settings.selectedEnvironmentProfile.authToken'), 'App must consume the saved active-profile token')
assert(source.includes('restoringAndroidProfile') && source.includes('!settings.profileReady'), 'Android must wait for account profile recovery before rendering the login page')
assert(source.includes('if (session.authenticated) setAuthenticated(true)'), 'saved session must enter the main interface')
assert(source.includes('session.clearToken'), 'only a confirmed invalid saved session may request token clearing')
assert(source.includes('settings.clearActiveSession().then(() => setAuthenticated(false))'), 'App must wait for secure token clearing before returning to login')
assert(source.includes("window.addEventListener('mtl:auth-challenge', challenge)"), 'sync authentication failures must trigger a challenge instead of immediate logout')
assert(source.includes('settings.verifyActiveSession().then(result =>'), 'Android must confirm a challenge through the identity endpoint')
assert(settingsSource.includes('/auth/logout'), 'manual Android sign-out must revoke the server session')
assert(settingsSource.includes('writeActiveAccountStorageKey') && settingsSource.includes('clearActiveAccountStorageKey'), 'Android must recover the account profile after login and remove only its pointer on logout')
assert(!/deleteDatabase|removeAccountStorage|mtl\.runtime\.timer\.logic\.snapshot/.test(settingsSource), 'authentication cleanup must not delete widget snapshots or account data')
assert(source.includes('initialAuthenticated') && source.includes('setInitialAuthenticated(true)'), 'account activation must preserve the authenticated session across remount')
assert(source.includes("detectPlatformRuntime() !== 'capacitor-android'"), 'PC authentication expiry must keep its existing path')
assert(resolveSavedSession('saved-token', 'network_failed').authenticated, 'network failure must retain the local Android workspace')
console.log('App saved session tests passed')
