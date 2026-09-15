import type { LedgerEntry } from '../Database'

export interface LedgerSummary {
  balance: number
  income: number
  expense: number
}

export interface RewardLedgerServicePort {
  now(): string
  localToday(): string
  get(sql: string, params?: any[]): Record<string, any> | undefined
  all(sql: string, params?: any[]): Record<string, any>[]
  run(sql: string, params?: any[]): void
  afterWrite(table: string, id: number | string): void
  getConfig(key: string): string | null
  setConfig(key: string, value: string, desc?: string): void
  getRecordById(table: string, id: number | string): Record<string, any> | undefined
}

export class RewardLedgerService {
  constructor(private readonly port: RewardLedgerServicePort) {}

  /**
   * 调用链路：UI Hook/奖励领取/任务结算 -> Database.addLedgerEntry 门面 -> RewardLedgerService -> reward_ledger SQL。
   * 写入边界：插入 reward_ledger 后通过 Database._afterWrite 维护 updated_at、pushed_at 和 wallet_balance。
   * 返回数据：返回新流水 id；若同一业务事件已存在，则返回既有 id，避免重复入账。
   */
  addLedgerEntry(amount: number, sourceType: string, sourceId?: number | string, description?: string, targetDate?: string): string {
    const now = this.port.now()
    const tDate = targetDate || this.port.localToday()
    const normalizedSourceId = sourceId !== undefined && sourceId !== null ? String(sourceId) : null
    const normalizedDescription = description ?? ''

    if (normalizedSourceId !== null && normalizedSourceId !== '') {
      const existing = this.port.get(
        `SELECT id FROM reward_ledger
         WHERE source_type = ? AND source_id = ? AND target_date = ? AND amount = ? AND description = ?`,
        [sourceType, normalizedSourceId, tDate, amount, normalizedDescription],
      )
      if (existing) {
        return existing.id as string
      }
    }

    const ledgerId = 'ledger_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    this.port.run(
      `INSERT INTO reward_ledger (id, amount, source_type, source_id, description, target_date, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [ledgerId, amount, sourceType, normalizedSourceId, normalizedDescription, tDate, now, now],
    )
    this.port.afterWrite('reward_ledger', ledgerId)
    return ledgerId
  }

  /**
   * 调用链路：流水界面删除 -> Database.deleteLedgerEntry 门面 -> RewardLedgerService -> reward_ledger/system_config SQL。
   * 写入边界：删除单条 reward_ledger，再反向调整 wallet_balance 快照。
   * 返回数据：返回布尔值表示删除入口已执行；不存在的 id 不抛错。
   */
  deleteLedgerEntry(id: number | string): boolean {
    const entry = this.port.getRecordById('reward_ledger', id)
    this.port.run('DELETE FROM reward_ledger WHERE id = ?', [id])
    this.port.afterWrite('reward_ledger', id)
    if (entry) {
      const configVal = this.port.getConfig('wallet_balance')
      const currentBalance = configVal !== null ? Number(configVal) : 0
      this.port.setConfig('wallet_balance', String(currentBalance - Number(entry.amount)))
    }
    return true
  }

  getLedgerSummary(): LedgerSummary {
    const row = this.port.get(
      `SELECT
         COALESCE(SUM(amount), 0) AS balance,
         COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
         COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expense
       FROM reward_ledger`,
    )
    return {
      balance: Number((row as any)?.balance ?? 0),
      income: Number((row as any)?.income ?? 0),
      expense: Number((row as any)?.expense ?? 0),
    }
  }

  /**
   * 调用链路：奖励页/背包/购买校验 -> Database.getBalance 门面 -> RewardLedgerService -> reward_ledger SQL。
   * 写入边界：reward_ledger 是事实来源，wallet_balance 仅作快照；读取时发现快照陈旧会自动修正。
   * 返回数据：返回当前金币余额 number。
   */
  getBalance(): number {
    const summary = this.getLedgerSummary()
    const configVal = this.port.getConfig('wallet_balance')
    const cachedBalance = configVal !== null ? Number(configVal) : NaN
    if (!Number.isFinite(cachedBalance) || Math.abs(cachedBalance - summary.balance) > 0.000001) {
      this.port.setConfig('wallet_balance', String(summary.balance))
    }
    return summary.balance
  }

  getLedger(limit = 30): LedgerEntry[] {
    return this.port.all('SELECT * FROM reward_ledger ORDER BY COALESCE(occurred_at, created_at) DESC LIMIT ?', [limit]) as LedgerEntry[]
  }

  getLedgerFull(limit = 50, offset = 0): LedgerEntry[] {
    return this.port.all(
      'SELECT * FROM reward_ledger ORDER BY COALESCE(occurred_at, created_at) DESC, id DESC LIMIT ? OFFSET ?',
      [limit, offset],
    ) as LedgerEntry[]
  }
}
