/**
 * Image URL helper - routes through proxy to avoid CORS
 * 传入 name 时，图片加载失败后端返回带片名的占位海报（T5-1）
 */
const FALLBACK = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 140%22%3E%3Crect fill=%22%23333%22 width=%22100%22 height=%22140%22/%3E%3C/svg%3E'

export function imgUrl(url: string | undefined | null, name?: string): string {
  if (!url) return FALLBACK
  if (url.startsWith('data:') || url.startsWith('/api/')) return url
  let proxyUrl = `/api/img/proxy?url=${encodeURIComponent(url)}`
  if (name) proxyUrl += `&name=${encodeURIComponent(name)}`
  return proxyUrl
}
