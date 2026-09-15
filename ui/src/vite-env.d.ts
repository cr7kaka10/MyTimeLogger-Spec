/// <reference types="vite/client" />

// 声明音频文件模块，让 TypeScript 识别静态 import
declare module '*.mp3' {
  const src: string
  export default src
}
