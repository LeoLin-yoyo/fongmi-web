import request from './request'

export interface AuthStatus {
  required: boolean
  authenticated: boolean
  username: string
  configured_username: string
}

export const authAPI = {
  status: () => request.get('/auth/status') as unknown as Promise<{ data: AuthStatus }>,
  login: (username: string, password: string) =>
    request.post('/auth/login', { username, password }) as unknown as Promise<{ data: any }>,
  logout: () => request.post('/auth/logout', {}) as unknown as Promise<any>,
  getConfig: () => request.get('/auth/config') as unknown as
    Promise<{ data: { required: boolean; username: string; has_password: boolean } }>,
  setConfig: (username: string, password: string) =>
    request.post('/auth/config', { username, password }) as unknown as Promise<{ data: any }>,
}
