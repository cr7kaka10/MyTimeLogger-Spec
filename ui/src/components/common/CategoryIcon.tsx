import { memo } from 'react'
import { parseAtmIconName } from '@core/CategoryIconKey'
import { ATM_ICON_GROUP_BY_NAME, ATM_ICON_NAMES, atmIconPath } from '../../assets/atmIconManifest'

export const CategoryIcon = memo(({ icon, color, className = 'h-6 w-6' }: { icon?: string; color?: string; className?: string }) => {
  const atmName = parseAtmIconName(icon, ATM_ICON_NAMES)
  if (!atmName) return <span className={`${className} inline-flex items-center justify-center leading-none`} style={{ color }}>◉</span>
  const path = atmIconPath(atmName)
  if (ATM_ICON_GROUP_BY_NAME.get(atmName) === 'premium') return <img src={path} className={`${className} object-contain`} alt="" aria-hidden="true" />
  return <span className={`${className} inline-block`} style={{ color, backgroundColor: 'currentColor', maskImage: `url(${path})`, WebkitMaskImage: `url(${path})`, maskPosition: 'center', WebkitMaskPosition: 'center', maskRepeat: 'no-repeat', WebkitMaskRepeat: 'no-repeat', maskSize: 'contain', WebkitMaskSize: 'contain' }} aria-hidden="true" />
})

CategoryIcon.displayName = 'CategoryIcon'
