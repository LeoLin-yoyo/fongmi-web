import request from './request'

export interface DouyinMedia {
  token: string
  stream_path: string
  filename?: string
  path?: string
  index?: number
  playable?: boolean
}

export interface DouyinResult {
  aweme_id: string
  type: 'video' | 'images' | 'unknown'
  title: string
  author: string
  video: DouyinMedia | null
  cover: DouyinMedia | null
  music: DouyinMedia | null
  images: DouyinMedia[]
}

export const douyinAPI = {
  resolve: (text: string) => request.post('/douyin/resolve', { text }) as unknown as
    Promise<{ data: DouyinResult }>,
  download: (token: string, folder = '') =>
    request.post('/douyin/download', { token, folder }) as unknown as
      Promise<{ id: number; name: string }>,
  downloadAll: (tokens: string[], folder = '') =>
    request.post('/douyin/download_all', { tokens, folder }) as unknown as
      Promise<{ ids: number[]; count: number }>,
  streamUrl: (token: string) => `/api/douyin/stream/${token}`,
  config: () => request.get('/douyin/config') as unknown as
    Promise<{ data: { has_cookie: boolean; has_uifid: boolean; user_agent: string } }>,
  setConfig: (cookie: string, userAgent = '') =>
    request.post('/douyin/config', { cookie, user_agent: userAgent }) as unknown as
      Promise<{ data: { has_cookie: boolean; has_uifid: boolean } }>,
  verify: () => request.post('/douyin/verify', {}) as unknown as
    Promise<{ code: number; data: { ok: boolean; detail: string } }>,
}
