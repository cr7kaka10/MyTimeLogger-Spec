import { classifyReleaseAsset } from './classify-release-assets.mjs'

const fixtures = [
  ['public/my_time_logger.db', '', 'database'],
  ['assets/legacy.wasm', '', 'deprecated-wasm'],
  ['assets/config.js', "const token = 'secret'", 'secret-pattern'],
  ['android/AndroidManifest.xml', '<application android:usesCleartextTraffic="true" />', 'debug-cleartext'],
  ['public/icons/unknown.png', Buffer.from([0]), 'license-unknown'],
  ['public/icons/atm/cat_1.png', Buffer.from([0]), 'required-atm-icon'],
  ['public/index.html', '<main />', 'allowed'],
]

for (const [source, content, expected] of fixtures) {
  const actual = classifyReleaseAsset(source, content)
  if (actual !== expected) throw new Error(`${source}: expected ${expected}, got ${actual}`)
}

console.log(`release asset classifier fixtures passed (${fixtures.length})`)
