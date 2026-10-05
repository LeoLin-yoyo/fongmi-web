<template>
  <div class="local-page">
    <BackTop />
    <div v-if="!embedded" class="page-header">
      <h2>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-4px;margin-right:6px">
          <rect x="2" y="7" width="20" height="15" rx="2" ry="2"/><polygon points="10 11 16 14.5 10 18 10 11"/>
        </svg>
        本地片库
      </h2>
      <n-button size="small" :type="selectMode ? 'error' : 'default'" @click="toggleSelectMode">
        {{ selectMode ? '完成' : '管理' }}
      </n-button>
      <n-button size="small" :loading="scanBusy || scanning" @click="triggerScan">扫描</n-button>
    </div>

    <div class="toolbar">
      <n-input
        v-model:value="keyword"
        placeholder="搜索视频名称…"
        clearable
        round
        class="search-input"
      >
        <template #prefix>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        </template>
      </n-input>
      <n-select v-model:value="sort" class="sort-select" :options="sortOptions" />
      <n-select v-model:value="order" class="order-select" :options="orderOptions" />
    </div>

    <div v-if="visibleDirs.length > 1 || groups.length" class="chip-row">
      <button
        v-for="g in groups"
        :key="'g' + g.id"
        class="chip chip-group"
        :class="{ active: groupId === g.id }"
        :title="groupDirsLabel(g)"
        @click="selectGroup(g.id)"
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px;margin-right:3px"><rect x="3" y="3" width="12" height="12" rx="2"/><rect x="9" y="9" width="12" height="12" rx="2"/></svg>{{ g.name }}
      </button>
      <button
        v-for="d in visibleDirs"
        :key="d.id"
        class="chip"
        :class="{ active: dirId === d.id }"
        @click="selectDir(d.id)"
      >
        {{ d.name }}
      </button>
    </div>

    <div class="list-meta">共 {{ total }} 个视频</div>

    <div v-if="scanning" class="scan-progress">
      <n-progress type="line" :percentage="scanPercent" :show-indicator="false" processing />
      <span>扫描中… {{ scanStatus.done }}/{{ scanStatus.total }}</span>
    </div>

    <template v-if="loading">
      <div class="video-grid">
        <n-skeleton v-for="i in 12" :key="i" width="100%" :height="200" bordered />
      </div>
    </template>

    <template v-else-if="videos.length === 0">
      <div class="empty-state">
        <n-empty :description="keyword ? '没有匹配的视频' : '还没有视频'">
          <template #extra>
            <span class="hint">在「设置 → 本地视频」中添加目录并扫描</span>
          </template>
        </n-empty>
      </div>
    </template>

    <template v-else>
      <div class="video-grid">
        <div
          v-for="v in videos"
          :key="v.id"
          class="video-card"
          :class="{ 'is-selected': selected.has(v.id), 'is-managing': selectMode }"
          @click="onCardClick(v)"
        >
          <div v-if="selectMode" class="card-check" :class="{ checked: selected.has(v.id) }">
            <svg v-if="selected.has(v.id)" viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
          </div>
          <div class="card-cover">
            <img :src="thumbUrl(v.id)" :alt="v.name" loading="lazy" @error="onImgError($event)" />
            <span v-if="v.duration" class="duration-badge">{{ formatDuration(v.duration) }}</span>
            <button
              v-if="extPlayerEnabled && !selectMode"
              class="card-ext"
              title="用外部播放器播放"
              :disabled="extPlaying.has(v.id)"
              @click.stop="playExternal(v)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/><path d="M10 7.5v6l5-3z" fill="currentColor" stroke="none"/></svg>
            </button>
          </div>
          <div class="card-info">
            <div class="video-name" :title="v.name">{{ v.name }}</div>
            <div class="video-meta">
              <span v-if="resOf(v)" class="tag tag-res">{{ resOf(v) }}</span>
              <span v-if="codecOf(v)" class="tag tag-codec">{{ codecOf(v) }}</span>
              <span v-if="v.size" class="tag">{{ formatSize(v.size) }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-if="hasMore" ref="sentinel" class="load-more-wrap">
        <n-spin v-if="loadingMore" size="small" />
      </div>
    </template>

    <div v-if="selectMode" class="select-bar">
      <span class="select-count">已选 <b>{{ selected.size }}</b> 个视频</span>
      <n-button type="error" size="small" :disabled="selected.size === 0" @click="confirmDelete">
        删除所选（{{ selected.size }}）
      </n-button>
      <n-button size="small" @click="toggleSelectMode">取消</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useMessage, NButton, NInput, NSelect, NSkeleton, NProgress, NEmpty, NSpin } from 'naive-ui'
import { localAPI } from '@/api/local'
import { openPlayPage } from '@/utils/navigation'
import { isMobileDevice } from '@/utils/device'
import { formatDuration, formatSize } from '@/utils/format'
import BackTop from '@/components/BackTop.vue'

const props = defineProps<{ embedded?: boolean }>()

const message = useMessage()

const PAGE = 60
const keyword = ref('')
const dirId = ref<number | null>(null)
const groupId = ref<number | null>(null)
const sort = ref('mtime')
const order = ref('desc')
const videos = ref<any[]>([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const dirs = ref<any[]>([])
const groups = ref<any[]>([])
const scanStatus = ref({ scanning: false, done: 0, total: 0 })
const wasScanning = ref(false)
const scanBusy = ref(false)
const sentinel = ref<HTMLElement | null>(null)
const selectMode = ref(false)
const selected = reactive(new Set<number>())
const extPlayerEnabled = ref(false)
const extPlaying = reactive(new Set<number>())
let searchTimer: number | undefined
let observer: IntersectionObserver | null = null

const sortOptions = [
  { label: '按修改时间', value: 'mtime' },
  { label: '按名称', value: 'name' },
  { label: '按入库时间', value: 'created' },
  { label: '按大小', value: 'size' },
  { label: '按时长', value: 'duration' },
]
const orderOptions = [
  { label: '降序（新在前）', value: 'desc' },
  { label: '升序', value: 'asc' },
]

const scanning = computed(() => scanStatus.value.scanning)
const scanPercent = computed(() => {
  const s = scanStatus.value
  return s.total > 0 ? Math.min(100, Math.round((s.done / s.total) * 100)) : 0
})
const hasMore = computed(() => videos.value.length < total.value)

function thumbUrl(id: number) { return localAPI.thumbUrl(id) }
function resOf(v: any) { return formatResolution(v) }
function codecOf(v: any) { return formatCodec(v.codec) }
function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.visibility = 'hidden'
}

function formatResolution(v: any) {
  if (!v || !v.width || !v.height) return ''
  if (v.height >= 2160) return '4K'
  if (v.height >= 1080) return '1080P'
  if (v.height >= 720) return '720P'
  if (v.height >= 480) return '480P'
  return `${v.height}P`
}
function formatCodec(codec: string) {
  const map: Record<string, string> = { h264: 'H.264', hevc: 'H.265', vp9: 'VP9', av1: 'AV1', mpeg4: 'MPEG4', vp8: 'VP8', h263: 'H.263', wmv3: 'WMV3' }
  return map[codec] || (codec ? codec.toUpperCase() : '')
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) selected.clear()
}

function dirNameOf(id: number) {
  return dirs.value.find(d => d.id === id)?.name || `#${id}`
}

/** 片库页选项卡只展示可见目录；隐藏目录仍参与扫描与聚合选项卡 */
const visibleDirs = computed(() => dirs.value.filter(d => d.visible === undefined || !!d.visible))

function groupDirsLabel(g: any) {
  return (g.dir_ids || []).map(dirNameOf).join(' + ')
}

function selectDir(id: number) {
  if (dirId.value === id) return
  dirId.value = id
  groupId.value = null
}

function selectGroup(id: number) {
  if (groupId.value === id) return
  groupId.value = id
  dirId.value = null
}

/** 校正当前选项卡：组/目录被删或目录被隐藏后，回退到第一个可用选项卡 */
function ensureActiveTab() {
  if (groupId.value !== null && groups.value.some(g => g.id === groupId.value)) return
  if (dirId.value !== null && visibleDirs.value.some(d => d.id === dirId.value)) return
  if (groups.value.length) {
    groupId.value = groups.value[0].id
    dirId.value = null
  } else if (visibleDirs.value.length) {
    dirId.value = visibleDirs.value[0].id
    groupId.value = null
  } else {
    dirId.value = null
    groupId.value = null
  }
}

function onCardClick(v: any) {
  if (selectMode.value) {
    if (selected.has(v.id)) selected.delete(v.id)
    else selected.add(v.id)
  } else {
    openPlayPage({ path: `/local/player/${v.id}` }, 'local')
  }
}

/** 调用设置页配置的外部播放器（PotPlayer 等）播放；播放器路径校验在后端 */
async function playExternal(v: any) {
  if (extPlaying.has(v.id)) return
  extPlaying.add(v.id)
  try {
    await localAPI.externalPlay(v.id)
    message.success(`已调用外部播放器播放「${v.name}」`)
  } catch (e: any) {
    message.error(`外部播放失败：${e?.response?.data?.detail || e.message}`)
  } finally {
    extPlaying.delete(v.id)
  }
}

async function confirmDelete() {
  const ids = [...selected]
  if (ids.length === 0) return
  const names = videos.value.filter((v) => selected.has(v.id)).slice(0, 3).map((v) => v.name)
  const preview = names.join('\n') + (ids.length > 3 ? `\n…等 ${ids.length} 个` : '')
  if (!confirm(`将从磁盘永久删除以下 ${ids.length} 个视频文件（不可恢复）：\n\n${preview}\n\n确定删除？`)) return
  try {
    await localAPI.deleteVideos(ids)
    message.success('删除成功')
    selected.clear()
    selectMode.value = false
    await loadVideos()
  } catch (e: any) {
    message.error(`删除失败：${e.message}`)
  }
}

async function loadVideos(append = false) {
  if (append) loadingMore.value = true
  else loading.value = true
  try {
    const params: Record<string, any> = {
      search: keyword.value,
      sort: sort.value,
      order: order.value,
      limit: PAGE,
      offset: append ? videos.value.length : 0,
    }
    if (groupId.value !== null) params.group_id = groupId.value
    else if (dirId.value !== null) params.dir_id = dirId.value
    const data = await localAPI.videos(params)
    videos.value = append ? [...videos.value, ...data.items] : data.items
    total.value = data.total
  } catch (e: any) {
    message.error('加载视频失败: ' + (e?.message || ''))
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function loadMore() { loadVideos(true) }

function triggerScan() {
  if (scanBusy.value) return
  scanBusy.value = true
  message.info('开始扫描…')
  // POST 返回后后台任务才开始执行，故随后自行轮询状态直到结束（兜底 60s）
  localAPI.scanAll()
    .then(() => waitScanDone(Date.now()))
    .catch((e: any) => {
      scanBusy.value = false
      message.error(`扫描失败：${e?.response?.data?.detail || e?.message || '未知错误'}`)
    })
}

function waitScanDone(startedAt: number, sawScanning = false) {
  const tick = async () => {
    const elapsed = Date.now() - startedAt
    const s = await localAPI.scanStatus().catch(() => null)
    if (s) {
      scanStatus.value = s
      if (s.scanning) sawScanning = true
    }
    // 结束判定：必须曾观察到「扫描中」再变空闲（POST 用 BackgroundTasks，
    // 响应后才真正开扫，避免开扫前误判）；或无新文件时超过宽限期直接收尾
    const finished = sawScanning && s && !s.scanning
    if (finished || elapsed > 60000 || (!sawScanning && elapsed > 3000)) {
      scanBusy.value = false
      refreshAfterScan()
      message.success('扫描完成')
      return
    }
    setTimeout(tick, 300)
  }
  setTimeout(tick, 300)
}

/** 扫描结束后刷新视频列表、目录/分组与统计 */
function refreshAfterScan() {
  loadVideos()
  localAPI.dirs().then((d) => { dirs.value = d; ensureActiveTab() }).catch(() => {})
  localAPI.groups().then((g) => { groups.value = g; ensureActiveTab() }).catch(() => {})
}

async function pollScan() {
  try {
    const s = await localAPI.scanStatus()
    const was = wasScanning.value
    scanStatus.value = s
    wasScanning.value = s.scanning
    if (was && !s.scanning) {
      refreshAfterScan()
    }
  } catch { /* ignore */ }
}

watch(keyword, () => {
  clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => loadVideos(), 350)
})
watch([sort, order, dirId, groupId], () => loadVideos())

let pollTimer: number | undefined
onMounted(async () => {
  dirs.value = await localAPI.dirs().catch(() => [])
  groups.value = await localAPI.groups().catch(() => [])
  // 配置了外部播放器路径且非移动终端才显示卡片角标按钮
  // （移动终端浏览器无法调起本机 exe 播放器，对移动端隐藏入口）
  fetch('/api/system/config')
    .then((r) => r.json())
    .then((data) => { extPlayerEnabled.value = !!data?.data?.external_player_path && !isMobileDevice() })
    .catch(() => {})
  ensureActiveTab()
  if (dirId.value === null && groupId.value === null) loadVideos()
  localAPI.scanAll().catch(() => {})
  pollScan()
  pollTimer = window.setInterval(pollScan, 2000)
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && hasMore.value && !loadingMore.value && !loading.value) {
        loadMore()
      }
    },
    { rootMargin: '400px' },
  )
  watch(sentinel, (el) => {
    if (el && observer) observer.observe(el)
  }, { flush: 'post' })
})
onUnmounted(() => {
  clearInterval(pollTimer)
  clearTimeout(searchTimer)
  observer?.disconnect()
})
</script>

<style scoped>
.local-page { padding: 20px; max-width: 1600px; margin: 0 auto; min-height: 100vh; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; flex: 1; }
.toolbar { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.search-input { flex: 1; min-width: 220px; max-width: 460px; }
.sort-select { width: 140px; }
.order-select { width: 140px; }
.chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.chip { flex-shrink: 0; padding: 6px 16px; border: 1px solid rgba(255,255,255,0.15); border-radius: 20px; background: rgba(255,255,255,0.06); color: #ccc; font-size: 13px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
.chip:hover { border-color: var(--n-primary-color); color: #fff; background: rgba(0,170,238,0.1); }
.chip.active { background: var(--n-primary-color); border-color: var(--n-primary-color); color: #fff; font-weight: 600; }
.chip-group { border-style: dashed; }
.list-meta { font-size: 13px; color: var(--n-text-color-3); padding: 2px 2px 10px; }
.scan-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.scan-progress .n-progress { flex: 1; }
.scan-progress span { font-size: 13px; color: var(--n-text-color-3); white-space: nowrap; }
.video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 16px; }
.video-card { position: relative; border-radius: 12px; overflow: hidden; background: var(--n-card-color); cursor: pointer; transition: all 0.25s; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.video-card:hover { transform: translateY(-3px); border-color: var(--n-primary-color); box-shadow: 0 6px 20px rgba(0,0,0,0.15); }
.video-card.is-selected { outline: 2px solid var(--n-primary-color); outline-offset: -2px; }
.card-cover { position: relative; aspect-ratio: 16/9; overflow: hidden; background: var(--n-base-color); }
.card-cover img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }
.video-card:hover .card-cover img { transform: scale(1.05); }
.duration-badge { position: absolute; right: 8px; bottom: 8px; padding: 2px 7px; border-radius: 6px; background: rgba(0,0,0,0.72); color: #fff; font-size: 12px; font-weight: 600; }
.card-ext { position: absolute; top: 8px; right: 8px; z-index: 3; width: 26px; height: 26px; border: none; border-radius: 7px; background: rgba(0,0,0,0.55); color: #fff; display: flex; align-items: center; justify-content: center; cursor: pointer; opacity: 0.85; transition: opacity 0.2s, background 0.2s; }
.card-ext:hover { background: var(--n-primary-color); opacity: 1; }
.card-ext:disabled { opacity: 0.4; cursor: wait; }
.card-ext svg { width: 15px; height: 15px; }
.card-info { padding: 10px 12px; }
.video-name { font-size: 14px; font-weight: 500; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 6px; }
.video-meta { display: flex; gap: 5px; flex-wrap: wrap; }
.tag { padding: 2px 7px; border-radius: 5px; font-size: 11px; background: var(--n-divider-color); color: var(--n-text-color-3); font-weight: 500; }
.tag-res { color: #a78bfa; background: rgba(139, 92, 246, 0.13); }
.tag-codec { color: #67e8f9; background: rgba(34, 211, 238, 0.1); }
.empty-state { padding: 60px 0; }
.hint { font-size: 13px; color: var(--n-text-color-3); }
.card-check { position: absolute; top: 10px; left: 10px; z-index: 3; width: 24px; height: 24px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.75); background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; }
.card-check svg { width: 15px; height: 15px; fill: #fff; }
.card-check.checked { background: var(--n-primary-color); border-color: var(--n-primary-color); }
.load-more-wrap { display: flex; justify-content: center; padding: 24px 0; }
.select-bar { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 60; display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-radius: 16px; background: var(--n-card-color); border: 1px solid var(--n-border-color); box-shadow: 0 8px 30px rgba(0,0,0,0.35); }
.select-count { font-size: 14px; color: var(--n-text-color-3); white-space: nowrap; }
.select-count b { color: var(--n-primary-color); font-size: 16px; }
@media (max-width: 640px) {
  .video-grid { grid-template-columns: repeat(2, 1fr); gap: 11px; }
  .select-bar { bottom: 12px; padding: 10px 14px; }
}
</style>
