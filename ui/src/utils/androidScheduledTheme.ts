const beijingClock = (now: Date) => Object.fromEntries(new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
}).formatToParts(now).filter(part => part.type !== 'literal').map(part => [part.type, Number(part.value)])) as Record<string, number>

export type AndroidThemeOverride = { theme: 'light' | 'dark'; expiresAt: number }

export const androidScheduledTheme = (now = new Date()): 'light' | 'dark' => {
  const { hour } = beijingClock(now)
  return hour >= 7 && hour < 22 ? 'light' : 'dark'
}

export const millisecondsUntilAndroidThemeBoundary = (now = new Date()) => {
  const { hour, minute, second } = beijingClock(now)
  const elapsed = hour * 3600 + minute * 60 + second
  const boundary = elapsed < 7 * 3600 ? 7 * 3600 : elapsed < 22 * 3600 ? 22 * 3600 : 31 * 3600
  return Math.max(1_000, (boundary - elapsed) * 1_000)
}

export const nextAndroidThemeBoundaryAt = (now = new Date()) => now.getTime() + millisecondsUntilAndroidThemeBoundary(now)

export const resolveAndroidTheme = (override: AndroidThemeOverride | null, now = new Date()) => {
  if (override && override.expiresAt > now.getTime()) return { theme: override.theme, usesOverride: true }
  return { theme: androidScheduledTheme(now), usesOverride: false }
}
