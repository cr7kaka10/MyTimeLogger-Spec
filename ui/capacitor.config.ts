import type { CapacitorConfig } from '@capacitor/cli'

// 2026-07-14（北京时间）依赖审计：Capacitor/官方插件均为 MIT；
// secure-storage 8.0.0 为 MIT，Android 使用 KeyStore + AES-GCM。
// Native HTTP 由 @capacitor/core 8.4.1 内置；精确版本见 package.json。
const config: CapacitorConfig = {
  appId: 'com.mytimelogger.app',
  appName: 'MyTimeLogger',
  webDir: 'dist',
  plugins: {
    StatusBar: { overlaysWebView: false, backgroundColor: '#ffffff' },
  },
}

export default config
