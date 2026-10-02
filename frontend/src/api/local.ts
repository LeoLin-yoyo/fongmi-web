import request from './request'

export const localAPI = {
  dirs: () => request.get('/local/dirs') as unknown as Promise<any[]>,
  addDir: (path: string) => request.post('/local/dirs', { path }),
  deleteDir: (id: number) => request.delete(`/local/dirs/${id}`),
  scanDir: (id: number) => request.post(`/local/dirs/${id}/scan`),
  scanAll: () => request.post('/local/scan'),
  scanStatus: () => request.get('/local/scan/status') as unknown as Promise<{ scanning: boolean; done: number; total: number; dir: string | null }>,
  videos: (params: Record<string, any> = {}) => request.get('/local/videos', { params }) as unknown as Promise<{ items: any[]; total: number; limit: number; offset: number }>,
  video: (id: number | string) => request.get(`/local/videos/${id}`),
  deleteVideos: (ids: number[]) => request.delete(`/local/videos?ids=${ids.join(',')}`),
  stats: () => request.get('/local/stats') as unknown as Promise<{ video_count: number; dir_count: number; total_size: number }>,
  streamUrl: (id: number | string) => `/api/local/videos/${id}/stream`,
  thumbUrl: (id: number | string) => `/api/local/videos/${id}/thumb`,
}
