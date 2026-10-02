/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'flv.js' {
  const flvjs: any
  export default flvjs
}

declare module 'plyr' {
  const Plyr: any
  export default Plyr
}

interface Window {
  $message: import('naive-ui').MessageApi
}
