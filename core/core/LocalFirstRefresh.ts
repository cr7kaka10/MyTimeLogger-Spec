export async function runLocalFirstRefresh(loadLocal: () => Promise<void>, sync: () => Promise<void>) {
  await loadLocal()
  try {
    await sync()
    return ''
  } catch (error: any) {
    return error?.message || '增量同步失败'
  } finally {
    await loadLocal()
  }
}
