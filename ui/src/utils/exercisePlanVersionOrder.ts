export function sortExercisePlanVersions<T extends { version: string }>(versions: T[]): T[] {
  return versions.map((value, index) => ({ value, index, number: /^v(\d+)$/i.exec(value.version)?.[1] }))
    .sort((a, b) => {
      if (a.number === undefined) return b.number === undefined ? a.index - b.index : 1
      if (b.number === undefined) return -1
      return Number(b.number) - Number(a.number) || a.index - b.index
    }).map(item => item.value)
}
