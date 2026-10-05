/** 判断当前浏览器是否移动终端（手机/平板）：基于 UA，用于隐藏仅桌面端可用的功能入口。
 *
 * 移动终端浏览器无法调起本机 exe（如 PotPlayer），外部播放器入口对其隐藏。
 * Windows 触屏笔记本等桌面设备 UA 不含 Mobile 标记，不受影响，仍可正常调用。
 */
const MOBILE_UA_RE = /Android|iPhone|iPad|iPod|Mobile|Windows Phone|webOS|BlackBerry|IEMobile|Opera Mini/i

export function isMobileDevice(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent || ''
  if (MOBILE_UA_RE.test(ua)) return true
  // iPadOS 13+ 默认请求桌面版网站，UA 呈 Macintosh；用触摸点数辅助识别
  return /Macintosh/i.test(ua) && (navigator.maxTouchPoints || 0) > 1
}
