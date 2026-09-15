const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const source = fs.readFileSync(new URL('./MainLayout.tsx', import.meta.url), 'utf8') as string
const padding = source.match(/mobileQuickActionsTopPadding = '([^']+)'/)?.[1] ?? ''
assert(padding.includes('env(safe-area-inset-top, 0px)'), 'top inset must use the system safe-area with a zero fallback')
assert(padding.includes('+ 0.5rem'), 'zero-inset screens must retain the base top spacing')
assert(!/\b(?:24|32|44|48)px\b/.test(padding), 'safe-area must not use device-specific pixels')
assert(source.includes('h-screen h-[100dvh]') && source.includes('overflow-hidden'), 'layout must constrain scrolling to the content region')
assert(source.includes('min-h-0 min-w-0 flex-1 overflow-y-auto'), 'main content must be the only vertical scroll container')
assert(source.includes('pb-[calc(4rem+env(safe-area-inset-bottom,0px))]'), 'main content must reserve the fixed tab height and bottom inset')
assert(source.includes('z-50 flex shrink-0 justify-end px-5'), 'mobile quick actions must stay outside the content scroll region')
const mobileStart = source.indexOf("!isElectron() && activeTab !== 'settings'")
const desktopStart = source.indexOf('desktopCapabilities.windowControls')
assert(mobileStart > desktopStart, 'safe-area wrapper must stay in the non-Electron branch')
assert(source.slice(mobileStart).includes('mobileQuickActionsTopPadding'), 'mobile quick actions must apply the safe-area padding')
assert(source.includes("style={{ WebkitAppRegion: 'drag' } as any}"), 'titlebar must retain a draggable brand and empty area')
assert(source.includes("const noDrag = { WebkitAppRegion: 'no-drag' } as any"), 'titlebar controls must define no-drag semantics')
assert(source.includes('className="flex items-center gap-1" style={noDrag}'), 'titlebar controls container must opt out of dragging')
assert(source.includes('onClick={handleMinimize}\n              style={noDrag}'), 'minimize control must be explicitly no-drag')
assert(source.includes('onClick={handleClose}\n              style={noDrag}'), 'close control must be explicitly no-drag')
console.log('MainLayout safe-area tests passed')
