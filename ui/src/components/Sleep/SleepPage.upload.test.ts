const fs = (globalThis as any).process.getBuiltinModule('node:fs')

const page = fs.readFileSync(new URL('./SleepPage.tsx', import.meta.url), 'utf8') as string
const hook = fs.readFileSync(new URL('../../hooks/useSleep.ts', import.meta.url), 'utf8') as string

if (!page.includes('onPickImage?: (file: File) => Promise<void>')) throw new Error('picker callback must expose upload completion')
if (!page.includes('onChange={async event =>')) throw new Error('picker change handler must await upload')
const upload = page.indexOf('await onPickImage?.(file)')
const clear = page.indexOf("input.value = ''", upload)
if (upload < 0 || clear < upload || !page.slice(upload, clear).includes('finally')) {
  throw new Error('input must clear in finally after upload settles')
}
if (!hook.includes('pickImage: (file: File) => Promise<void>')) throw new Error('sleep hook must preserve async picker contract')
if (!page.includes('if (!file) return')) throw new Error('cancelled selection must not upload')

console.log('sleep picker upload contract passed')
