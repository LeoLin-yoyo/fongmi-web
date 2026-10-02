import request from './request'

export const vodAPI = {
  home: (siteKey: string, filter = true) =>
    request.get('/vod/home', { params: { site_key: siteKey, filter: filter ? 'true' : 'false' } }),
  category: (siteKey: string, tid: string, pg = 1, extend = {}) =>
    request.get('/vod/category', { params: { site_key: siteKey, tid, pg: String(pg), extend: JSON.stringify(extend) || '' } }),
  detail: (siteKey: string, ids: string) =>
    request.get('/vod/detail', { params: { site_key: siteKey, ids } }),
  search: (wd: string) =>
    request.get('/vod/search', { params: { wd } }),
  searchAggregated: (wd: string) =>
    request.get('/vod/search_aggregated', { params: { wd } }),
  player: (siteKey: string, flag: string, id: string) =>
    request.get('/vod/player', { params: { site_key: siteKey, flag, id } }),
  vodSites: () => request.get('/vod_sites'),
}

export const liveAPI = {
  groups: () => request.get('/live/groups'),
  channels: (sourceIdx: number) => request.get('/live/channels', { params: { source_idx: sourceIdx } }),
  epg: (sourceIdx: number) => request.get('/live/epg', { params: { source_idx: sourceIdx } }),
}

export const historyAPI = {
  list: (page = 1, size = 50) => request.get('/history', { params: { page, size } }),
  check: (siteKey: string, vodId: string) => request.get('/history/check', { params: { site_key: siteKey, vod_id: vodId } }),
  add: (data: any) => request.post('/history', data),
  update: (data: any) => request.put('/history', data),
  delete: (id: number) => request.delete(`/history/${id}`),
  clear: () => request.delete('/history'),
}

export const keepAPI = {
  list: (page = 1, size = 20) => request.get('/keep', { params: { page, size } }),
  add: (data: any) => request.post('/keep', data),
  delete: (id: number) => request.delete(`/keep/${id}`),
  check: (siteKey: string, vodId: string) =>
    request.get('/keep/check', { params: { site_key: siteKey, vod_id: vodId } }),
}
