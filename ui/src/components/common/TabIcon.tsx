export type TabIconName = 'timer' | 'timebook' | 'learning' | 'checklist' | 'exercise' | 'sleep' | 'settings'

const iconPaths: Record<TabIconName, string[]> = {
  timer: ['M9 2h6', 'M12 5a8 8 0 1 0 8 8', 'M12 9v4l3 2'],
  timebook: ['M4 4.5A3.5 3.5 0 0 1 7.5 4H12v16H7.5A3.5 3.5 0 0 0 4 20.5z', 'M20 4.5A3.5 3.5 0 0 0 16.5 4H12v16h4.5a3.5 3.5 0 0 1 3.5.5z'],
  learning: ['m3 8 9-5 9 5-9 5z', 'M7 10.5V15c2.8 2 7.2 2 10 0v-4.5', 'M21 8v6'],
  checklist: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'm3.5 6 1.5 1.5L7.5 5', 'm3.5 12 1.5 1.5 2.5-2.5', 'm3.5 18 1.5 1.5 2.5-2.5'],
  exercise: ['M6 8v8', 'M3 10v4', 'M18 8v8', 'M21 10v4', 'M6 12h12'],
  sleep: ['M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5z'],
  settings: ['M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z', 'M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2 3.46-.09-.03a1.7 1.7 0 0 0-1.8-.29l-.11.06a1.7 1.7 0 0 0-1 1.55V22h-4v-.31a1.7 1.7 0 0 0-1-1.55l-.11-.06a1.7 1.7 0 0 0-1.8.29l-.09.03-2-3.46.06-.06A1.7 1.7 0 0 0 6.2 15v-.12a1.7 1.7 0 0 0-1.34-1.59L4.8 13.27v-4l.06-.02A1.7 1.7 0 0 0 6.2 7.66v-.12a1.7 1.7 0 0 0-.34-1.88L5.8 5.6l2-3.46.09.03a1.7 1.7 0 0 0 1.8.29l.11-.06a1.7 1.7 0 0 0 1-1.55V.54h4v.31a1.7 1.7 0 0 0 1 1.55l.11.06a1.7 1.7 0 0 0 1.8-.29l.09-.03 2 3.46-.06.06a1.7 1.7 0 0 0-.34 1.88v.12a1.7 1.7 0 0 0 1.34 1.59l.06.02v4l-.06.02a1.7 1.7 0 0 0-1.34 1.59z'],
}

export function TabIcon({ name }: { name: TabIconName }) {
  return (
    <svg aria-hidden="true" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
      {iconPaths[name].map((path, index) => <path key={index} d={path} strokeLinecap="round" strokeLinejoin="round" />)}
    </svg>
  )
}
