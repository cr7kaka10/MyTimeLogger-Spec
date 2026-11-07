import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { build } from 'esbuild'
import { chromium } from 'playwright'

const root = resolve(import.meta.dirname, '..')
const bundle = await build({ stdin: {
  contents: `import React from 'react'; import { createRoot } from 'react-dom/client';
    import { RewardsPage } from './src/components/Rewards/RewardsPage';
    window.calls = [];
    createRoot(document.getElementById('app')).render(React.createElement(RewardsPage, {
      balance: 100, rewards: [{ id: 'spend', title: '消费', icon: '🛍️', price: 0,
        redemption_mode: 'custom_spend', inventory_mode: 'unlimited', fulfillment_mode: 'immediate' }],
      ledger: [], unclaimedRewards: [], buyReward: async (...args) => { window.calls.push(args) },
      addReward: async () => {}, updateReward: async () => {}, deleteReward: async () => {},
      claimRewards: async () => {}, activeSection: 'store', onSectionChange: () => {}, ledgerHook: {},
    }));`,
  resolveDir: root, loader: 'tsx', sourcefile: 'reward-steps.tsx',
}, bundle: true, write: false, platform: 'browser', format: 'iife' })

const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage()
  await page.setContent('<div id="app"></div>')
  await page.addScriptTag({ content: bundle.outputFiles[0].text })
  await page.getByRole('button', { name: '填写金额消费' }).click()
  await page.getByPlaceholder('消费金额（元）').fill('18.50')
  await page.getByRole('button', { name: '确认金额' }).click()
  assert.equal(await page.getByPlaceholder('消费金额（元）').count(), 0)
  await page.getByRole('button', { name: '确认提交' }).click()
  await page.getByText('请填写购买内容').waitFor()
  assert.equal((await page.evaluate(() => window.calls)).length, 0)
  await page.getByPlaceholder('具体买了什么（必填）').fill('午餐')
  await page.getByRole('button', { name: '确认提交' }).click()
  await page.waitForFunction(() => window.calls.length === 1)
  assert.deepEqual((await page.evaluate(() => window.calls))[0].slice(0, 3), ['spend', 18.5, '午餐'])
  console.log('reward purchase steps: passed')
} finally {
  await browser.close()
}
