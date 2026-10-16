import request from './request'

export interface PanFile {
  fid: string
  fname: string
  fsize: number
  isdir: boolean
  pdir_fid: string
  fid_token: string
  updated_at: string
  path: string
}

export interface PanSession {
  platform: string
  label: string
  share_id: string
  passcode: string
  title: string
  guest: boolean
  notice: string
}

export const panAPI = {
  platforms: () => request.get('/pan/platforms') as unknown as Promise<{ data: { key: string; label: string }[] }>,
  resolve: (text: string, passcode = '') =>
    request.post('/pan/resolve', { text, passcode }) as unknown as
      Promise<{ session: PanSession; files: PanFile[] }>,
  browse: (platform: string, shareId: string, passcode: string, pdirFid: string, path: string) =>
    request.post('/pan/browse', {
      platform, share_id: shareId, passcode, pdir_fid: pdirFid, path,
    }) as unknown as Promise<{ files: PanFile[] }>,
  link: (platform: string, shareId: string, passcode: string, fid: string, pdirFid: string) =>
    request.post('/pan/link', {
      platform, share_id: shareId, passcode, fid, pdir_fid: pdirFid,
    }) as unknown as Promise<{ token: string; name: string; size: number; stream_path: string; playable: boolean }>,
  download: (token: string, folder = '') =>
    request.post('/pan/download', { token, folder }) as unknown as Promise<{ id: number; name: string }>,
  accounts: () => request.get('/pan/accounts') as unknown as
    Promise<{ data: { platform: string; label: string; has_cookie: boolean; nickname: string; valid: boolean; guest_note: string }[] }>,
  saveAccount: (platform: string, cookie: string) =>
    request.post('/pan/accounts', { platform, cookie }) as unknown as Promise<{ code: number; detail?: string }>,
  deleteAccount: (platform: string) => request.delete(`/pan/accounts/${platform}`),
  checkAccount: (platform: string) =>
    request.post(`/pan/accounts/${platform}/check`, {}) as unknown as
      Promise<{ data: { valid: boolean; nickname?: string; detail?: string } }>,
}
