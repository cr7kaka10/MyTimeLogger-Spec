import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { continueDiaryNumbering } from './SleepPage'

const source = readFileSync(fileURLToPath(new URL('./SleepPage.tsx', import.meta.url)), 'utf8')

if (source.includes('}, [textValue.length, title])')) {
  throw new Error('diary focus must not reset when text length changes during middle edits')
}
if (!source.includes('}, [title])')) {
  throw new Error('diary focus must initialize for each morning/evening modal instance')
}

const first = '1. 第一件事'
const continued = continueDiaryNumbering(first, first.length, first.length)
if (!continued || continued.value !== '1. 第一件事\n2. ' || continued.cursor !== continued.value.length) {
  throw new Error('Enter must insert the next number and place the cursor after it')
}

const middle = continueDiaryNumbering('1. 第一件事\n普通段落', 4, 4)
if (!middle || !middle.value.startsWith('1. 第\n2. ')) {
  throw new Error('numbering must honor the actual middle selection instead of moving to the end')
}

console.log('sleep diary cursor contracts passed')
