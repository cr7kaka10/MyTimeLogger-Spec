import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { androidScheduledTheme, millisecondsUntilAndroidThemeBoundary, nextAndroidThemeBoundaryAt, resolveAndroidTheme } from '../utils/androidScheduledTheme'

test('Android scheduled theme follows Beijing 07:00-22:00', () => {
  assert.equal(androidScheduledTheme(new Date('2026-08-24T22:59:00Z')), 'dark')
  assert.equal(androidScheduledTheme(new Date('2026-08-24T23:00:00Z')), 'light')
  assert.equal(androidScheduledTheme(new Date('2026-08-25T13:59:00Z')), 'light')
  assert.equal(androidScheduledTheme(new Date('2026-08-25T14:00:00Z')), 'dark')
  assert.equal(millisecondsUntilAndroidThemeBoundary(new Date('2026-08-24T22:59:00Z')), 60_000)
  assert.equal(millisecondsUntilAndroidThemeBoundary(new Date('2026-08-25T13:59:00Z')), 60_000)
})

test('scheduled theme is Android-only and does not persist a preference', () => {
  const source = readFileSync(new URL('./useSettings.ts', import.meta.url), 'utf8')
  const start = source.indexOf("useEffect(() => {\n    if (!profileReady || detectPlatformRuntime() !== 'capacitor-android')")
  const scheduler = source.slice(start, source.indexOf('  }, [profileReady, settings])', start))
  assert.match(scheduler, /document\.addEventListener\('visibilitychange'/)
  assert.match(scheduler, /window\.addEventListener\('focus'/)
  assert.doesNotMatch(scheduler, /updateSetting\(/)
})

test('manual Android theme override survives settings refresh until the next boundary', () => {
  const noon = new Date('2026-08-25T04:00:00Z')
  const expiresAt = nextAndroidThemeBoundaryAt(noon)
  assert.deepEqual(resolveAndroidTheme({ theme: 'dark', expiresAt }, noon), { theme: 'dark', usesOverride: true })
  assert.deepEqual(resolveAndroidTheme({ theme: 'dark', expiresAt }, new Date(expiresAt)), { theme: 'dark', usesOverride: false })

  const source = readFileSync(new URL('./useSettings.ts', import.meta.url), 'utf8')
  assert.match(source, /androidThemeOverrideRef\.current = \{ theme: nextTheme, expiresAt: nextAndroidThemeBoundaryAt\(\) \}/)
  assert.match(source, /resolveAndroidTheme\(androidThemeOverrideRef\.current, now\)/)
  assert.match(source, /if \(!resolved\.usesOverride\) androidThemeOverrideRef\.current = null/)
})
