export type StatusControlState = 'success' | 'failure' | 'idle'

const BASE = 'flex h-7 w-7 items-center justify-center rounded-full text-[11px] transition-all'

export function statusControlClass(state: StatusControlState): string {
  if (state === 'success') return `${BASE} bg-green-500 border border-green-600 text-white font-bold`
  if (state === 'failure') return `${BASE} bg-red-500 border border-red-600 text-white font-bold`
  return `${BASE} border border-gray-200 bg-gray-100 text-gray-300`
}
