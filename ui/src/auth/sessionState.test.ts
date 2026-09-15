import { resolveActiveSessionVerification, resolveSavedSession, verificationFromStatus } from './sessionState'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
assert(resolveSavedSession('', 'checking').mode === 'login', 'missing token must show login')
assert(resolveSavedSession('saved', 'checking').authenticated, 'saved token must enter the local workspace while checking')
assert(resolveSavedSession('saved', verificationFromStatus(0)).authenticated, 'network failure must keep an offline session')
assert(resolveSavedSession('saved', verificationFromStatus(403)).authenticated, 'a non-identity 403 must not expire the session')
const expired = resolveSavedSession('saved', verificationFromStatus(401))
assert(!expired.authenticated && expired.clearToken && expired.mode === 'expired', 'only identity endpoint 401 may expire the session')
assert(resolveSavedSession('saved', verificationFromStatus(200)).mode === 'connected', '200 must confirm the session')
assert(resolveActiveSessionVerification(200, '7', 7) === 'valid', 'matching identity keeps the session')
assert(resolveActiveSessionVerification(200, '7', 8) === 'invalid', 'mismatched identity invalidates the session')
assert(resolveActiveSessionVerification(401, '7', null) === 'invalid', 'identity endpoint 401 invalidates the session')
assert(resolveActiveSessionVerification(403, '7', null) === 'unavailable', '403 does not prove the session is invalid')
assert(resolveActiveSessionVerification(503, '7', null) === 'unavailable', 'server errors keep the session')

const persistedToken = 'isolated-device-token'
assert(resolveSavedSession(persistedToken, 'checking').authenticated, 'a saved device session starts locally before verification')
assert(resolveSavedSession(persistedToken, 'network_failed').authenticated, 'offline restart keeps timer workspace available')
assert(resolveActiveSessionVerification(200, '7', 7) === 'valid', 'network recovery confirms the persisted session')
assert(!resolveSavedSession('', 'checking').authenticated, 'manual sign-out removes the token and returns to login')
console.log('saved session state tests passed')
