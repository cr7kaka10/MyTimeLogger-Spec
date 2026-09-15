const { app, BrowserWindow, ipcMain, Tray, Menu, Notification, globalShortcut, safeStorage, screen, shell, session } = require('electron');
const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');
const { accountDatabasePath, isolateSharedDatabases } = require('./account-storage');
const { createTimerFlowLogger } = require('./timer-flow-logger');
if (process.env.MTL_TIMER_INPUT_E2E === '1') require('./timer-input-slow-fetch.cjs');

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (app.isReady()) showMainWindow();
    else app.whenReady().then(showMainWindow);
  });
}

let mainWindow;
let tray;
let db;
const registeredHotkeys = { timer: null, minimize: null };
const TIMER_HOTKEY = 'Alt+C';
const VISIBILITY_HOTKEY = 'Alt+X';

// 打包后资源基础路径：app.isPackaged 时用 resourcesPath，开发时用项目相对路径
const resourceBase = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..');

// 打包后数据库存到用户 AppData，开发时存到 local_data
const dbDir = process.env.MTL_DATA_DIR ? path.resolve(process.env.MTL_DATA_DIR) : app.isPackaged
  ? path.join(app.getPath('userData'), 'local_data')
  : path.join(__dirname, 'local_data');
const legacyDbDir = path.join(__dirname, '../local_data');
const dbPath = path.join(dbDir, 'my_time_logger.db');
const legacyDbPath = path.join(legacyDbDir, 'my_time_logger.db');
const bootstrapDbPath = path.join(dbDir, 'bootstrap', 'unauthenticated.db');
const windowStatePath = path.join(dbDir, 'window_state.json');
const debugSql = process.env.MTL_DEBUG_SQL === '1' || process.env.MTL_DEBUG_SQL === 'true';
const TIMER_FLOW_PREFIX = '[timer-flow]';
const timerFlowLogger = createTimerFlowLogger({ baseDir: path.join(dbDir, 'logs') });
void timerFlowLogger.cleanup().catch(() => console.warn(TIMER_FLOW_PREFIX, { layer: 'ElectronMain', event: 'log.cleanup.failed', errorCode: 'timer-flow-cleanup-failed' }));

function createShortcutTraceId(source) {
  return `${source}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function sendStatusSwitchShortcut(source) {
  const payload = {
    type: 'status-switch',
    source,
    traceId: createShortcutTraceId(source),
    traceStep: 1
  };
  const flowEvent = {
    beijingTime: new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }).replace(' ', 'T') + '+08:00',
    step: 1,
    layer: 'ElectronMain',
    event: mainWindow ? 'shortcut.sent' : 'flow.failed',
    source,
    traceId: payload.traceId,
    hasMainWindow: Boolean(mainWindow),
    result: mainWindow ? 'dispatched' : 'failed',
    errorCode: mainWindow ? undefined : 'missing-main-window',
    failedStep: mainWindow ? undefined : 'shortcut.dispatch'
  };
  console.log(TIMER_FLOW_PREFIX, flowEvent);
  void timerFlowLogger.append(flowEvent).then(persisted => {
    if (!persisted.ok) console.warn(TIMER_FLOW_PREFIX, { layer: 'ElectronMain', event: 'log.write.failed', errorCode: persisted.errorCode });
  }).catch(() => undefined);
  if (mainWindow) {
    mainWindow.webContents.send('shortcut-trigger', payload);
  }
}

function ensureDesktopDataDir() {
  if (!fs.existsSync(dbDir)) {
    fs.mkdirSync(dbDir, { recursive: true });
  }
}

function openDatabase(databasePath) {
  if (db) db.close();
  fs.mkdirSync(path.dirname(databasePath), { recursive: true });
  db = new Database(databasePath);
  db.pragma('journal_mode = WAL');
  console.log('[Electron DB] connected to isolated cache');
}

function activateAccountDatabase(storageKey) {
  openDatabase(accountDatabasePath(dbDir, storageKey));
}

// 初始化数据库逻辑
async function initDatabase() {
  try {
    ensureDesktopDataDir();
    const moved = isolateSharedDatabases(dbDir, [dbPath, legacyDbPath]);
    if (moved.length) console.warn('[Electron DB] unknown shared cache isolated');
    openDatabase(bootstrapDbPath);
  } catch (err) {
    console.error('[Electron DB] Failed to open database:', err.message);
  }
}

function reloadDatabaseFromDisk() {
  console.log('[Electron DB] better-sqlite3 uses direct disk access. No explicit reload needed.');
}

// better-sqlite3 直接写入本地物理磁盘
function saveDatabase() {
  // Obsolete with better-sqlite3
}

// 执行 SQL Select 并返回扁平的对象数组
function dbQuery(sql, params = []) {
  try {
    const stmt = db.prepare(sql);
    return stmt.all(params);
  } catch (err) {
    console.error('[Electron DB] Query error:', err.message);
    return [];
  }
}

// 执行 SQL 写操作，并自动写回本地磁盘，同时返回 changes & lastInsertRowid
function dbExecute(sql, params = []) {
  if (debugSql) {
    console.log('[dbExecute] SQL:', sql, 'Params:', params);
  }

  try {
    if (params && params.length > 0) {
      const stmt = db.prepare(sql);
      const info = stmt.run(params);
      return {
        changes: info.changes,
        lastInsertRowid: info.lastInsertRowid
      };
    } else {
      // 执行无参数可能包含多条语句的脚本
      db.exec(sql);
      try {
        const row = db.prepare('SELECT last_insert_rowid() AS id, changes() AS chgs').get();
        return { changes: row.chgs || 0, lastInsertRowid: row.id || 0 };
      } catch(e) {
        return { changes: 0, lastInsertRowid: 0 };
      }
    }
  } catch (err) {
    const isExpected = err.message && (err.message.includes('duplicate column name') || err.message.includes('already exists') || err.message.includes('no such column'));
    if (!isExpected) {
      console.error('[Electron DB] Execute error:', err.message);
    }
    throw err;
  }
}

function getVisibleWindowBounds(savedX, savedY, width = 920, height = 720) {
  const numericX = Number(savedX);
  const numericY = Number(savedY);
  const hasSavedPosition = Number.isFinite(numericX) && Number.isFinite(numericY);
  const candidate = hasSavedPosition
    ? { x: numericX, y: numericY, width, height }
    : screen.getPrimaryDisplay().workArea;
  const display = screen.getDisplayMatching(candidate) || screen.getPrimaryDisplay();
  const area = display.workArea;
  const visibleWidth = Math.min(width, area.width);
  const visibleHeight = Math.min(height, area.height);
  const maxX = area.x + area.width - visibleWidth;
  const maxY = area.y + area.height - visibleHeight;

  if (!hasSavedPosition) {
    return {
      x: Math.round(area.x + (area.width - visibleWidth) / 2),
      y: Math.round(area.y + (area.height - visibleHeight) / 2),
      width,
      height
    };
  }

  return {
    x: Math.min(Math.max(numericX, area.x), maxX),
    y: Math.min(Math.max(numericY, area.y), maxY),
    width,
    height
  };
}

function ensureMainWindowVisible() {
  if (!mainWindow) return;
  const bounds = mainWindow.getBounds();
  const visibleBounds = getVisibleWindowBounds(bounds.x, bounds.y, bounds.width, bounds.height);
  if (bounds.x !== visibleBounds.x || bounds.y !== visibleBounds.y) {
    mainWindow.setBounds(visibleBounds);
  }
}

function showMainWindow() {
  if (!mainWindow) {
    createWindow();
  }
  if (!mainWindow) return;

  ensureMainWindowVisible();
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.show();
  mainWindow.focus();
  mainWindow.setAlwaysOnTop(true);
  mainWindow.setAlwaysOnTop(false);
  console.log(TIMER_FLOW_PREFIX, { layer: 'ElectronMain', event: 'window:show-main-window' });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showRendererError(window, title, details) {
  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(title)}</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
      background: #f6f7fb;
      color: #1f2937;
    }
    main {
      width: min(680px, calc(100vw - 48px));
      padding: 28px;
      border: 1px solid #d8dde8;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 20px 48px rgba(15, 23, 42, 0.14);
    }
    h1 { margin: 0 0 14px; font-size: 22px; }
    p { margin: 0 0 12px; line-height: 1.65; }
    code {
      display: block;
      padding: 12px;
      white-space: pre-wrap;
      word-break: break-all;
      background: #eef2f7;
      border-radius: 6px;
      font-family: Consolas, monospace;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <main>
    <h1>${escapeHtml(title)}</h1>
    <p>桌面端窗口已打开，但生产 UI 没有正常加载。请把下面的信息发给排查人员。</p>
    <code>${escapeHtml(details)}</code>
  </main>
</body>
</html>`;
  window.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html)).catch((err) => {
    console.error('[Electron] Failed to show renderer error page:', err.message);
  });
  showMainWindow();
}

function createWindow() {
  let x, y;
  try {
    if (fs.existsSync(windowStatePath)) {
      const state = JSON.parse(fs.readFileSync(windowStatePath, 'utf8'));
      x = state.x;
      y = state.y;
    }
  } catch (e) {
    console.error('[Electron] Failed to read window state:', e);
  }

  const initialBounds = getVisibleWindowBounds(x, y);

  mainWindow = new BrowserWindow({
    width: initialBounds.width,
    height: initialBounds.height,
    x: initialBounds.x,
    y: initialBounds.y,
    resizable: true,
    frame: false, // 无边框
    transparent: true, // 开启透明，允许 React 渲染毛玻璃特效
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false
    }
  });

  loadRenderer(mainWindow);
  mainWindow.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    const levels = ['debug', 'info', 'warn', 'error'];
    const label = levels[level] || String(level);
    console.log(`[Renderer:${label}] ${message} (${sourceId}:${line})`);
  });
  // mainWindow.webContents.openDevTools();

  // Handle downloads (e.g. from blob URLs or export buttons)
  session.defaultSession.on('will-download', (event, item, webContents) => {
    // Let electron handle it with the default save dialog
    // No preventDefault() here means it will prompt the user to save
  });

  // 拦截关闭按钮，关闭窗口时不退出程序，而是隐藏到系统托盘
  mainWindow.on('close', (event) => {
    try {
      ensureDesktopDataDir();
      const bounds = mainWindow.getBounds();
      fs.writeFileSync(windowStatePath, JSON.stringify({ x: bounds.x, y: bounds.y }));
      console.log('[Electron] Saved window state bounds:', bounds.x, bounds.y);
    } catch (err) {
      console.error('[Electron] Error saving window state:', err);
    }

    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
    return false;
  });

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

function loadRenderer(window) {
  const devUrl = process.env.MTL_DEV_SERVER_URL || 'http://127.0.0.1:5173';
  // 打包后 UI 资源在 resources/ui/dist 下，开发时在项目相对路径
  const distIndex = path.join(resourceBase, 'ui/dist/index.html');

  // 调用链路：Electron app ready -> createWindow -> loadRenderer。
  // 运行边界：开发态加载 Vite；生产/打包态加载 ui/dist，避免生产硬依赖 127.0.0.1:5173。
  if (!app.isPackaged && process.env.MTL_LOAD_DEV_SERVER !== '0') {
    window.loadURL(devUrl).catch((err) => {
      console.error(`[Electron] Failed to load dev server ${devUrl}:`, err.message);
    });
    return;
  }

  if (fs.existsSync(distIndex)) {
    window.webContents.once('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (isMainFrame === false) return;
      showRendererError(
        window,
        'MyTimeLogger UI 加载失败',
        `${errorCode}: ${errorDescription}\n${validatedURL || distIndex}`
      );
    });
    window.loadFile(distIndex).catch((err) => {
      console.error('[Electron] Failed to load packaged UI:', err.message);
      showRendererError(window, 'MyTimeLogger UI 加载失败', `${err.message}\n${distIndex}`);
    });
    return;
  }

  console.error('[Electron] Packaged UI not found:', distIndex);
  showRendererError(window, 'MyTimeLogger UI 文件缺失', distIndex);
}

function createTray() {
  // 打包后图标在 resources/assets/icons 下
  const iconPath = path.join(resourceBase, 'assets/icons/icon.ico');
  tray = new Tray(iconPath);

  const contextMenu = Menu.buildFromTemplate([
    { label: '显示主面板', click: () => { showMainWindow(); } },
    { label: '状态切换', click: () => { showMainWindow(); sendStatusSwitchShortcut('tray-menu'); } },
    { type: 'separator' },
    { label: '退出应用', click: () => { app.isQuitting = true; app.quit(); } }
  ]);

  tray.setToolTip('MyTimeLogger 时间记录器');

  // 单击托盘图标始终恢复并前置主窗口；隐藏由关闭按钮或 Alt+Z 承担
  tray.on('click', () => {
    showMainWindow();
  });

  // Windows 兼容：右键时显式弹出菜单，避免 setContextMenu 抢夺左键 click 事件
  tray.on('right-click', () => {
    tray.popUpContextMenu(contextMenu);
  });
}

function registerHotkeys() {
  const registerFixedHotkey = (name, candidate, callback) => {
    const previous = registeredHotkeys[name];
    if (candidate === previous) return { ok: true, key: candidate, activeKey: previous };
    if (!globalShortcut.register(candidate, callback)) return { ok: false, reason: 'unavailable', activeKey: previous };
    if (previous) globalShortcut.unregister(previous);
    registeredHotkeys[name] = candidate;
    return { ok: true, key: candidate, activeKey: candidate };
  };

  const timer = registerFixedHotkey('timer', TIMER_HOTKEY, () => {
      console.log(`[Electron Main] Global Shortcut ${TIMER_HOTKEY} triggered`);
      console.log(TIMER_FLOW_PREFIX, { layer: 'ElectronMain', event: 'shortcut:global-triggered', source: 'electron-global', key: TIMER_HOTKEY });
      if (mainWindow) {
        showMainWindow();
        sendStatusSwitchShortcut('electron-global');
      }
    });
  const minimize = registerFixedHotkey('minimize', VISIBILITY_HOTKEY, () => {
      console.log(`[Electron Main] Global Shortcut ${VISIBILITY_HOTKEY} triggered`);
      if (mainWindow) {
        if (mainWindow.isVisible()) {
          mainWindow.hide();
        } else {
          showMainWindow();
        }
      }
    });
  console.log('[Electron Main] Global hotkeys reloaded:', { timer, minimize });
  return { timer, minimize };
}

app.on('ready', async () => {
  // 1. 初始化数据库
  await initDatabase();

  // 2. 创建主窗口
  createWindow();

  // 3. 创建托盘
  createTray();

  // 4. 注册全局快捷键
  registerHotkeys();

  // 5. 绑定数据库查询执行 IPC
  ipcMain.handle('db-query', async (event, sql, params) => {
    return dbQuery(sql, params);
  });

  ipcMain.on('timer-flow-log', (_event, payload) => {
    if (!payload || typeof payload !== 'object') return;
    void timerFlowLogger.append(payload).then(persisted => {
      if (!persisted.ok) console.warn(TIMER_FLOW_PREFIX, { layer: 'ElectronMain', event: 'log.write.failed', errorCode: persisted.errorCode });
    }).catch(() => console.warn(TIMER_FLOW_PREFIX, { layer: 'ElectronMain', event: 'log.write.failed', errorCode: 'timer-flow-write-failed' }));
  });

  ipcMain.handle('db-execute', async (event, sql, params) => {
    return dbExecute(sql, params);
  });

  ipcMain.on('db-query-sync', (event, sql, params) => {
    try {
      event.returnValue = dbQuery(sql, params);
    } catch (err) {
      console.error('[Electron Main] db-query-sync error:', err);
      event.returnValue = [];
    }
  });

  ipcMain.on('db-execute-sync', (event, sql, params) => {
    try {
      event.returnValue = dbExecute(sql, params);
    } catch (err) {
      const isExpected = err.message && (err.message.includes('duplicate column name') || err.message.includes('already exists') || err.message.includes('no such column'));
      if (!isExpected) {
        console.error('[Electron Main] db-execute-sync error:', err);
      }
      event.returnValue = { changes: 0, lastInsertRowid: 0, error: err.message };
    }
  });

  ipcMain.handle('db-reload', () => {
    reloadDatabaseFromDisk();
    return true;
  });

  ipcMain.handle('activate-account-database', (_event, storageKey) => {
    try {
      activateAccountDatabase(String(storageKey || ''));
      return { ok: true };
    } catch (_error) {
      return { ok: false, error: 'account_database_activation_failed' };
    }
  });

  ipcMain.handle('open-external-url', async (_event, targetUrl) => {
    try {
      const parsed = new URL(String(targetUrl || ''));
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        return { ok: false, error: '只允许打开 http/https 链接' };
      }
      await shell.openExternal(parsed.toString());
      return { ok: true };
    } catch (err) {
      return { ok: false, error: err.message || '无法打开浏览器' };
    }
  });

  ipcMain.handle('desktop-notify', (_event, message = {}) => {
    const route = String(message.route || '');
    if (!['timer', 'sleep', 'goals', 'rewards', 'backpack', 'settings'].includes(route)) return { ok: false };
    const notification = new Notification({ title: String(message.title || 'MyTimeLogger'), body: String(message.body || '') });
    notification.on('click', () => { showMainWindow(); mainWindow?.webContents.send('desktop-notification-route', route); });
    notification.show(); return { ok: true };
  });

  ipcMain.on('safe-storage-encrypt-sync', (event, text) => {
    try {
      if (safeStorage.isEncryptionAvailable() && text) {
        const encrypted = safeStorage.encryptString(text);
        event.returnValue = 'ENC:' + encrypted.toString('base64');
      } else {
        event.returnValue = text;
      }
    } catch (err) {
      console.error('[Electron] safeStorage encrypt error:', err);
      event.returnValue = text;
    }
  });

  ipcMain.on('safe-storage-decrypt-sync', (event, encryptedText) => {
    try {
      if (safeStorage.isEncryptionAvailable() && encryptedText && encryptedText.startsWith('ENC:')) {
        const base64Text = encryptedText.substring(4);
        const encrypted = Buffer.from(base64Text, 'base64');
        const decrypted = safeStorage.decryptString(encrypted);
        event.returnValue = decrypted;
      } else {
        event.returnValue = encryptedText;
      }
    } catch (err) {
      console.error('[Electron] safeStorage decrypt error:', err);
      event.returnValue = encryptedText; // Fallback
    }
  });

  // 接收从渲染进程传来的修改托盘提示的通知
  ipcMain.on('set-tray-tooltip', (event, text) => {
    if (tray) tray.setToolTip(text);
  });

  // TickTick HTTP 代理 — 渲染进程受 CORS 限制，由主进程代理请求
  ipcMain.handle('ticktick-fetch', async (_event, url, options) => {
    try {
      const fetchOptions = {
        method: options?.method || 'GET',
        headers: options?.headers || {},
      };
      if (options?.body) {
        fetchOptions.body = options.body;
      }
      const resp = await fetch(url, fetchOptions);
      const body = await resp.text();
      return {
        status: resp.status,
        statusText: resp.statusText,
        body,
        ok: resp.ok,
      };
    } catch (err) {
      let requestPath = '';
      try { requestPath = new URL(url).pathname; } catch {}
      console.error('[ticktick-fetch] failed ' + JSON.stringify({
        method: options?.method || 'GET',
        path: requestPath,
        name: err?.name || 'Error',
        message: String(err?.message || '').slice(0, 160),
        causeCode: String(err?.cause?.code || '').slice(0, 80),
      }));
      return {
        status: 0,
        statusText: err.message || 'Network error',
        body: '',
        ok: false,
      };
    }
  });

  // 接收窗口控制 IPC 消息
  ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
  });

  ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close();
  });

  ipcMain.handle('reload-hotkeys', () => {
    console.log('[Electron Main] Reloading global hotkeys...');
    return registerHotkeys();
  });
});

app.on('will-quit', () => {
  void timerFlowLogger.flush().catch(() => undefined);
  // 解绑所有快捷键
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', function () {
  if (mainWindow === null) createWindow();
});
