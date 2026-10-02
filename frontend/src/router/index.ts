import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'Home', component: () => import('@/views/Home.vue') },
  { path: '/setting', name: 'Setting', component: () => import('@/views/Setting.vue') },
  { path: '/category/:site', name: 'Category', component: () => import('@/views/CategoryPage.vue') },
  { path: '/detail/:site/:ids', name: 'Detail', component: () => import('@/views/DetailPage.vue') },
  { path: '/search', name: 'Search', component: () => import('@/views/SearchPage.vue') },
  { path: '/play', name: 'Play', component: () => import('@/views/PlayPage.vue') },
  { path: '/live', name: 'Live', component: () => import('@/views/LivePage.vue') },
  { path: '/history', name: 'History', component: () => import('@/views/HistoryPage.vue') },
  { path: '/keep', name: 'Keep', component: () => import('@/views/KeepPage.vue') },
  { path: '/local', name: 'LocalHome', component: () => import('@/views/LocalHome.vue') },
  { path: '/local/player/:id', name: 'LocalPlayer', component: () => import('@/views/LocalPlayer.vue'), props: true },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 导航埋点（T0-1）：统计首页→首次播放步数
router.afterEach((to, from) => {
  if (from.path !== to.path) {
    import('@/utils/metrics').then(({ trackNav }) => trackNav(from.path, to.path)).catch(() => {})
  }
})

export default router
