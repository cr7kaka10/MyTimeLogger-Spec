import { clearActiveAccountStorageKey, createSecureCredentialsService, credentialView, loadScopedCredentialView, loadSecureCredentialView, MemoryCredentialView, readActiveAccountStorageKey, scopedCredentialKey, setSecureCredential, writeActiveAccountStorageKey } from './credentials'

const view = new MemoryCredentialView()
await view.load({ token: 'secret', empty: null })
if (view.get('token') !== 'secret' || view.get('empty') !== null) throw new Error('credential view failed')

const stored = new Map<string, string>()
const storage = {
  getItem: async (key: string) => stored.get(key) ?? null,
  setItem: async (key: string, value: string) => { stored.set(key, value) },
  removeItem: async (key: string) => { stored.delete(key) },
}
const secure = createSecureCredentialsService('capacitor-android', storage as any)
await secure.set('atimelogger_token', 'first'); await secure.set('atimelogger_token', 'updated')
if (await secure.get('atimelogger_token') !== 'updated' || [...stored.keys()].join(',') !== 'mtl.credential.atimelogger_token') throw new Error('secure credential write/update failed')
await secure.remove('atimelogger_token')
if (await secure.get('atimelogger_token') !== null || stored.size !== 0) throw new Error('secure credential delete failed')
const web = createSecureCredentialsService('web', storage as any); await web.set('token', 'fallback')
if (web.available || stored.size !== 0) throw new Error('Web must not fall back to insecure storage')
await loadSecureCredentialView(secure)
await setSecureCredential('env_development_auth_token', 'runtime-token')
if (credentialView.get('env_development_auth_token') !== 'runtime-token' || stored.get('mtl.credential.env_development_auth_token') !== 'runtime-token') throw new Error('runtime credential write must update memory and secure storage')
await setSecureCredential('env_development_auth_token', '')
if (credentialView.get('env_development_auth_token') !== null || stored.has('mtl.credential.env_development_auth_token')) throw new Error('runtime credential delete failed')
await writeActiveAccountStorageKey('acct-ABCDEF0123456789ABCDEF0123456789')
if (await readActiveAccountStorageKey() !== 'acct-abcdef0123456789abcdef0123456789') throw new Error('active account pointer must be normalized in secure storage')
let malformedPointerRejected = false
try { await writeActiveAccountStorageKey('other-account') } catch { malformedPointerRejected = true }
if (!malformedPointerRejected || stored.has('mtl.credential.active_account_storage_key') === false) throw new Error('malformed account pointer must not replace the saved pointer')
await clearActiveAccountStorageKey()
if (await readActiveAccountStorageKey() !== null || stored.has('mtl.credential.active_account_storage_key')) throw new Error('logout must remove only the active account pointer')
const accountA = scopedCredentialKey('acct-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'ai_text_api_key')
const accountB = scopedCredentialKey('acct-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'ai_text_api_key')
await setSecureCredential(accountA, 'a-secret'); await setSecureCredential(accountB, 'b-secret')
await loadScopedCredentialView('acct-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')
if (credentialView.get(accountB) !== 'b-secret' || credentialView.get(accountA) !== 'a-secret' || accountA === accountB) throw new Error('account credentials must remain namespaced')
console.log('credential view tests passed')
