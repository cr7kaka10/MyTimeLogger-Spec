import { useRef, useState } from 'react'
import type { Database } from '@models/Database'
import { getDatabase, syncNow } from '../db'

export const LOCAL_HABITS_UPDATED = 'local-habits-updated'

export function useLocalHabitMutation() {
  const running = useRef(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const run = async (write: (db: Database) => void): Promise<boolean> => {
    if (running.current) return false
    running.current = true
    setBusy(true); setMessage('')
    try {
      const db = await getDatabase()
      write(db)
      window.dispatchEvent(new Event(LOCAL_HABITS_UPDATED))
      setMessage('已保存到本机，正在同步…')
      try {
        const result = await syncNow({ reason: 'local-habit-management' })
        setMessage(result.ok ? '已保存并同步' : '已保存到本机，待同步；请检查网络后重试同步')
      } catch {
        setMessage('已保存到本机，待同步；请检查网络后重试同步')
      }
      return true
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存失败，请重试')
      return false
    } finally {
      running.current = false; setBusy(false)
    }
  }
  return { run, busy, message }
}
