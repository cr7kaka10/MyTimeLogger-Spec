import { useEffect } from 'react'
import type { Category } from '../types'
import { getDatabase } from '../db'

export function useTimerEvents(
  setCategories: (cats: Category[]) => void,
  setBalance: (balance: number) => void
) {
  // 监听 balance-updated 事件来刷新余额
  useEffect(() => {
    const handleBalanceUpdate = () => {
      getDatabase().then(db => {
        setBalance(db.getBalance())
      })
    }
    window.addEventListener('balance-updated', handleBalanceUpdate)
    window.addEventListener('sync-pull-complete', handleBalanceUpdate)
    return () => {
      window.removeEventListener('balance-updated', handleBalanceUpdate)
      window.removeEventListener('sync-pull-complete', handleBalanceUpdate)
    }
  }, [setBalance])

  // 本地编辑和跨端 Pull 都会改变分类；两条路径必须刷新首页计时网格。
  useEffect(() => {
    const handleCategoriesUpdate = () => {
      getDatabase().then(db => {
        const cats = db.getCategories()
        setCategories(cats as Category[])
      })
    }
    window.addEventListener('categories-updated', handleCategoriesUpdate)
    window.addEventListener('sync-pull-complete', handleCategoriesUpdate)
    return () => {
      window.removeEventListener('categories-updated', handleCategoriesUpdate)
      window.removeEventListener('sync-pull-complete', handleCategoriesUpdate)
    }
  }, [setCategories])
}
