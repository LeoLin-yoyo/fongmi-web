import type { RouteLocationRaw } from 'vue-router'
import router from '@/router'
import { playOpenPrefs, type PlayOpenKind } from '@/utils/playPrefs'

/** 打开点播/本地视频的播放页：按设置决定新浏览器标签页或当前页跳转。
 *  新标签页时当前页保留浏览位置；弹窗被浏览器/插件拦截时 window.open 返回 null，
 *  此时回退为当前页跳转，保证点击必有响应 */
export function openPlayPage(location: RouteLocationRaw, kind: PlayOpenKind = 'vod') {
  if (!playOpenPrefs[kind]) {
    router.push(location)
    return
  }
  const win = window.open(router.resolve(location).href, '_blank')
  if (!win) router.push(location)
}
