import { chromium } from 'playwright'

const browser = await chromium.launch({
  headless: true,
  executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
})
try {
  const page = await browser.newPage()
  await page.goto('http://127.0.0.1:5173/visual-tests/backpack-refresh.html')
  await page.locator('button[title="开发环境测试卡"]').waitFor()
  await page.evaluate(() => { window.__backpackCard = document.querySelector('button[title="开发环境测试卡"]') })
  await page.locator('#begin-refresh').click()
  const refreshing = await page.evaluate(() => ({
    sameCard: window.__backpackCard === document.querySelector('button[title="开发环境测试卡"]'),
    status: document.body.innerText.includes('正在刷新'),
    skeleton: Boolean(document.querySelector('.animate-pulse')),
  }))
  await page.locator('#fail-refresh').click()
  const failed = await page.evaluate(() => ({
    sameCard: window.__backpackCard === document.querySelector('button[title="开发环境测试卡"]'),
    alert: document.body.innerText.includes('保留上次成功数据'),
  }))
  if (!refreshing.sameCard || !refreshing.status || refreshing.skeleton || !failed.sameCard || !failed.alert) {
    throw new Error(JSON.stringify({ refreshing, failed }))
  }
  await page.getByRole('button', { name: '已使用', exact: true }).click()
  await page.locator('button[title="开发环境已使用卡"]').waitFor()
  if (await page.locator('button[title="开发环境测试卡"]').count()) throw new Error('used filter still shows available card')
  console.log('backpack visual refresh passed:', JSON.stringify({ refreshing, failed }))
} finally {
  await browser.close()
}
