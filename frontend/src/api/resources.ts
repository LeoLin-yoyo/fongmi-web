import request from './request'

export interface ResourceEntry {
  id: number
  kind: 'tg' | 'pan' | string
  site_key: string
  name: string
  size: number
  payload: any
}

export const resourceAPI = {
  stats: () => request.get('/resources/stats') as unknown as
    Promise<{ data: { site_key: string; site_name: string; count: number }[] }>,
  indexTg: (peer: string, limit = 200) =>
    request.post('/resources/index/tg', { peer, limit }) as unknown as Promise<{ data: any }>,
  indexPan: (payload: { platform: string; share_id: string; passcode?: string; recursive?: boolean; max_files?: number }) =>
    request.post('/resources/index/pan', payload) as unknown as Promise<{ data: any }>,
  clear: (kind = '') => request.delete(`/resources/index?kind=${kind}`),
  search: (wd: string) => request.get('/resources/search', { params: { wd } }),
  detail: (id: number | string) => request.get(`/resources/detail/${id}`) as unknown as Promise<{ data: ResourceEntry }>,
  play: (id: number | string) =>
    request.post(`/resources/play/${id}`) as unknown as
      Promise<{ data: { url: string; name: string; size?: number; playable: boolean } }>,
}
