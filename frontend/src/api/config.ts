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

export function setPriority(id: number, priority: number) {
  return request.put(`/config/${id}/priority`, { priority })
}

export function reorderConfigs(ids: number[]) {
  return request.put('/config/reorder', { ids })
}

export function getSites() {
  return request.get('/config/site/') as unknown as Promise<{ code: number; data: any[] }>
}

export function getParses() {
  return request.get('/config/parses/') as unknown as Promise<{ code: number; data: any[] }>
}