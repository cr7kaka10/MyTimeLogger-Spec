const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const source = fs.readFileSync(new URL('./LoginPage.tsx', import.meta.url), 'utf8') as string
const manifest = fs.readFileSync(new URL('../../../android/app/src/main/AndroidManifest.xml', import.meta.url), 'utf8') as string

assert(!source.includes('inputFocused'), 'login focus must not alter page layout state')
assert(!source.includes('pb-[55vh]'), 'login focus must not add fixed keyboard space')
assert(!source.includes("scrollIntoView({ block: 'start', behavior: 'smooth' })"), 'login focus must not scroll the desktop card')
assert(source.includes('pb-[env(safe-area-inset-bottom)]'), 'login page must keep only the platform safe-area padding')
assert(manifest.includes('android:windowSoftInputMode="adjustResize"'), 'Android activity must resize the WebView for the system keyboard')
console.log('LoginPage focus contract tests passed')
