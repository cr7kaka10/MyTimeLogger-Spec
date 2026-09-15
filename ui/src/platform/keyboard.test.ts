import { installCapacitorKeyboard } from './keyboard'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const listeners: Record<string, (info: { keyboardHeight?: number }) => void> = {}; let removed = 0
const plugin = { addListener: (event: string, listener: (info: { keyboardHeight?: number }) => void) => { listeners[event] = listener; return { remove: () => { removed++ } } } }
const heights: Array<number | null> = []; let revealed = 0
const viewport = { setHeight: (height: number | null) => { heights.push(height) }, revealActiveInput: () => { revealed++ } }
const dispose = installCapacitorKeyboard('capacitor-android', plugin as any, viewport)
listeners.keyboardWillShow({ keyboardHeight: 280 }); listeners.keyboardWillHide({}); await Promise.resolve(); dispose()
assert(heights.join(',') === '280,,', 'keyboard show/hide and disposal should reset viewport height')
assert(revealed === 1 && removed === 2, 'show should reveal input and disposal should remove both listeners')
listeners.keyboardWillShow({ keyboardHeight: 300 })
assert(revealed === 1, 'disposed listener callbacks must have no effect')
assert(installCapacitorKeyboard('web', plugin as any, viewport) instanceof Function, 'Web should return a no-op cleanup')
let focused = 0; let selected = ''; let shown = 0; let frame: (() => void) | undefined
const input = { value: '72.5', focus: () => { focused++ }, setSelectionRange: (start: number, end: number) => { selected = `${start}:${end}` } }
const { requestCapacitorInputFocus } = await import('./keyboard')
requestCapacitorInputFocus(input, 'capacitor-android', { show: async () => { shown++ } }, callback => { frame = callback; return 1 })
assert(focused === 0 && shown === 0, 'Android input focus must wait for the native touch frame')
frame?.(); await Promise.resolve()
assert(focused === 1 && selected === '4:4' && shown === 1, 'Android touch must focus, place cursor and request the IME')
requestCapacitorInputFocus(input, 'web', { show: async () => { shown++ } }, callback => { frame = callback; return 1 })
assert(shown === 1, 'Web input focus must not invoke the Capacitor keyboard')
console.log('platform keyboard tests passed')
