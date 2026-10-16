<template>
  <div class="dl-page">
    <BackTop />
    <div class="page-header">
      <h2>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-4px;margin-right:6px">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>
        </svg>
        下载任务
      </h2>
      <n-button size="small" :loading="loading" @click="load">刷新</n-button>
    </div>

    <div class="dir-bar">
      <span class="dir-label">下载目录</span>
      <n-input v-model:value="downloadDir" size="small" placeholder="绝对路径，例如 D:\Downloads" class="dir-input" />
      <n-button size="small" type="primary" :loading="savingDir" @click="saveDir">保存</n-button>
    </div>

    <div class="add-bar">
      <n-input
        v-model:value="newUrl"
        size="small"
        placeholder="粘贴直链 URL 添加下载任务…"
        class="add-input"
        @keyup.enter="addTask"
      />
      <n-input v-model:value="newName" size="small" placeholder="文件名（可选）" class="name-input" />
      <n-button size="small" type="primary" :loading="adding" :disabled="!newUrl.trim()" @click="addTask">添加</n-button>
    </div>

    <div v-if="tasks.length === 0" class="empty">
      <n-empty description="暂无下载任务">
        <template #extra>
          <span class="hint">在「网盘解析」页点下载，或在此粘贴直链</span>
        </template>
      </n-empty>
    </div>

    <div v-else class="task-list">
      <div v-for="t in tasks" :key="t.id" class="task-card">
        <div class="task-head">
          <span class="src-badge" :class="'src-' + t.source">{{ sourceLabel(t.source) }}</span>
          <span class="task-name" :title="t.name">{{ t.name || '未命名' }}</span>
          <n-tag size="small" :type="statusType(t.status)">{{ statusLabel(t.status) }}</n-tag>
        </div>

        <div class="progress-row">
          <n-progress
            type="line"
            :percentage="t.pct"
            :status="t.status === 'success' ? 'success' : t.status === 'failed' ? 'error' : 'default'"
            :show-indicator="false"
          />
          <span class="progress-text">{{ formatSize(t.done) }} / {{ formatSize(t.total) }}</span>
        </div>

        <div class="task-meta">
          <span v-if="t.status === 'running' && t.speed" class="speed">{{ formatSize(t.speed) }}/s</span>
          <span v-if="t.file_path" class="path" :title="t.file_path">{{ t.file_path }}</span>
          <span v-if="t.error" class="err" :title="t.error">{{ t.error }}</span>
        </div>

        <div class="task-actions">
          <n-button v-if="t.status === 'running'" size="tiny" @click="pause(t)">暂停</n-button>
          <n-button v-if="['paused', 'failed', 'interrupted', 'canceled'].includes(t.status)" size="tiny" type="primary" ghost @click="resume(t)">继续</n-button>
          <n-button v-if="['running', 'queued', 'paused'].includes(t.status)" size="tiny" type="warning" ghost @click="cancel(t)">取消</n-button>
          <n-button v-if="!['running', 'queued'].includes(t.status)" size="tiny" type="error" ghost @click="remove(t)">删除</n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useMessage, NButton, NInput, NProgress, NTag, NEmpty } from 'naive-ui'
import { downloadAPI, type DownloadTask } from '@/api/downloads'
import { formatSize } from '@/utils/format'
import BackTop from '@/components/BackTop.vue'

const message = useMessage()
const tasks = ref<DownloadTask[]>([])
const loading = ref(false)
const downloadDir = ref('')
const savingDir = ref(false)
const newUrl = ref('')
const newName = ref('')
const adding = ref(false)
let es: EventSource | null = null

const STATUS: Record<string, string> = {
  queued: '排队中', running: '下载中', paused: '已暂停', success: '已完成',
  failed: '失败', canceled: '已取消', interrupted: '已中断',
}

function statusLabel(s: string) { return STATUS[s] || s }
function statusType(s: string) {
  if (s === 'success') return 'success'
  if (s === 'failed') return 'error'
  if (s === 'running') return 'info'
  if (s === 'paused' || s === 'interrupted') return 'warning'
  return 'default'
}
function sourceLabel(s: string) {
  return { tg: 'TG', pan: '网盘', url: '直链' }[s] || s
}

async function load() {
  loading.value = true
  try {
    const res = await downloadAPI.list()
    tasks.value = res.data || []
  } catch { /* ignore */ } finally {
    loading.value = false
  }
}

async function loadConfig() {
  try {
    const res = await downloadAPI.config()
    downloadDir.value = res.dir || ''
  } catch { /* ignore */ }
}

async function saveDir() {
  savingDir.value = true
  try {
    const res = await downloadAPI.setConfig(downloadDir.value.trim())
    downloadDir.value = res.dir
    message.success('下载目录已更新')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingDir.value = false
  }
}

async function addTask() {
  const url = newUrl.value.trim()
  if (!url) return
  adding.value = true
  try {
    await downloadAPI.add({ url, name: newName.value.trim(), source: 'url' })
    message.success('已加入下载队列')
    newUrl.value = ''
    newName.value = ''
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '添加失败')
  } finally {
    adding.value = false
  }
}

async function pause(t: DownloadTask) { try { await downloadAPI.pause(t.id); await load() } catch { message.error('操作失败') } }
async function resume(t: DownloadTask) { try { await downloadAPI.resume(t.id); await load() } catch { message.error('操作失败') } }
async function cancel(t: DownloadTask) { try { await downloadAPI.cancel(t.id); await load() } catch { message.error('操作失败') } }
async function remove(t: DownloadTask) { try { await downloadAPI.removeRecord(t.id); await load() } catch { message.error('操作失败') } }

function applyProgress(data: any) {
  const t = tasks.value.find(x => x.id === data.id)
  if (!t) return
  t.done = data.done
  t.total = data.total
  t.speed = data.speed
  t.pct = t.total ? Math.round((t.done * 1000 / t.total)) / 10 : 0
  if (data.status) t.status = data.status
}

function connectSSE() {
  try {
    es = new EventSource('/api/downloads/events')
    es.addEventListener('task', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      if (data.deleted) { tasks.value = tasks.value.filter(x => x.id !== data.id); return }
      const idx = tasks.value.findIndex(x => x.id === data.id)
      if (idx >= 0) tasks.value[idx] = { ...tasks.value[idx], ...data }
      else load()
    })
    es.addEventListener('task-progress', (e: MessageEvent) => applyProgress(JSON.parse(e.data)))
  } catch { /* SSE 不可用时退回轮询 */ }
}

let poll: number | undefined

onMounted(() => {
  load()
  loadConfig()
  connectSSE()
  poll = window.setInterval(load, 15000)
})

onUnmounted(() => {
  if (es) es.close()
  if (poll) clearInterval(poll)
})
</script>

<style scoped>
.dl-page { padding: 20px; max-width: 1100px; margin: 0 auto; min-height: 100vh; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; flex: 1; }
.dir-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.dir-label { font-size: 13px; color: #888; flex-shrink: 0; }
.dir-input { flex: 1; max-width: 520px; }
.add-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.add-input { flex: 1; max-width: 460px; }
.name-input { max-width: 220px; }
.empty { padding: 60px 0; }
.hint { font-size: 13px; color: #888; }
.task-list { display: flex; flex-direction: column; gap: 12px; }
.task-card { border: 1px solid rgba(128,128,128,0.15); border-radius: 10px; padding: 14px 16px; background: var(--n-card-color); }
.task-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.src-badge { font-size: 11px; padding: 2px 7px; border-radius: 4px; flex-shrink: 0; background: rgba(128,128,128,0.15); color: #aaa; }
.src-badge.src-tg { background: rgba(42,171,238,0.18); color: #2aabee; }
.src-badge.src-pan { background: rgba(0,170,238,0.15); color: var(--n-primary-color); }
.task-name { flex: 1; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.progress-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.progress-row :deep(.n-progress) { flex: 1; }
.progress-text { font-size: 12px; color: #888; flex-shrink: 0; min-width: 120px; text-align: right; }
.task-meta { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: #888; margin-bottom: 10px; }
.task-meta .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.task-meta .err { color: #e88080; }
.speed { color: var(--n-primary-color); }
.task-actions { display: flex; gap: 8px; }
</style>
