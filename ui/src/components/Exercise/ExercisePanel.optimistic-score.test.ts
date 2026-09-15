import { readFileSync } from 'node:fs'

const panel = readFileSync(new URL('./ExercisePanel.tsx', import.meta.url), 'utf8')

if (!panel.includes('authoritative = Boolean(state?.score_rule_version)')) throw new Error('server score facts must be the only authoritative score source')
if (!panel.includes('const maxPoints = authoritative ? state?.max_points : previewMax')) throw new Error('local plan points must remain visible before Pull')
if (!panel.includes("earned_points: authoritative ? state?.earned_points : (state?.status === 1 ? maxPoints : 0)")) throw new Error('completed optimistic check-ins must not render as zero points')

console.log('exercise optimistic score contract passed')
