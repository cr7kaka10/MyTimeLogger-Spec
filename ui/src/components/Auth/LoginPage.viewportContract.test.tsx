const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }

const fs = (globalThis as any).process.getBuiltinModule('node:fs')
const loginSource = fs.readFileSync(new URL('./LoginPage.tsx', import.meta.url), 'utf8') as string
const cssSource = fs.readFileSync(new URL('../../index.css', import.meta.url), 'utf8') as string
const nativeSource = fs.readFileSync(new URL('../../../android/app/src/main/java/com/mytimelogger/app/MainActivity.java', import.meta.url), 'utf8') as string

assert(loginSource.includes('w-full max-w-full') && loginSource.includes('overflow-x-hidden'), 'login page must constrain itself to the Android viewport')
assert(loginSource.includes('safe-area-inset-left') && loginSource.includes('safe-area-inset-right'), 'login page must consume horizontal safe-area insets')
assert(cssSource.includes('max-width: 100%') && cssSource.includes('overflow-x: hidden'), 'application root must prevent horizontal overflow')
assert(nativeSource.includes('setDecorFitsSystemWindows(getWindow(), true)'), 'Android WebView must receive a stable content viewport')
console.log('LoginPage viewport contract tests passed')
