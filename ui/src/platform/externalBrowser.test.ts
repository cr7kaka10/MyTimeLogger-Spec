import { createExternalBrowserService } from './externalBrowser'

const assert = (value: unknown, message: string) => { if (!value) throw new Error(message) }
const opened: string[] = []
const browser = { open: async ({ url }: { url: string }) => { opened.push(url) } }
const service = createExternalBrowserService('capacitor-android', browser)
await service.open('https://example.com/help')
assert(service.available && opened.join(',') === 'https://example.com/help', 'Android links should use Capacitor Browser')
assert(!createExternalBrowserService('electron', browser).available, 'Electron without preload must not use Capacitor Browser')
console.log('platform external browser tests passed')
