const url = process.env.MTL_ANDROID_RELEASE_URL || ''
let parsed
try { parsed = new URL(url) } catch { throw new Error('Android Release URL is required') }
if (parsed.protocol !== 'https:' || /^(127\.0\.0\.1|localhost)$/i.test(parsed.hostname)) throw new Error('Android Release URL must use non-loopback HTTPS')
console.log(`Android Release URL preflight passed: ${parsed.origin}`)
