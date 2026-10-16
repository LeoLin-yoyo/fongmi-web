import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'Login', component: () => import('@/views/LoginPage.vue') },
  { path: '/', name: 'Home', component: () => import('@/views/Home.vue') },
  { path: '/setting', name: 'Setting', component: () => import('@/views/Setting.vue') },
  { path: '/category/:site', name: 'Category', component: () => import('@/views/CategoryPage.vue') },
  { path: '/detail/:site/:ids', name: 'Detail', component: () => import('@/views/DetailPage.vue') },
  { path: '/resource/:id', name: 'Resource', component: () => import('@/views/ResourcePage.vue'), props: true },
  { path: '/search', name: 'Search', component: () => import('@/views/SearchPage.vue') },
  { path: '/play', name: 'Play', component: () => import('@/views/PlayPage.vue') },
  { path: '/live', name: 'Live', component: () => import('@/views/LivePage.vue') },
  { path: '/pan', name: 'Pan', component: () => import('@/views/PanPage.vue') },
  { path: '/tg', name: 'Tg', component: () => import('@/views/TgPage.vue') },
  { path: '/downloads', name: 'Downloads', component: () => import('@/views/DownloadsPage.vue') },
  { path: '/history', name: 'History', component: () => import('@/views/HistoryPage.vue') },
  { path: '/keep', name: 'Keep', component: () => import('@/views/KeepPage.vue') },
  { path: '/local', name: 'LocalHome', component: () => import('@/views/LocalHome.vue') },
  { path: '/local/player/:id', name: 'LocalPlayer', component: () => import('@/views/LocalPlayer.vue'), props: true },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 登录守卫：需要认证且未登录时，任何页面都先跳登录页
let authChecked = false
let authRequired = false

router.beforeEach(async (to) => {
  if (to.path === '/login') return true
  if (!authChecked) {
    try {
      const { authAPI } = await import('@/api/auth')
      const res: any = await authAPI.status()
      authRequired = !!res.data?.required && !res.data?.authenticated
    } catch { authRequired = false }
    authChecked = true
  }
  if (authRequired) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

// 导航埋点（T0-1）：统计首页→首次播放步数
router.afterEach((to, from) => {
  if (from.path !== to.path) {
    import('@/utils/metrics').then(({ trackNav }) => trackNav(from.path, to.path)).catch(() => {})
  }
})

export default router
