<template>
  <div class="res-page">
    <BackTop />
    <div class="page-header">
      <n-button size="small" quaternary @click="$router.back()">
        <template #icon><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg></template>
        返回
      </n-button>
      <h2>资源详情</h2>
    </div>

    <div v-if="loading" class="loading-area"><n-spin size="large" /></div>

    <n-empty v-else-if="!entry" description="资源不存在或已失效" />

    <div v-else class="res-card">
      <div class="res-main">
        <div class="res-badge">{{ entry.kind === 'tg' ? 'TG' : '网盘' }}</div>
        <div class="res-name" :title="entry.name">{{ entry.name }}</div>
        <div class="res-meta">
          <span v-if="entry.size">{{ formatSize(entry.size) }}</span>
          <span class="res-site">{{ entry.site_key }}</span>
        </div>
      </div>
      <div class="res-actions">
        <n-button type="primary" :loading="playing" @click="play">播放</n-button>
        <n-button ghost :loading="downloading" @click="download">下载</n-button>
      </div>
      <n-alert v-if="notice" :type="noticeType" class="res-notice">{{ notice }}</n-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, NButton, NSpin, NEmpty, NAlert } from 'naive-ui'
import { resourceAPI, type ResourceEntry } from '@/api/resources'
import { downloadAPI } from '@/api/downloads'
import { formatSize } from '@/utils/format'
import BackTop from '@/components/BackTop.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const entry = ref<ResourceEntry | null>(null)
const loading = ref(true)
const playing = ref(false)
const downloading = ref(false)
const notice = ref('')
const noticeType = ref<'warning' | 'error' | 'info'>('warning')

async function load() {
  loading.value = true
  try {
    const res: any = await resourceAPI.detail(route.params.id as string)
    entry.value = res.data
  } catch (e: any) {
    if (e?.response?.status === 404) entry.value = null
    else message.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function resolveUrl(): Promise<{ url: string; name: string; playable: boolean } | null> {
  try {
    const res: any = await resourceAPI.play(entry.value!.id)
    return res.data
  } catch (e: any) {
    const detail = e?.response?.data?.detail || '获取播放地址失败'
    notice.value = detail
    noticeType.value = e?.response?.status === 410 ? 'warning' : 'error'
    message.error(detail)
    return null
  }
}

async function play() {
  if (!entry.value) return
  playing.value = true
  try {
    const info = await resolveUrl()
    if (!info) return
    if (!info.playable) notice.value = '该文件浏览器无法直接播放，建议下载后用本地播放器'
    window.open(`/play?url=${encodeURIComponent(info.url)}&title=${encodeURIComponent(info.name)}`, '_blank')
  } finally {
    playing.value = false
  }
}

async function download() {
  if (!entry.value) return
  downloading.value = true
  try {
    const info = await resolveUrl()
    if (!info) return
    if (entry.value.kind === 'tg') {
      // TG：直接用统一引擎下载（url 为 /api/tg/stream 相对路径，需补全主机）
      const abs = info.url.startsWith('http') ? info.url : window.location.origin + info.url
      await downloadAPI.add({ url: abs, name: info.name, source: 'tg' })
    } else {
      // 网盘：走 pan 下载入队（复用 token）
      const token = info.url.split('/').pop() || ''
      await (await import('@/api/pan')).panAPI.download(token)
    }
    message.success(`已加入下载队列：${info.name}`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '下载失败')
  } finally {
    downloading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.res-page { padding: 20px; max-width: 900px; margin: 0 auto; min-height: 100vh; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 18px; }
.loading-area { display: flex; justify-content: center; padding: 80px 0; }
.res-card { border: 1px solid rgba(128,128,128,0.15); border-radius: 12px; padding: 24px; background: var(--n-card-color); }
.res-main { margin-bottom: 20px; }
.res-badge { display: inline-block; font-size: 12px; padding: 2px 8px; border-radius: 6px; background: rgba(0,170,238,0.15); color: var(--n-primary-color); margin-bottom: 10px; }
.res-name { font-size: 18px; font-weight: 600; line-height: 1.4; word-break: break-all; }
.res-meta { display: flex; gap: 14px; font-size: 13px; color: #888; margin-top: 8px; }
.res-site { color: #666; }
.res-actions { display: flex; gap: 12px; }
.res-notice { margin-top: 16px; }
</style>
