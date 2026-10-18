import { createSleepAutomation, createSleepAutomationConfigSync } from './sleepAutomation'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const calls: string[] = []
const api = createSleepAutomation({ MTLSleepAutomation: {
  status: () => '{"enabled":true,"stage":"idle"}', enable: () => { calls.push('enable'); return true },
  disable: () => { calls.push('disable') }, test: () => { calls.push('test'); return true },
  cancel: () => { calls.push('cancel') }, configure: (url, token) => { calls.push(`${url}:${token}`); return true },
  authorize: permission => { calls.push(`authorize:${permission}`); return true }, clearConfiguration: () => { calls.push('clear') },
} })
assert(api.status().available && api.status().enabled, 'status must parse native JSON')
assert(api.enable().ok && api.disable().ok && api.test().ok && api.cancel().ok, 'actions must normalize success')
assert(api.configure('https://example.test', 'secret').ok && api.authorize('media').ok && api.clearConfiguration().ok, 'configuration actions must forward')
assert(calls.join(',') === 'enable,disable,test,cancel,https://example.test:secret,authorize:media,clear', 'all bridge actions must be forwarded')
assert(createSleepAutomation({}).enable().error === 'unavailable', 'web/electron must report unavailable')
const broken = createSleepAutomation({ MTLSleepAutomation: { status: () => '{', enable: () => { throw new Error() }, disable: () => {}, test: () => false, cancel: () => {}, configure: () => false, authorize: () => false, clearConfiguration: () => {} } })
assert(broken.status().error === 'native_error' && broken.enable().error === 'native_error', 'native exceptions must normalize')
assert(broken.test().error === 'rejected' && broken.configure('', '').error === 'rejected', 'native rejection must normalize')
const order: string[] = []
let configured = false
const sync = createSleepAutomationConfigSync(createSleepAutomation({ MTLSleepAutomation: {
  status: () => JSON.stringify({ enabled: true, configured }), enable: () => { order.push('enable'); return true }, disable: () => { order.push('disable') }, test: () => true,
  cancel: () => { order.push('cancel') }, configure: (url) => { configured = true; order.push(`configure:${url}`); return true }, authorize: () => true, clearConfiguration: () => { configured = false; order.push('clear') },
} }))
sync({ url: 'https://one.test', token: 'one' }); sync({ url: 'https://one.test', token: 'one' })
assert(order.join(',') === 'cancel,configure:https://one.test', 'login sync must preserve enabled intent and ignore healthy duplicates')
configured = false; sync({ url: 'https://one.test', token: 'one' })
assert(order.join(',').endsWith('cancel,configure:https://one.test'), 'same config must restore a missing native secret')
order.length = 0; sync(null)
assert(order.join(',') === 'cancel,disable,clear', 'logout alone must cancel, disable, and clear the token')
console.log('sleep automation bridge tests passed')
