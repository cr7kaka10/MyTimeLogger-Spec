export const DEFAULT_CATEGORY_ATM_ICONS: Record<string, string> = {
  输入: 'atm:cat_96', 输出: 'atm:cat_85', 副业生产: 'atm:cat_158', 副业营销: 'atm:fs_010',
  副业研发: 'atm:st_024', 吃饭: 'atm:ec_045', 家庭: 'atm:fam_021', 娱乐: 'atm:cat_116',
  车: 'atm:cat_205', 生活杂事: 'atm:hpcd_034', 运动: 'atm:sp_068', 松鼠病: 'atm:cat_79',
  状态切换: 'atm:cat_5', 睡觉: 'atm:fam_008', 拉屎: 'atm:hpcd_041',
}

export const LEGACY_CATEGORY_ICONS: Record<string, readonly string[]> = {
  输入: ['fa:book-open', '📖'], 输出: ['fa:trophy', '✒️'], 副业生产: ['fa:wrench', '🏭'],
  副业营销: ['mdi:sack', 'fa:bullhorn', '📢'], 副业研发: ['fa:flask', '💻'], 吃饭: ['fa:bowl-food', '🍽️'],
  家庭: ['mdi:human-male-female-child', 'fa:house', '🏠'], 娱乐: ['fa:gamepad', '🎮'], 车: ['fa:car', '🚗'],
  生活杂事: ['fa:shower', '☕'], 运动: ['mdi:weight-lifter', 'fa:dumbbell', '🏋️'], 松鼠病: ['fa:kit-medical', '🐿️'],
  状态切换: ['fa:shuffle', '🔄'], 睡觉: ['fa:bed', '🛏️'], 拉屎: ['fa:toilet', '🚽'],
}

const ATM_ICON_NAME = /^(?:(?:ico|cat|ec|fam|fs|hpcd|mi|rph|sp|st|tt)_[0-9]{1,3}|flat_[0-9]{3}|swift_colored_[a-z]+_[0-9]{3})$/

export const parseAtmIconName = (value: unknown, allowedNames?: ReadonlySet<string>): string | null => {
  if (typeof value !== 'string' || !value.startsWith('atm:')) return null
  const name = value.slice(4)
  if (!ATM_ICON_NAME.test(name) || (allowedNames && !allowedNames.has(name))) return null
  return name
}

export const isAtmIconKey = (value: unknown, allowedNames?: ReadonlySet<string>): value is string =>
  parseAtmIconName(value, allowedNames) !== null

export const rgbToHex = (r: number, g: number, b: number): string | null => {
  if (![r, g, b].every(value => Number.isInteger(value) && value >= 0 && value <= 255)) return null
  return `#${[r, g, b].map(value => value.toString(16).padStart(2, '0')).join('').toUpperCase()}`
}

export const hexToRgb = (hex: string): [number, number, number] | null => {
  const match = /^#([0-9A-F]{2})([0-9A-F]{2})([0-9A-F]{2})$/i.exec(hex.trim())
  return match ? [parseInt(match[1], 16), parseInt(match[2], 16), parseInt(match[3], 16)] : null
}
