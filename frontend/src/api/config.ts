import request from './request'

export function importConfig(data: { url?: string; content?: string; type: string }) {
  return request.post('/config/import', data)
}

export function importBatch(urls: string[]) {
  return request.post('/config/import_batch', { urls })
}

export function getConfigs() {
  return request.get('/config/') as unknown as Promise<{ code: number; data: any[] }>
}

export function deleteConfig(id: number) {
  return request.delete(`/config/${id}`)
}

export function toggleConfig(id: number) {
  return request.put(`/config/${id}/toggle`)
}

export function activateConfig(id: number) {
  return request.put(`/config/${id}/toggle`)
}

export function setPriority(id: number, priority: number) {
  return request.put(`/config/${id}/priority`, { priority })
}

export function reorderConfigs(ids: number[]) {
  return request.put('/config/reorder', { ids })
}

export function renameConfig(id: number, name: string) {
  return request.put(`/config/${id}/name`, { name })
}

export function getSites() {
  return request.get('/config/site/') as unknown as Promise<{ code: number; data: any[] }>
}

export function getParses() {
  return request.get('/config/parses/') as unknown as Promise<{ code: number; data: any[] }>
}

export function checkUrl(url: string) {
  return request.post('/config/check_url', { url })
}

export function checkBatch(urls: string[]) {
  return request.post('/config/check_batch', { urls })
}

export function importLiveSource(url: string, name: string = '') {
  return request.post('/live_source/import', { url, name })
}

export function importLiveBatch(items: { url: string; name: string }[]) {
  return request.post('/live_source/import_batch', { items })
}

export function getLiveSources() {
  return request.get('/live_source/')
}

export function deleteLiveSource(id: number) {
  return request.delete(`/live_source/${id}`)
}

export function toggleLiveSource(id: number) {
  return request.put(`/live_source/${id}/toggle`)
}

export function getLiveChannels(id: number) {
  return request.get('/live_source/channels', { params: { source_id: id } })
}