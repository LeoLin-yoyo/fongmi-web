import request from './request'

export const localAPI = {
  dirs: () => request.get('/local/dirs') as unknown as Promise<any[]>,
  addDir: (path: string) => request.post('/local/dirs', { path }),
  deleteDir: (id: number) => request.delete(`/local/dirs/${id}`),
  setDirVisible: (id: number, visible: boolean) => request.patch(`/local/dirs/${id}/visible`, { visible }),
  reorderDirs: (ids: number[]) => request.put('/local/dirs/order', { ids }),
  scanDir: (id: number) => request.post(`/local/dirs/${id}/scan`),
  scanAll: () => request.post('/local/scan'),
  scanStatus: () => request.get('/local/scan/status') as unknown as Promise<{ scanning: boolean; done: number; total: number; dir: string | null }>,
  videos: (params: Record<string, any> = {}) => request.get('/local/videos', { params }) as unknown as Promise<{ items: any[]; total: number; limit: number; offset: number }>,
  video: (id: number | string) => request.get(`/local/videos/${id}`),
  deleteVideos: (ids: number[]) => request.delete(`/local/videos?ids=${ids.join(',')}`),
  stats: () => request.get('/local/stats') as unknown as Promise<{ video_count: number; dir_count: number; total_size: number }>,
  groups: () => request.get('/local/groups') as unknown as Promise<any[]>,
  createGroup: (name: string, dirIds: number[]) => request.post('/local/groups', { name, dir_ids: dirIds }),
  updateGroup: (id: number, name: string, dirIds: number[]) => request.put(`/local/groups/${id}`, { name, dir_ids: dirIds }),
  deleteGroup: (id: number) => request.delete(`/local/groups/${id}`),
  streamUrl: (id: number | string) => `/api/local/videos/${id}/stream`,
  thumbUrl: (id: number | string) => `/api/local/videos/${id}/thumb`,
}
