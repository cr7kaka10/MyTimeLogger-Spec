export interface PlatformDatabaseService<TDatabase = unknown> {
  readonly available: boolean
  open(): Promise<TDatabase>
}

export interface NativeHttpResponse {
  status: number
  headers: Record<string, string>
  text: string
}

export interface NativeHttpService {
  readonly available: boolean
  request(url: string, options?: { method?: string; headers?: Record<string, string>; body?: string; timeoutMs?: number }): Promise<NativeHttpResponse>
  uploadMultipart?(url: string, file: File, options?: { fieldName?: string; headers?: Record<string, string>; timeoutMs?: number }): Promise<NativeHttpResponse>
}

export interface SecureCredentialsService {
  readonly available: boolean
  get(key: string): Promise<string | null>
  set(key: string, value: string): Promise<void>
  remove(key: string): Promise<void>
}

export interface DeviceRuntimeStateService {
  readonly available: boolean
  get(key: string): Promise<string | null>
  set(key: string, value: string): Promise<void>
  remove(key: string): Promise<void>
}

export interface DeviceIdentityService {
  readonly available: boolean
  get(): Promise<string | null>
  getOrCreate(): Promise<string | null>
}

export type LifecycleEvent = 'foreground' | 'background' | 'online' | 'offline'

export interface LifecycleService {
  readonly available: boolean
  subscribe(listener: (event: LifecycleEvent) => void): () => void
}

export interface RemindersService {
  readonly available: boolean
  schedule(id: string, atMs: number): Promise<void>
  cancel(id: string): Promise<void>
}

export type NotificationChannel = 'timer' | 'sleep' | 'achievements' | 'rewards' | 'account'
export type NotificationRoute = 'timer' | 'sleep' | 'goals' | 'rewards' | 'backpack' | 'settings'
export interface NotificationMessage {
  eventKey: string; channel: NotificationChannel; title: string; body: string
  route: NotificationRoute; atMs?: number
}
export interface NotificationService {
  readonly available: boolean
  initialize(): Promise<void>
  permissionStatus(): Promise<string>
  requestPermission(): Promise<string>
  notify(message: NotificationMessage): Promise<'delivered' | 'denied' | 'rejected' | 'unavailable'>
  schedule(message: NotificationMessage & { atMs: number }): Promise<'delivered' | 'denied' | 'rejected' | 'unavailable'>
  cancel(eventKey: string): Promise<void>
  subscribe(listener: (route: string) => void): Promise<() => void>
}

export interface ExternalBrowserService {
  readonly available: boolean
  open(url: string): Promise<void>
}

export interface FileShareService {
  readonly available: boolean
  share(path: string): Promise<void>
}

export interface BackNavigationService {
  readonly available: boolean
  subscribe(handler: () => boolean): () => void
}

export interface DesktopCapabilities {
  readonly windowControls: boolean
  readonly tray: boolean
  readonly globalHotkeys: boolean
}
