const targets = await (await fetch('http://127.0.0.1:9222/json')).json()
const target = targets.find(item => item.url === 'https://localhost/')
if (!target) throw new Error('MyTimeLogger WebView target not found')
const socket = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})
let nextId = 0
const pending = new Map()
socket.addEventListener('message', event => {
  const reply = JSON.parse(event.data)
  if (!reply.id || !pending.has(reply.id)) return
  const { resolve, reject } = pending.get(reply.id)
  pending.delete(reply.id)
  reply.error ? reject(new Error(reply.error.message)) : resolve(reply.result)
})
const evaluate = async expression => {
  const id = ++nextId
  const result = await new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    socket.send(JSON.stringify({ id, method: 'Runtime.evaluate', params: { expression, returnByValue: true } }))
  })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
  return result.result.value
}
try {
  const before = await evaluate(`(() => {
    const card = document.querySelector('button[title="开发环境背包验收卡"]')
    window.__backpackCard = card
    return { card: !!card, skeleton: !!document.querySelector('.animate-pulse') }
  })()`)
  if (!before.card || before.skeleton) throw new Error(`Backpack not ready: ${JSON.stringify(before)}`)
  await evaluate(`window.dispatchEvent(new Event('balance-updated'))`)
  await new Promise(resolve => setTimeout(resolve, 500))
  const after = await evaluate(`({
    card: !!document.querySelector('button[title="开发环境背包验收卡"]'),
    sameCard: window.__backpackCard === document.querySelector('button[title="开发环境背包验收卡"]'),
    skeleton: !!document.querySelector('.animate-pulse')
  })`)
  if (!after.card || !after.sameCard || after.skeleton) throw new Error(`Backpack refresh failed: ${JSON.stringify(after)}`)
  console.log(JSON.stringify({ before, after }))
} finally {
  socket.close()
}
