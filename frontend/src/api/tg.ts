import request from './request'

export interface TgFile {
  href: string
  peer: number
  msg: number
  name: string
  size: number
  ext: string
  playable: boolean
}

export const tgAPI = {
  config: () => request.get('/tg/config') as unknown as
    Promise<{ data: any; tdl: { hasTdl: boolean; autoDir: string; target: string }; login: any; sessions: any[] }>,
  saveConfig: (patch: Record<string, any>) => request.post('/tg/config', patch),
  tdlStatus: () => request.get('/tg/tdl/status') as unknown as Promise<{ data: any }>,
  tdlDownload: () => request.post('/tg/tdl/download') as unknown as Promise<{ data: any }>,

  login: () => request.get('/tg/login') as unknown as Promise<{ data: any }>,
  detect: () => request.post('/tg/login/detect') as unknown as Promise<{ state: string }>,
  loginStart: (kind: string, phone = '', ns = '') =>
    request.post('/tg/login/start', { kind, phone, ns }) as unknown as Promise<{ data: any }>,
  loginInput: (value: string) => request.post('/tg/login/input', { value }),
  loginCancel: () => request.post('/tg/login/cancel'),

  chats: (refresh = false) => request.get('/tg/chats', { params: { refresh } }) as unknown as
    Promise<{ code: number; data: any[]; detail?: string }>,

  preview: (urls: string) => request.post('/tg/preview', { urls }) as unknown as
    Promise<{ data: { sid: string; dir: string; files: TgFile[] } }>,
  session: (sid: string) => request.get(`/tg/session/${sid}`) as unknown as
    Promise<{ data: { sid: string; state: string; files: TgFile[] } }>,
  stop: (sid: string) => request.post(`/tg/session/${sid}/stop`),
  keepalive: (sid: string) => request.post(`/tg/keepalive/${sid}`) as unknown as
    Promise<{ code: number; data: { sid: string; idle: number } }>,
  download: (sid: string, href: string, name = '', folder = '') =>
    request.post('/tg/download', { sid, href, name, folder }) as unknown as Promise<{ id: number; name: string }>,
  streamUrl: (sid: string, href: string) => `/api/tg/stream/${sid}/${href}`,
}
