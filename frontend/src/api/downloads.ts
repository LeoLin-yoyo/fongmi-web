import request from './request'

export interface DownloadTask {
  id: number
  source: 'tg' | 'pan' | 'url' | string
  name: string
  status: 'queued' | 'running' | 'paused' | 'success' | 'failed' | 'canceled' | 'interrupted' | string
  file_path: string
  error: string
  done: number
  total: number
  speed: number
  pct: number
  created_at: string
}

export const downloadAPI = {
  list: () => request.get('/downloads/tasks') as unknown as
    Promise<{ code: number; data: DownloadTask[] }>,
  add: (payload: { url: string; name?: string; filename?: string; headers?: Record<string, string>; source?: string }) =>
    request.post('/downloads/tasks', payload) as unknown as Promise<{ code: number; id: number }>,
  pause: (id: number) => request.post(`/downloads/tasks/${id}/pause`),
  resume: (id: number) => request.post(`/downloads/tasks/${id}/resume`),
  cancel: (id: number, removeFiles = false) =>
    request.delete(`/downloads/tasks/${id}?remove_files=${removeFiles ? 'true' : 'false'}`),
  removeRecord: (id: number) => request.delete(`/downloads/tasks/${id}/record`),
  config: () => request.get('/downloads/config') as unknown as
    Promise<{ dir: string; default_dir: string }>,
  setConfig: (dir: string) => request.post('/downloads/config', { dir }) as unknown as Promise<{ dir: string }>,
}
