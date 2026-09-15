export interface HabitServicePort {
  all(sql: string, params?: any[]): Record<string, any>[]
  run(sql: string, params?: any[]): void
  getConfig(key: string): string | null
  setConfig(key: string, value: string, desc?: string): void
}

export class HabitService {
  constructor(private readonly port: HabitServicePort) {}

  /**
   * 调用链路：HabitsPage/useHabits -> Database.toggleCheckin 门面 -> HabitService -> reward_ledger SQL。
   * 写入边界：只删除同一 habit_id、同一 target_date 的习惯奖励/惩罚流水，并同步修正 wallet_balance 快照。
   * 返回数据：返回被删除流水数量，便于后续测试和问题定位。
   */
  removeLedgerForCancelledCheckin(habitId: string | number, targetDate: string): number {
    const rows = this.port.all(
      `SELECT id, amount FROM reward_ledger
       WHERE source_type IN ('habit_checkin', 'habit_fail') AND source_id = ? AND target_date = ?`,
      [String(habitId), targetDate],
    )
    if (rows.length === 0) {
      return 0
    }

    const total = rows.reduce((sum, row) => sum + Number(row.amount || 0), 0)
    this.port.run(
      `DELETE FROM reward_ledger
       WHERE source_type IN ('habit_checkin', 'habit_fail') AND source_id = ? AND target_date = ?`,
      [String(habitId), targetDate],
    )

    const configVal = this.port.getConfig('wallet_balance')
    const currentBalance = configVal !== null ? Number(configVal) : 0
    this.port.setConfig('wallet_balance', String(currentBalance - total))
    return rows.length
  }
}
