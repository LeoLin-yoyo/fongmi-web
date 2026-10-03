import type { RouteLocationRaw } from 'vue-router'
import router from '@/router'

/** 在新浏览器标签页打开 SPA 路由，当前页保留浏览位置。
 *  弹窗被浏览器/插件拦截时 window.open 返回 null，此时回退为当前页跳转，保证点击必有响应 */
export function openInNewTab(location: RouteLocationRaw) {
  const win = window.open(router.resolve(location).href, '_blank')
  if (!win) router.push(location)
}
