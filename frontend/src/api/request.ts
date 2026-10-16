import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 未登录：跳转登录页（避免在登录页自身循环跳转）
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    if (status === 401 && !url.includes('/auth/')) {
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export { request }
export default request
