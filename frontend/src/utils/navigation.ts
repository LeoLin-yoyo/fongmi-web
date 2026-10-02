import type { RouteLocationRaw } from 'vue-router'
import router from '@/router'

/** 在新浏览器标签页打开 SPA 路由，当前页保留浏览位置 */
export function openInNewTab(location: RouteLocationRaw) {
  window.open(router.resolve(location).href, '_blank')
}
