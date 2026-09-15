const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  dbQuery: (sql, params) => ipcRenderer.invoke('db-query', sql, params),
  dbExecute: (sql, params) => ipcRenderer.invoke('db-execute', sql, params),
  dbQuerySync: (sql, params) => ipcRenderer.sendSync('db-query-sync', sql, params),
  dbExecuteSync: (sql, params) => ipcRenderer.sendSync('db-execute-sync', sql, params),
  onShortcutTrigger: (callback) => {
    const subscription = (_event, type) => callback(_event, type);
    ipcRenderer.on('shortcut-trigger', subscription);
    return () => ipcRenderer.removeListener('shortcut-trigger', subscription);
  },
  writeTimerFlow: (event) => ipcRenderer.send('timer-flow-log', event),
  setTrayTooltip: (text) => ipcRenderer.send('set-tray-tooltip', text),
  minimizeWindow: () => ipcRenderer.send('window-minimize'),
  closeWindow: () => ipcRenderer.send('window-close'),
  ticktickFetch: (url, options) => ipcRenderer.invoke('ticktick-fetch', url, options),
  reloadHotkeys: () => ipcRenderer.invoke('reload-hotkeys'),
  reloadDb: () => ipcRenderer.invoke('db-reload'),
  activateAccountDatabase: (storageKey) => ipcRenderer.invoke('activate-account-database', storageKey),
  openExternalUrl: (url) => ipcRenderer.invoke('open-external-url', url),
  notifyDesktop: (message) => ipcRenderer.invoke('desktop-notify', message),
  onDesktopNotificationRoute: (callback) => { const listener = (_event, route) => callback(route); ipcRenderer.on('desktop-notification-route', listener); return () => ipcRenderer.removeListener('desktop-notification-route', listener); },
  encryptStringSync: (text) => ipcRenderer.sendSync('safe-storage-encrypt-sync', text),
  decryptStringSync: (encryptedText) => ipcRenderer.sendSync('safe-storage-decrypt-sync', encryptedText)
});
