import { createElement, Fragment, type ReactNode, useCallback, useEffect, useState } from 'react'

import { getDatabase, initDatabase, syncNow } from './db'
import { detectPlatformRuntime } from './platform'
import { createDeviceRuntimeStateService } from './platform/runtimeState'
import { installCapacitorKeyboard } from './platform/keyboard'
import { createCapacitorNativeHttpService, setNativeHttpTransport } from './platform/fetch'
import { createSecureCredentialsService, loadSecureCredentialView } from './platform/credentials'
import { createCapacitorRemindersService } from './platform/reminders'
import { setTimerRemindersService } from './platform/timerReminders'
import { setTimerDeviceRuntimeState } from './hooks/useTimer'
import { createCapacitorAppLifecycleService, createCapacitorNetworkLifecycleService, installAndroidSyncLifecycle, installAndroidTimerWidgetLifecycle } from './platform/lifecycle'
import { installNotificationRuntime } from './platform/notificationRuntime'
import { createSleepAutomationConfigSync } from './platform/sleepAutomation'

type BootstrapState = 'loading' | 'ready' | 'bootstrap_credentials_failed' | 'bootstrap_database_failed'
let removeKeyboardListeners = () => {}
let removeWidgetLifecycle = () => {}
let removeSyncLifecycle = () => {}
let removeSleepConfigSync = () => {}

export async function bootstrapApplication(loadCredentials: () => Promise<void> = async () => {}): Promise<void> {
  ;(globalThis as any).__MTL_EXTENDED_FOCUS_GROUPS__ = import.meta.env.VITE_EXTENDED_FOCUS_GROUPS !== 'false'
  const runtime = detectPlatformRuntime()
  removeKeyboardListeners(); removeKeyboardListeners = installCapacitorKeyboard(runtime)
  setNativeHttpTransport(createCapacitorNativeHttpService(runtime))
  setTimerRemindersService(createCapacitorRemindersService(runtime))
  const runtimeState = createDeviceRuntimeStateService(runtime)
  setTimerDeviceRuntimeState(runtimeState)
  removeWidgetLifecycle()
  removeSyncLifecycle(); removeSyncLifecycle = () => {}
  removeSleepConfigSync(); removeSleepConfigSync = () => {}
  const appLifecycle = createCapacitorAppLifecycleService(runtime)
  removeWidgetLifecycle = installAndroidTimerWidgetLifecycle(
    appLifecycle,
    () => {
      ;(window as any).MTLTimerWidget?.ready()
      window.dispatchEvent(new Event('mtl:timer-widget-snapshot-changed'))
    },
  )
  try {
    await loadSecureCredentialView(createSecureCredentialsService(runtime))
    await loadCredentials()
  } catch {
    throw new Error('bootstrap_credentials_failed')
  }
  try {
    await initDatabase()
    removeSyncLifecycle = installAndroidSyncLifecycle(
      appLifecycle,
      createCapacitorNetworkLifecycleService(runtime),
      reason => syncNow({ reason }),
    )
    await installNotificationRuntime(runtime, await getDatabase(), appLifecycle)
    if (runtime === 'capacitor-android') {
      const syncSleep = createSleepAutomationConfigSync()
      const pull = () => { void getDatabase().then(db => { const cfg = db.getAllConfig(); const active = cfg.active_environment || 'development'; const prefix = `env_${active}_`; const url = cfg[`${prefix}server_url`] || ''; const token = cfg[`${prefix}auth_token`] || ''; syncSleep(url && token ? { url, token } : null) }) }
      const timer = window.setInterval(pull, 1000)
      window.addEventListener('mtl:auth-cleared', pull); pull()
      removeSleepConfigSync = () => { window.clearInterval(timer); window.removeEventListener('mtl:auth-cleared', pull) }
    }
  } catch {
    throw new Error('bootstrap_database_failed')
  }
}

export function BootstrapGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BootstrapState>('loading')
  const bootstrap = useCallback(() => {
    setState('loading')
    void bootstrapApplication().then(() => setState('ready')).catch(error => {
      setState(error instanceof Error && error.message === 'bootstrap_credentials_failed'
        ? 'bootstrap_credentials_failed'
        : 'bootstrap_database_failed')
    })
  }, [])

  useEffect(() => { bootstrap() }, [bootstrap])
  if (state === 'ready') return createElement(Fragment, null, children)
  if (state === 'loading') return createElement('main', { className: 'theme-page min-h-screen' })
  return createElement('main', { className: 'theme-page min-h-screen flex flex-col items-center justify-center gap-3' },
    createElement('p', { role: 'alert' }, state),
    createElement('button', { type: 'button', onClick: bootstrap }, '重试'))
}
