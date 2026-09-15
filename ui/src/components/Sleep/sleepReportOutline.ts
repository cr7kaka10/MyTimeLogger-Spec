export type SleepReportOutlineItem = {
  level: number
  title: string
  anchor: string
}

function plainText(value: string): string {
  return value.replace(/<[^>]+>/g, '').replace(/[*_`]/g, '').replace(/&nbsp;/gi, ' ').replace(/\s+/g, ' ').trim()
}

function anchorFor(title: string, index: number): string {
  const slug = plainText(title).toLowerCase().replace(/[^\w\u4e00-\u9fff]+/g, '-').replace(/^-+|-+$/g, '')
  return `sleep-report-${slug || 'section'}-${index + 1}`
}

export function extractSleepReportOutline(source: string, format: 'markdown' | 'html'): SleepReportOutlineItem[] {
  const headings: Array<{ level: number; title: string }> = []
  if (format === 'html') {
    const safe = source.replace(/<(pre|code|table)\b[\s\S]*?<\/\1>/gi, '')
    const matcher = /<h([1-4])\b[^>]*>([\s\S]*?)<\/h\1>/gi
    let match: RegExpExecArray | null
    while ((match = matcher.exec(safe))) {
      const title = plainText(match[2])
      if (title) headings.push({ level: Number(match[1]), title })
    }
  } else {
    let inCodeBlock = false
    for (const line of source.split(/\r?\n/)) {
      const trimmed = line.trim()
      if (trimmed.startsWith('```')) { inCodeBlock = !inCodeBlock; continue }
      if (inCodeBlock || trimmed.startsWith('|')) continue
      const match = trimmed.match(/^(#{1,4})\s+(.+?)\s*#*\s*$/)
      if (match) {
        const title = plainText(match[2])
        if (title) headings.push({ level: match[1].length, title })
      }
    }
  }
  return headings.map((heading, index) => ({ ...heading, anchor: anchorFor(heading.title, index) }))
}

export function applySleepReportHeadingAnchors(html: string, outline: SleepReportOutlineItem[]): string {
  let index = 0
  return html.replace(/<h([1-4])\b([^>]*)>/gi, (tag, level, attrs) => {
    const item = outline[index]
    if (!item || item.level !== Number(level)) return tag
    index += 1
    return `<h${level}${attrs} id="${item.anchor}">`
  })
}
