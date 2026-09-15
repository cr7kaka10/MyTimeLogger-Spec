import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const count = (text, pattern) => [...text.matchAll(pattern)].length

export const classifyAndroidSmoke = (logcat, cdp) => {
  const atmLines = cdp.split(/\r?\n/).filter(line => /\/icons\/atm\/[^\s"']+\.png/i.test(line))
  return {
    fatal: count(logcat, /FATAL EXCEPTION|AndroidRuntime[^\r\n]*FATAL/gi),
    cleartext: count(logcat, /CLEARTEXT communication[^\r\n]*not permitted|NetworkSecurityConfig/gi),
    ssl: count(logcat, /SSLHandshakeException|CERTIFICATE_VERIFY_FAILED|ERR_CERT/gi),
    duplicateColumn: count(logcat, /duplicate column/gi),
    atmSuccess: atmLines.filter(line => /(?:"status"\s*:\s*|\s)(?:2\d\d|3\d\d)(?:\D|$)/i.test(line)).length,
    atmFailure: atmLines.filter(line => /(?:"status"\s*:\s*|\s)(?:4\d\d|5\d\d)(?:\D|$)|404|failed|net::ERR/i.test(line)).length,
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [logcatPath, cdpPath] = process.argv.slice(2)
  if (!logcatPath || !cdpPath) throw new Error('Usage: node classify_android_smoke.mjs <logcat> <cdp>')
  console.log(JSON.stringify(classifyAndroidSmoke(readFileSync(logcatPath, 'utf8'), readFileSync(cdpPath, 'utf8'))))
}
