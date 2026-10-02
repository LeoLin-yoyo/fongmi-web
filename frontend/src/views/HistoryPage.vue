<template>
  <div class="history-page">
    <div class="page-header">
      <n-button text @click="$router.back()">← 返回</n-button>
      <h2>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-4px;margin-right:4px">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        我的
      </h2>
      <n-button v-if="list.length" text type="error" @click="clearAll">清空</n-button>
    </div>
    <div class="page-tabs">
      <router-link to="/history" class="page-tab">观看历史</router-link>
      <router-link to="/keep" class="page-tab">我的收藏</router-link>
    </div>
    <div v-if="loading" class="loading"><n-spin size="large" /></div>
    <div v-else-if="!list.length" class="empty"><n-empty description="暂无观看记录" /></div>
    <div v-else class="history-list">
      <div v-for="item in list" :key="item.id" class="history-card" @click="goPlay(item)">
        <div class="h-cover"><img :src="imgUrl(item.pic, item.name) || defaultPic" /></div>
        <div class="h-info">
          <div class="h-name">{{ item.name }}</div>
          <div class="h-time">{{ formatTime(item.time) }}</div>
        </div>
        <n-button text type="error" size="small" @click.stop="remove(item.id)">删除</n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NButton, NSpin, NEmpty } from 'naive-ui'
import { historyAPI } from '@/api/vod'
import { imgUrl } from '@/api/img'
import { openInNewTab } from '@/utils/navigation'

const list = ref<any[]>([])
const loading = ref(false)
const defaultPic = imgUrl('')

onMounted(loadList)

async function loadList() {
  loading.value = true
  try {
    const res: any = await historyAPI.list(1, 500)
    list.value = res?.items || (Array.isArray(res) ? res : [])
  } finally {
    loading.value = false
  }
}

function formatTime(t: string) {
  if (!t) return ''
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

function goPlay(item: any) {
  // 优先进详情页续看（可换源/选集），老数据没有站点信息时回退直连播放；均在新标签页打开
  if (item.site_key && item.vod_id) {
    openInNewTab({ path: `/detail/${item.site_key}/${item.vod_id}`, query: { autoplay: '1' } })
  } else if (item.episode) {
    openInNewTab({ path: '/play', query: { url: item.episode } })
  }
}

async function remove(id: number) {
  await historyAPI.delete(id)
  await loadList()
}

async function clearAll() {
  await historyAPI.clear()
  list.value = []
}
</script>

<style scoped>
.history-page { padding: 20px; max-width: 1000px; margin: 0 auto; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.page-header h2 { margin: 0; font-size: 20px; flex: 1; }
.page-tabs { display: flex; gap: 6px; margin-bottom: 20px; }
.page-tab { padding: 6px 18px; border-radius: 18px; font-size: 13px; color: #888; background: rgba(128,128,128,0.08); transition: all 0.2s; }
.page-tab:hover { color: var(--text-color); }
.page-tab.router-link-exact-active { background: var(--n-primary-color, #4098ff); color: #fff; }
.loading, .empty { padding: 60px 0; display: flex; justify-content: center; }
.history-list { display: flex; flex-direction: column; gap: 8px; }
.history-card {
  display: flex; align-items: center; gap: 12px;
  padding: 12px; background: var(--n-card-color); border-radius: 10px;
  cursor: pointer; transition: all 0.2s;
}
.history-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
.h-cover { width: 80px; flex-shrink: 0; }
.h-cover img { width: 80px; border-radius: 6px; aspect-ratio: 2/3; object-fit: cover; }
.h-info { flex: 1; min-width: 0; }
.h-name { font-size: 14px; font-weight: 500; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h-time { font-size: 12px; color: var(--n-text-color-3); }
</style>
