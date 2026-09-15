import { classifyAndroidSmoke } from './classify_android_smoke.mjs'

const secret = 'Bearer must-not-be-printed'
const result = classifyAndroidSmoke(
  `FATAL EXCEPTION\nduplicate column x\nCLEARTEXT communication not permitted\nSSLHandshakeException\n${secret}`,
  '{"url":"https://localhost/icons/atm/cat_1.png","status":200}\n{"url":"https://localhost/icons/atm/cat_2.png","status":404}',
)
const expected = { fatal: 1, cleartext: 1, ssl: 1, duplicateColumn: 1, atmSuccess: 1, atmFailure: 1 }
if (JSON.stringify(result) !== JSON.stringify(expected) || JSON.stringify(result).includes(secret)) throw new Error(JSON.stringify(result))
console.log('Android smoke classifier passed')
