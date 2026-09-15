const fs = require('fs');
const os = require('os');
const path = require('path');
const { _electron: electron } = require('../ui/node_modules/playwright');
const assert = (value, message) => { if (!value) throw new Error(message); };
const shutdown = async app => { await app.evaluate(({ app }) => { app.isQuitting = true; }); await app.close(); };
const removeTemp = async dir => {
  for (let attempt = 0; attempt < 10; attempt++) {
    try { fs.rmSync(dir, { recursive: true, force: true }); return; } catch (error) {
      if (attempt === 9) { console.warn(`isolated temp retained after EPERM: ${dir}`); return; }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
};
const waitForLog = async (dir, event) => {
  let seen = '';
  for (let attempt = 0; attempt < 200; attempt++) {
    const logDir = path.join(dir, 'logs');
    if (fs.existsSync(logDir)) { seen = fs.readdirSync(logDir).map(name => fs.readFileSync(path.join(logDir, name), 'utf8')).join(''); if (seen.includes(`"event":"${event}"`)) return; }
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error(`log event timeout: ${event}; seen=${seen.slice(-1200)}`);
};

async function main() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mtl-input-backlog-'));
  const errors = []; let app;
  try {
    app = await electron.launch({ executablePath: path.join(__dirname, 'node_modules/electron/dist/electron.exe'), args: [__dirname], env: { ...process.env, MTL_DATA_DIR: dataDir, MTL_LOAD_DEV_SERVER: '0', MTL_TIMER_INPUT_E2E: '1' } });
    const page = await app.firstWindow(); page.setDefaultTimeout(5000); page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = route.request().url(); let body = {};
      if (!/\/auth\/(?:login|me)(?:\?|$)/.test(url) && !/\/api\/sync\//.test(url)) return route.continue();
      if (url.endsWith('/auth/login')) body = { status: 'ok', token: 'isolated-server-token', username: 'isolated' };
      else if (url.includes('/auth/me')) body = { status: 'ok', username: 'isolated' };
      else if (url.includes('/api/sync/pull')) body = { status: 'ok', tables: {}, changes: [], from_version: 0, to_version: 0, server_time: '2026-07-11 16:00:00' };
      else if (url.includes('/api/sync/push')) body = { status: 'ok', operation_results: [], server_time: '2026-07-11 16:00:00' };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.waitForFunction(() => Boolean(window.electronAPI?.dbExecuteSync));
    await page.evaluate(() => {
      const api = window.electronAPI; const now = '2026-07-11 16:00:00';
      const set = (key, value) => api.dbExecuteSync('INSERT OR REPLACE INTO system_config(key,value,value_type,updated_at) VALUES(?,?,?,?)', [key, value, 'string', now]);
      set('active_environment', 'development'); set('env_development_server_url', 'http://127.0.0.1:8000'); set('env_development_username', 'isolated'); set('env_development_auth_token', 'isolated-server-token');
    });
    await page.reload(); await page.getByText('已找到保存的登录，点击登录进入。').waitFor({ timeout: 10000 });
    await page.getByRole('button', { name: '登录', exact: true }).last().evaluate(button => button.click());
    await page.getByRole('button', { name: '输入', exact: true }).waitFor({ timeout: 15000 }).catch(async () => { throw new Error(`timer page unavailable: ${(await page.locator('body').innerText()).slice(0, 500)}`); });
    const skip = page.getByRole('button', { name: '跳过', exact: true }); if (await skip.isVisible().catch(() => false)) await skip.click();
    await page.evaluate(() => {
      const api = window.electronAPI; const now = '2026-07-11 16:00:00';
      const inputId = api.dbQuerySync('SELECT id FROM categories WHERE name = ?', ['输入'])[0].id;
      const set = (key, value) => api.dbExecuteSync('INSERT OR REPLACE INTO system_config(key,value,value_type,updated_at) VALUES(?,?,?,?)', [key, value, 'string', now]);
      set('atimelogger_config', JSON.stringify({ enabled: true, username: '', password: '', owner_username: '', token: 'isolated-token', refresh_token: '', device_id: '', auth_required: false, type_map: JSON.stringify({ [inputId]: 'type-input' }), unmatched_categories: '[]' }));
      for (let index = 0; index < 16; index++) {
        const id = `backlog-${index}`;
        api.dbExecuteSync('INSERT INTO study_sessions(id,start_time,end_time,net_duration_minutes,date,category_id) VALUES(?,?,?,?,?,?)', [id, now, now, 1, '2026-07-11', inputId]);
        api.dbExecuteSync('INSERT INTO atimelogger_segments(local_session_id,local_segment_key,local_category_id,atimelogger_type_id,atimelogger_activity_id,remote_status,sync_state,created_at) VALUES(?,?,?,?,?,?,?,?)', [id, 'session', inputId, 'type-input', `remote-${index}`, 'stopped', 'pending_delete', now]);
      }
    });
    await page.waitForTimeout(100); await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await waitForLog(dataDir, 'remote.retry.batch.started'); await page.getByRole('button', { name: '输入', exact: true }).click();
    await page.getByRole('button', { name: '编辑计时备注' }).waitFor();
    const durations = [];
    for (let index = 0; index < 10; index++) {
      let started = Date.now(); await page.getByRole('button', { name: '编辑计时备注' }).click();
      const note = page.locator('input[placeholder="备注"]'); await note.waitFor(); await page.waitForFunction(() => document.activeElement?.getAttribute('placeholder') === '备注'); durations.push(Date.now() - started);
      await note.fill('中文备注'); await note.evaluate(input => input.setSelectionRange(1, 1)); assert(await note.evaluate(input => document.activeElement === input && input.selectionStart === 1), 'note supports focused middle editing');
      await page.getByRole('button', { name: '取消', exact: true }).click();
    }
    for (let index = 0; index < 10; index++) {
      const started = Date.now(); await page.getByRole('button', { name: '停止' }).click();
      const summary = page.locator('textarea'); await summary.waitFor(); await page.waitForFunction(() => document.activeElement?.tagName === 'TEXTAREA'); durations.push(Date.now() - started);
      await summary.fill('1. 中文原因'); await summary.evaluate(input => input.setSelectionRange(2, 2)); assert(await summary.evaluate(input => document.activeElement === input && input.selectionStart === 2), 'summary supports focused middle editing');
      await page.getByRole('button', { name: '取消', exact: true }).click(); await summary.waitFor({ state: 'hidden' });
    }
    assert(durations.every(ms => ms <= 500), `all focus durations must be <=500ms: ${durations.join(',')}`);
    console.log(`focus samples ready; maxFocusMs=${Math.max(...durations)}; samples=${durations.length}`);
    await page.waitForTimeout(1500); await shutdown(app); app = null;
    const text = fs.readdirSync(path.join(dataDir, 'logs')).filter(name => name.endsWith('.jsonl')).map(name => fs.readFileSync(path.join(dataDir, 'logs', name), 'utf8')).join('');
    const events = text.trim().split('\n').filter(Boolean).map(JSON.parse); const names = events.map(item => item.event);
    const firstBatch = names.indexOf('remote.retry.batch.started'); const live = names.indexOf('remote.start.queued'); const secondBatch = names.indexOf('remote.retry.batch.started', firstBatch + 1);
    assert(firstBatch >= 0 && live > firstBatch && (secondBatch < 0 || live < secondBatch), 'interactive start runs before the next maintenance batch');
    assert(events.filter(item => item.event === 'focus.verified').length >= 20, 'all note and summary focus attempts are verified');
    assert(errors.length === 0, `renderer errors: ${errors.join('; ')}`); console.log(`timer input backlog e2e passed; maxFocusMs=${Math.max(...durations)}; samples=${durations.length}`);
  } finally {
    if (app) await shutdown(app).catch(() => undefined);
    if (path.resolve(dataDir).startsWith(path.resolve(os.tmpdir()))) await removeTemp(dataDir);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
