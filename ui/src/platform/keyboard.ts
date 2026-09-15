import { Keyboard } from '@capacitor/keyboard'
import { detectPlatformRuntime, type PlatformRuntime } from './runtime'

type ListenerHandle = { remove(): void | Promise<void> }
type KeyboardPlugin = {
  show(): Promise<void>
  addListener(event: 'keyboardWillShow' | 'keyboardWillHide', listener: (info: { keyboardHeight?: number }) => void): ListenerHandle | Promise<ListenerHandle>
}
type KeyboardViewport = { setHeight(height: number | null): void; revealActiveInput(): void }
type FocusableInput = { value: string; focus(options?: FocusOptions): void; setSelectionRange(start: number, end: number): void }

const browserViewport = (): KeyboardViewport => ({
  setHeight(height) {
    if (height === null) document.documentElement.style.removeProperty('--keyboard-height')
    else document.documentElement.style.setProperty('--keyboard-height', `${height}px`)
  },
  revealActiveInput() { (document.activeElement as HTMLElement | null)?.scrollIntoView?.({ block: 'center' }) },
})

export function requestCapacitorInputFocus(
  target: FocusableInput,
  runtime: PlatformRuntime = detectPlatformRuntime(),
  plugin: Pick<KeyboardPlugin, 'show'> = Keyboard,
  requestFrame: (callback: () => void) => number = callback => window.requestAnimationFrame(callback),
): void {
  if (runtime !== 'capacitor-android') return
  requestFrame(() => {
    target.focus({ preventScroll: true })
    const cursor = target.value.length
    target.setSelectionRange(cursor, cursor)
    void plugin.show().catch(() => undefined)
  })
}

export function installCapacitorKeyboard(runtime: PlatformRuntime = detectPlatformRuntime(), plugin: KeyboardPlugin = Keyboard, viewport: KeyboardViewport = browserViewport()): () => void {
  if (runtime !== 'capacitor-android') return () => {}
  let closed = false; const removers: Array<() => void> = []
  const attach = (handle: ListenerHandle | Promise<ListenerHandle>) => {
    void Promise.resolve(handle).then(value => { if (closed) void value.remove(); else removers.push(() => { void value.remove() }) })
  }
  attach(plugin.addListener('keyboardWillShow', info => { if (!closed) { viewport.setHeight(info.keyboardHeight ?? 0); viewport.revealActiveInput() } }))
  attach(plugin.addListener('keyboardWillHide', () => { if (!closed) viewport.setHeight(null) }))
  return () => { closed = true; viewport.setHeight(null); for (const remove of removers.splice(0)) remove() }
}
