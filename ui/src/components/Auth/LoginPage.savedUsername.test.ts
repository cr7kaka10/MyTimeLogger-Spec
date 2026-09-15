import { resolveSavedUsername } from './LoginPage'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
assert(resolveSavedUsername('', 'saved-user', false) === 'saved-user', 'late saved username should hydrate an untouched field')
assert(resolveSavedUsername('initial', 'saved-user', false) === 'saved-user', 'a new saved username should replace an untouched default')
assert(resolveSavedUsername('typed-user', 'saved-user', true) === 'typed-user', 'late saved username must not overwrite user input')
assert(resolveSavedUsername('typed-user', '', true) === 'typed-user', 'credential clearing must not overwrite user input')
console.log('saved username timing tests passed')
