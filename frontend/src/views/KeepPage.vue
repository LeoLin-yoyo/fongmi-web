<template>
  <div class="keep-page">
    <div class="page-header">
      <n-button text @click="$router.back()">← 返回</n-button>
      <h2>♥ 我的</h2>
      <div class="header-actions">
        <n-button size="small" quaternary @click="checkAllUpdates" :loading="checkingUpdates">
          {{ updatedCount > 0 ? `有 ${updatedCount} 个更新` : '检查更新' }}
        </n-button>
      </div>
    </div>
    <div class="page-tabs">
      <router-link to="/history" class="page-tab">观看历史</router-link>
      <router-link to="/keep" class="page-tab">我的收藏</router-link>
    </div>
    <div v-if="loading" class="loading"><n-spin size="large" /></div>
    <div v-else-if="!list.length" class="empty"><n-empty description="暂无收藏" /></div>
    <div v-else class="grid">
      <div v-for="item in list" :key="item.id" class="video-card" :class="{ 'has-update': item._hasUpdate }" @click="goDetail(item)">
        <div class="card-cover">
          <img :src="imgUrl(item.pic, item.name) || defaultPic" />
          <div v-if="item._hasUpdate" class="update-badge">更新</div>
        </div>
        <div class="card-info">
          <div class="video-name">{{ item.name }}</div>
          <div class="video-meta" v-if="item._episodeCount">共 {{ item._episodeCount }} 集</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { NSpin, NEmpty, NButton } from 'naive-ui'
import { keepAPI, vodAPI } from '@/api/vod'
import { imgUrl } from '@/api/img'
import { openPlayPage } from '@/utils/navigation'

const list = ref<any[]>([])
const loading = ref(false)
const checkingUpdates = ref(false)
const defaultPic = imgUrl('')

const updatedCount = computed(() => list.value.filter(i => i._hasUpdate).length)

onMounted(async () => {
  await loadList()
  if (list.value.length > 0) {
    setTimeout(() => checkAllUpdates(), 2000)
  }
})

async function loadList() {
  loading.value = true
  try {
    const res: any = await keepAPI.list(1, 500)
    list.value = res?.items || (Array.isArray(res) ? res : [])
  } catch (e) {
    console.error(e)
    list.value = []
  } finally {
    loading.value = false
  }
}

async function checkAllUpdates() {
  checkingUpdates.value = true
  let count = 0
  for (const item of list.value) {
    try {
      const res: any = await vodAPI.detail(item.site_key, item.vod_id)
      if (res?.list?.[0]) {
        const detail = res.list[0]
        const epCount = (detail.vod_play_url || '').split('$$$').filter(Boolean).length
        item._episodeCount = epCount
        const oldEpCount = (item as any)._oldEpCount || 0
        if (oldEpCount > 0 && epCount > oldEpCount) {
          item._hasUpdate = true
          count++
        }
        item._oldEpCount = epCount
      }
    } catch { /* ignore */ }
  }
  checkingUpdates.value = false
  if (count > 0 && document.visibilityState === 'visible') {
    window.$message?.success(`有 ${count} 个收藏剧集更新了`)
  }
}

function goDetail(item: any) {
  openPlayPage({ path: `/detail/${item.site_key}/${item.vod_id}`, query: { autoplay: '1' } }, 'vod')
}
</script>

<style scoped>
.keep-page { padding: 20px; max-width: 1600px; margin: 0 auto; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.page-header h2 { margin: 0; flex: 1; }
.header-actions { flex-shrink: 0; }
.page-tabs { display: flex; gap: 6px; margin-bottom: 20px; }
.page-tab { padding: 6px 18px; border-radius: 18px; font-size: 13px; color: #888; background: rgba(128,128,128,0.08); transition: all 0.2s; }
.page-tab:hover { color: var(--text-color); }
.page-tab.router-link-exact-active { background: var(--n-primary-color, #4098ff); color: #fff; }
.loading, .empty { padding: 60px 0; display: flex; justify-content: center; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
.video-card { border-radius: 12px; overflow: hidden; background: var(--n-card-color); cursor: pointer; transition: all 0.3s; }
.video-card:hover { transform: translateY(-4px); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
.video-card.has-update { box-shadow: 0 0 0 2px var(--n-primary-color); }
.card-cover { position: relative; aspect-ratio: 2/3; background: #1a1a2e; }
.card-cover img { width: 100%; height: 100%; object-fit: cover; }
.update-badge { position: absolute; top: 8px; right: 8px; background: #f5222d; color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.card-info { padding: 10px 12px; }
.video-name { font-size: 13px; font-weight: 500; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }
.video-meta { font-size: 11px; color: #888; margin-top: 2px; }
</style>
