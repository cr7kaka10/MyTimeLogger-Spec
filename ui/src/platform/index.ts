export { getElectronApi, isElectron, type ElectronApi } from './electron'
export { platformFetch, type PlatformFetchResponse } from './fetch'
export { encryptString, decryptString } from './crypto'
export { MemoryCredentialView } from './credentials'
export { detectPlatformRuntime, type PlatformRuntime, type RuntimeHost } from './runtime'
export { createDeviceIdentityService } from './deviceIdentity'
export {
  TimerLeaseCommandJournal, createTimerLeaseMonitor, loadTimerLeaseJournal,
  persistTimerLeaseJournal, requireTimerLeaseCapability,
} from './timerLease'
export { createCapacitorAppLifecycleService, createCapacitorNetworkLifecycleService, createLifecycleService, type LifecycleSources } from './lifecycle'
export { createCapacitorRemindersService, createRemindersService, type ReminderBackend } from './reminders'
export { createNotificationService, type NativeNotificationPlugin } from './notifications'
export { createExternalBrowserService } from './externalBrowser'
export { shareTextFile } from './fileShare'
export type {
  BackNavigationService, DesktopCapabilities, DeviceIdentityService, DeviceRuntimeStateService,
  ExternalBrowserService, FileShareService, LifecycleEvent, LifecycleService,
  NativeHttpResponse, NativeHttpService, PlatformDatabaseService,
  RemindersService, NotificationService, NotificationMessage, NotificationChannel, NotificationRoute, SecureCredentialsService,
} from './services'
