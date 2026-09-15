import { applySleepReportHeadingAnchors, extractSleepReportOutline } from './sleepReportOutline'

const markdown = '# 标题\n\n## 第二节\n```md\n### 忽略\n```\n| 列 | 值 |\n| --- | --- |\n#### 第四节'
const markdownOutline = extractSleepReportOutline(markdown, 'markdown')
if (markdownOutline.map(item => item.title).join('|') !== '标题|第二节|第四节') throw new Error('markdown headings must keep hierarchy and exclude code/table')
if (markdownOutline.map(item => item.level).join(',') !== '1,2,4') throw new Error('markdown heading levels missing')

const html = '<h1>标题</h1><pre><h2>忽略</h2></pre><table><h3>忽略</h3></table><h2>第二节</h2><h4>第四节</h4>'
const htmlOutline = extractSleepReportOutline(html, 'html')
if (htmlOutline.map(item => item.title).join('|') !== markdownOutline.map(item => item.title).join('|')) throw new Error('HTML and markdown outlines must agree')
if (!applySleepReportHeadingAnchors('<h1>标题</h1><h2>第二节</h2>', htmlOutline).includes(`id="${htmlOutline[0].anchor}"`)) throw new Error('headings must receive stable anchors')
if (extractSleepReportOutline('plain report without headings', 'markdown').length) throw new Error('plain report must have no outline')

console.log('sleep report outline contract passed')
