<template>
  <div class="detail-page">
    <div v-if="!siteKey" class="empty-tip"><n-empty description="请先选择站点" /></div>

    <div v-else-if="detail" class="detail-layout fade-in">
      <div class="player-column">
        <div class="player-sticky">
          <div v-if="currentUrl" class="player-container" @mousemove="onMouseMove" @click="toggleControls">
            <div class="video-wrapper">
              <video ref="videoRef" autoplay preload="auto" class="detail-video"
                @click="togglePlay"></video>
              <div class="player-top-bar" v-if="showControls">
                <span class="resolution-tag" v-if="videoResolution">{{ videoResolution }}</span>
                <span class="speed-tag" v-if="playbackRate !== 1">{{ playbackRate }}x</span>
                <span class="buffer-tag" v-if="downloadSpeed">{{ downloadSpeed }}</span>
                <span class="buffer-tag" v-if="bufferPercent > 0">缓冲 {{ bufferPercent }}%</span>
                <button class="proxy-toggle" @click.stop="toggleProxy" :title="useProxy ? '代理加速' : '直连'">
                  {{ useProxy ? '加速' : '直连' }}
                </button>
                <button class="dashboard-toggle" @click.stop="showDashboard = !showDashboard" title="观感仪表盘">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                </button>
                <div v-if="showDashboard" class="dashboard-panel" @click.stop>
                  <div class="dashboard-row"><span class="d-label">分辨率</span><span class="d-value">{{ videoResolution || 'N/A' }}</span></div>
                  <div class="dashboard-row"><span class="d-label">下载速度</span><span class="d-value">{{ downloadSpeed || 'N/A' }}</span></div>
                  <div class="dashboard-row"><span class="d-label">缓冲进度</span><span class="d-value">{{ bufferPercent }}%</span></div>
                  <div class="dashboard-row"><span class="d-label">倍速</span><span class="d-value">{{ playbackRate }}x</span></div>
                  <div class="dashboard-row"><span class="d-label">播放时长</span><span class="d-value">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span></div>
                  <div class="dashboard-row"><span class="d-label">代理模式</span><span class="d-value">{{ useProxy ? '代理加速' : '直连' }}</span></div>
                </div>
              </div>
              <div v-if="isBuffering" class="buffering-indicator">
                <div class="buffering-spinner"></div>
                <span class="buffering-text" v-if="downloadSpeed">{{ downloadSpeed }}</span>
              </div>

              <!-- Custom Controls -->
              <div v-if="showControls" class="player-controls" @click.stop>
                <div ref="progressBoxRef" class="controls-progress" :class="{ dragging: uiSeeking }"
                  @mousedown.stop.prevent="onProgressDown" @click.stop>
                  <div class="progress-track">
                    <div class="progress-buffered" :style="{ width: displayBufferPercent + '%' }"></div>
                    <div class="progress-played" :style="{ width: displayProgressPercent + '%' }"></div>
                    <div class="progress-thumb" :style="{ left: displayProgressPercent + '%' }"></div>
                  </div>
                </div>
                <div class="controls-bottom">
                  <div class="controls-left">
                    <button class="ctrl-btn" @click="togglePlay" :title="isPlaying ? '暂停' : '播放'">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                        <polygon v-if="!isPlaying" points="5,3 19,12 5,21" />
                        <template v-else>
                          <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
                        </template>
                      </svg>
                    </button>
                    <span class="time-display">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
                  </div>
                  <div class="controls-center">
                    <button class="ctrl-btn" @click="skip(-10)" title="后退10秒">↺ 10</button>
                    <button class="ctrl-btn" @click="skip(10)" title="快进10秒">10 ↻</button>
                  </div>
                  <div class="controls-right">
                    <div class="ctrl-group">
                      <button class="ctrl-btn" @click="showSpeedMenu = !showSpeedMenu" title="倍速">{{ playbackRate }}x</button>
                      <div v-if="showSpeedMenu" class="ctrl-dropdown speed-menu">
                        <button v-for="r in PLAYBACK_RATES" :key="r" :class="['dropdown-item', { active: playbackRate === r }]"
                          @click="setPlaybackRate(r); showSpeedMenu = false">{{ r }}x</button>
                      </div>
                    </div>
                    <div class="ctrl-group" v-if="availableResolutions.length">
                      <button class="ctrl-btn" @click="showQualityMenu = !showQualityMenu" title="清晰度">
                        {{ currentResLabel }}
                      </button>
                      <div v-if="showQualityMenu" class="ctrl-dropdown quality-menu">
                        <button class="dropdown-item" :class="{ active: currentResolution === -1 }"
                          @click="setResolution(-1); showQualityMenu = false">自动</button>
                        <button v-for="r in availableResolutions" :key="r.value" :class="['dropdown-item', { active: currentResolution === r.value }]"
                          @click="setResolution(r.value); showQualityMenu = false">{{ r.label }}</button>
                      </div>
                    </div>
                    <div class="ctrl-group">
                      <button class="ctrl-btn" :class="{ active: activeSubtitle >= 0 }" @click="showSubtitleMenu = !showSubtitleMenu" title="字幕">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 13h4M6 16h8M14 13h4M18 16h1"/>
                        </svg>
                      </button>
                      <div v-if="showSubtitleMenu" class="ctrl-dropdown subtitle-menu" @click.stop>
                        <div class="dropdown-item" :class="{ active: activeSubtitle === -1 }" @click="selectSubtitle(-1); showSubtitleMenu = false">关闭字幕</div>
                        <div v-for="s in embeddedSubtitles" :key="s.index" class="dropdown-item" :class="{ active: activeSubtitle === s.index }"
                          @click="selectSubtitle(s.index); showSubtitleMenu = false">{{ s.label }}</div>
                        <div class="dropdown-item" @click="onImportSubtitle">导入字幕 (.srt/.vtt)</div>
                        <div class="dropdown-item">
                          <label>字号 <input type="range" min="12" max="36" step="2" :value="subtitleSize" @input="setSubtitleSize(parseInt(($event.target as HTMLInputElement).value))" style="width:70px" /></label>
                        </div>
                      </div>
                    </div>
                    <div class="ctrl-group">
                      <button class="ctrl-btn" @click="showDanmakuMenu = !showDanmakuMenu" :class="{ active: danmakuEnabled }" title="弹幕">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="12" r="2"/><path d="M10 12h4"/></svg>
                      </button>
                      <div v-if="showDanmakuMenu" class="ctrl-dropdown danmaku-menu" @click.stop>
                        <div class="dropdown-item" @click="toggleDanmaku">{{ danmakuEnabled ? '关闭弹幕' : '开启弹幕' }}</div>
                        <div class="dropdown-item">
                          <label>透明度 <input type="range" min="0.1" max="1" step="0.1" :value="danmakuOpacity" @input="danmakuOpacity = parseFloat(($event.target as HTMLInputElement).value)" style="width:60px" /></label>
                        </div>
                        <div class="dropdown-item">
                          <label>速度 <input type="range" min="0.5" max="2" step="0.25" :value="danmakuSpeed" @input="danmakuSpeed = parseFloat(($event.target as HTMLInputElement).value)" style="width:60px" /></label>
                        </div>
                        <div class="dropdown-item">
                          <label>区域 <select :value="danmakuArea" @change="danmakuArea = ($event.target as HTMLSelectElement).value as any">
                            <option value="full">全部</option><option value="top">顶部</option><option value="bottom">底部</option>
                          </select></label>
                        </div>
                        <div class="dropdown-item" @click="importDanmaku">导入弹幕文件</div>
                      </div>
                    </div>
                    <button class="ctrl-btn" @click="togglePip" title="画中画">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="2" y="3" width="20" height="14" rx="2" /><rect x="11" y="9" width="9" height="6" rx="1" />
                      </svg>
                    </button>
                    <button class="ctrl-btn" @click="toggleFullscreen" title="全屏">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path v-if="!isFullscreen" d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                        <path v-else d="M8 3v3a2 2 0 0 1-2 2H3m0 0h18M3 3v18" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

              <!-- Auto-next overlay -->
              <div v-if="showAutoNext" class="auto-next-overlay" @click.stop="onAutoNext">
                <div class="auto-next-box">
                  <div class="auto-next-info">下一集即将播放 ({{ autoNextCountdown }})</div>
                  <button class="auto-next-btn">播放下一集 →</button>
                  <button class="auto-next-cancel" @click.stop="cancelAutoNext">取消</button>
                </div>
              </div>
            </div>
            <div class="current-ep">{{ currentEpName }}</div>
          </div>
          <div v-else class="player-placeholder" @click="playFirst">
            <img :src="imgUrl(detail.vod_pic, detail.vod_name) || defaultPic" class="placeholder-bg" />
            <div class="placeholder-overlay">
              <span class="play-big">▶</span>
              <p>点击选择剧集播放</p>
            </div>
          </div>
        </div>
      </div>

      <div class="info-column">
        <div class="info-section">
          <div class="title-row">
            <h1>{{ detail.vod_name }}</h1>
            <button class="change-btn" @click="openSourceSwitch">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px;margin-right:3px"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
              换源
            </button>
            <button :class="['fav-btn', { active: isKeep }]" @click="toggleKeep">
              <span class="fav-text">{{ isKeep ? '♥ 已收藏' : '♡ 收藏' }}</span>
            </button>
          </div>

          <n-modal v-model:show="showSourceModal" title="切换播放源" :mask-closable="true" preset="card" style="max-width:560px">
            <n-input v-model:value="sourceKeyword" placeholder="搜索其他站点的同片资源..." clearable @keyup.enter="doSearchSources" style="margin-bottom:12px" />
            <n-button @click="doSearchSources" :loading="sourcesLoading" size="small" style="margin-bottom:12px">搜索</n-button>
            <div v-if="sources.length === 0 && !sourcesLoading" style="text-align:center;padding:20px;color:#888">输入关键词搜索其他源</div>
            <div v-for="s in sources" :key="s._site_key + s.vod_id" class="source-item" @click="switchToSource(s)">
              <img :src="imgUrl(s.vod_pic, s.vod_name) || defaultPic" class="source-pic" />
              <div class="source-info">
                <div class="source-name">{{ s.vod_name }}</div>
                <div class="source-site">{{ s._site_name || s._site_key }}</div>
              </div>
            </div>
          </n-modal>

          <div class="info-meta">
            <n-tag v-if="detail.vod_year" size="small">{{ detail.vod_year }}</n-tag>
            <n-tag v-if="detail.vod_area" size="small">{{ detail.vod_area }}</n-tag>
            <n-tag v-if="detail.vod_type" size="small">{{ detail.vod_type }}</n-tag>
          </div>
          <div v-if="detail.vod_director" class="info-row"><span class="label">导演：</span>{{ detail.vod_director }}</div>
          <div v-if="detail.vod_actor" class="info-row"><span class="label">主演：</span>{{ detail.vod_actor }}</div>
          <div v-if="plainContent" class="info-desc">
            <n-ellipsis :line-clamp="3" :tooltip="false">{{ plainContent }}</n-ellipsis>
          </div>
        </div>
      </div>

      <div v-if="flags.length" class="play-section">
        <n-tabs v-model:value="activeFlag" type="line" animated>
          <n-tab-pane v-for="f in flags" :key="f.flag" :name="f.flag" :tab="f.name">
            <div class="episode-grid">
              <button
                v-for="(ep, idx) in f.episodes"
                :key="idx"
                :class="['ep-btn', { active: currentUrl === ep.url }]"
                @click="playEpisode(f.flag, ep, idx)"
              >
                {{ ep.name }}
              </button>
            </div>
          </n-tab-pane>
        </n-tabs>
      </div>
    </div>

    <div v-else-if="loading" class="loading-fullscreen">
      <div class="loading-spinner"></div>
      <p class="loading-text">正在加载详情...</p>
    </div>

    <div v-else-if="!detail" class="loading-area">
      <div class="skeleton-info">
        <n-skeleton width="60%" :height="32" />
        <n-skeleton width="40%" :height="20" style="margin-top:12px" />
        <n-skeleton width="100%" :height="80" style="margin-top:16px" />
      </div>
      <n-skeleton width="100%" :height="200" style="margin-top:20px" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NTag, NTabs, NTabPane, NEllipsis, NEmpty, NSkeleton, NModal, NInput, NButton } from 'naive-ui'
import { imgUrl } from '@/api/img'
import { usePlayer } from '@/composables/usePlayer'
import { useDanmaku } from '@/composables/useDanmaku'

const route = useRoute()
const router = useRouter()
const {
  videoRef, videoResolution, bufferPercent, isBuffering, downloadSpeed,
  initPlayer, setupVideoEvents, resetVideoInfo, useProxy,
  currentTime, duration, uiSeeking, playbackRate, isPlaying, showControls,
  isFullscreen, availableResolutions, currentResolution, autoNextCallback, playErrorCallback,
  embeddedSubtitles, activeSubtitle, subtitleSize,
  progressBoxRef, displayProgressPercent, displayBufferPercent, onProgressDown,
  PLAYBACK_RATES,
  setPlaybackRate, togglePlay, skip, toggleFullscreen, togglePip,
  setResolution, setupKeyboardShortcuts, removeKeyboardShortcuts,
  startControlsTimer, toggleControls, savePrefs,
  selectSubtitle, importSubtitleFile, setSubtitleSize,
} = usePlayer()

const {
  danmakuEnabled, danmakuOpacity, danmakuSpeed, danmakuArea, danmakuVisible, danmakuItems,
  initDanmaku, loadDanmaku, startDanmaku, toggleDanmaku, seekDanmaku, destroyDanmaku,
} = useDanmaku()

const flags = ref<{ flag: string; name: string; episodes: { name: string; url: string }[] }[]>([])
const activeFlag = ref('')
const currentUrl = ref('')
const currentEpName = ref('')
const currentEpIdx = ref(-1)
const detail = ref<any>(null)
const siteKey = ref('')
const isKeep = ref(false)
const loading = ref(false)
const defaultPic = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140"><rect fill="%23333" width="100" height="140"/></svg>'
const showSpeedMenu = ref(false)
const showQualityMenu = ref(false)
const showDanmakuMenu = ref(false)
const showSubtitleMenu = ref(false)
const showDashboard = ref(false)
const showAutoNext = ref(false)
const autoNextCountdown = ref(5)
let autoNextTimer: ReturnType<typeof setInterval> | null = null

const showSourceModal = ref(false)
const sourceKeyword = ref('')
const sources = ref<any[]>([])
const sourcesLoading = ref(false)

const currentResLabel = computed(() => {
  if (currentResolution.value === -1) return '自动'
  const found = availableResolutions.value.find(r => r.value === currentResolution.value)
  return found ? found.label : '自动'
})

/** 部分站点简介带 HTML 标签，剥掉后展示纯文本 */
const plainContent = computed(() => {
  const raw = detail.value?.vod_content || ''
  return raw
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .trim()
})

onMounted(async () => {
  siteKey.value = route.params.site as string
  const ids = route.params.ids as string
  // 非 fallback 链进入时清空换源失败记录（正常浏览各自独立）
  if (!route.query.fallback) sessionStorage.removeItem(FALLBACK_KEY)
  await loadDetail(ids)
  setupKeyboardShortcuts()
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

// 路由参数变化（自动换源/换源弹窗在同路由记录间跳转）时组件被复用，必须手动重载
watch(() => [route.params.site, route.params.ids], async ([, ids]) => {
  if (!ids || !route.path.startsWith('/detail/')) return
  resetVideoInfo()
  cancelAutoNext()
  siteKey.value = route.params.site as string
  await loadDetail(ids as string)
})

onBeforeUnmount(() => {
  removeKeyboardShortcuts()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  cancelAutoNext()
  disarmFallbackWatchdog()
})

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

function onMouseMove() {
  startControlsTimer()
}

function formatTime(t: number): string {
  if (!t || isNaN(t)) return '00:00'
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = Math.floor(t % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

async function loadDetail(ids: string) {
  loading.value = true
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.detail(siteKey.value, ids)
    if (res.list && res.list.length > 0) {
      detail.value = res.list[0]
    }
    parseEpisodes()
    if (flags.value.length) {
      activeFlag.value = flags.value[bestFlagIndex()].flag
    }
    if (route.query.autoplay && !currentUrl.value) {
      autoPlayResume()
    }
    await checkKeep()
  } catch (e: any) {
    window.$message?.error('加载详情失败: ' + (e?.message || ''))
  } finally {
    loading.value = false
  }
}

function parseEpisodes() {
  if (!detail.value) return
  const playFrom: string[] = (detail.value.vod_play_from || '').split('$$$')
  const playUrl: string[] = (detail.value.vod_play_url || '').split('$$$')
  flags.value = playFrom.map((flag: string, i: number) => {
    const eps = (playUrl[i] || '').split('#').filter(Boolean).map((ep: string) => {
      const parts = ep.split('$')
      return { name: parts[0] || '播放', url: parts[1] || parts[0] || '' }
    }).filter((ep: { url: string }) => ep.url)
    return { flag, name: flag || `源${i + 1}`, episodes: eps }
  })
}

/** 线路名估分：默认别落在低清线路，优先 4K/蓝光 > 1080/高清 > 720/标清 > 流畅/直连 */
function flagQualityScore(name: string): number {
  const n = (name || '').toLowerCase()
  let s = 0
  if (/4k|2160|蓝光|原盘|remux/.test(n)) s += 100
  if (/1080|高清|超清|hd/.test(n)) s += 50
  if (/720|标清|sd/.test(n)) s += 20
  if (/m3u8|直连|普通|流畅/.test(n)) s += 5
  return s
}

function bestFlagIndex(): number {
  let best = 0
  for (let i = 1; i < flags.value.length; i++) {
    if (flagQualityScore(flags.value[i].name) > flagQualityScore(flags.value[best].name)) best = i
  }
  return best
}

async function checkKeep() {
  if (!detail.value) return
  try {
    const { keepAPI } = await import('@/api/vod')
    const res: any = await keepAPI.check(siteKey.value, detail.value.vod_id)
    isKeep.value = !!(res && res.is_keep)
  } catch { isKeep.value = false }
}

async function toggleKeep() {
  if (!detail.value) return
  const { keepAPI } = await import('@/api/vod')
  if (isKeep.value) {
    try {
      const listRes: any = await keepAPI.list(1, 500)
      const list = listRes?.items || []
      const found = list.find((k: any) => k.site_key === siteKey.value && k.vod_id === detail.value.vod_id)
      if (found) {
        await keepAPI.delete(found.id)
        isKeep.value = false
      }
    } catch (e: any) { window.$message?.error('取消收藏失败') }
  } else {
    try {
      await keepAPI.add({
        site_key: siteKey.value,
        vod_id: detail.value.vod_id,
        name: detail.value.vod_name,
        pic: detail.value.vod_pic || '',
      })
      isKeep.value = true
    } catch (e: any) { window.$message?.error('收藏失败') }
  }
}

function toggleProxy() {
  useProxy.value = !useProxy.value
  savePrefs()
  if (currentUrl.value) {
    window.$message?.info(useProxy.value ? '已切换为代理加速' : '已切换为直连播放')
  }
}

function openSourceSwitch() {
  sourceKeyword.value = detail.value?.vod_name || ''
  sources.value = []
  showSourceModal.value = true
  if (sourceKeyword.value) doSearchSources()
}

async function doSearchSources() {
  if (!sourceKeyword.value.trim()) return
  sourcesLoading.value = true
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.search(sourceKeyword.value.trim())
    const list = Array.isArray(res) ? res : (res?.list || res?.data || [])
    sources.value = list.filter((item: any) => item._site_key !== siteKey.value)
  } catch (e: any) {
    window.$message?.error('搜索失败: ' + (e?.message || ''))
  } finally {
    sourcesLoading.value = false
  }
}

function switchToSource(item: any) {
  showSourceModal.value = false
  const sKey = item._site_key
  const vodId = item.vod_id
  if (sKey && vodId) {
    router.push(`/detail/${sKey}/${vodId}`)
  }
}

/** 直链判定：http(s) 且以媒体扩展名结尾的 URL 直接播；其余（爬虫 id、网页地址）
 *  走 /vod/player 让 spider playerContent + 解析器解析，失败回退原始串 */
function isDirectMedia(url: string): boolean {
  return /^https?:\/\//i.test(url) && /\.(m3u8|mp4|flv|mkv|avi|ts|mpd|mov|webm)(\?|#|$)/i.test(url)
}

async function resolvePlayUrl(url: string): Promise<{ url: string; headers?: Record<string, string> }> {
  if (isDirectMedia(url)) return { url }
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.player(siteKey.value, activeFlag.value, url)
    const real = res?.url || res?.data?.url
    if (typeof real === 'string' && real) return { url: real, headers: res?.headers || res?.data?.headers }
  } catch { /* 解析失败回退原始地址 */ }
  return { url }
}

// ---------- 播放失败自动降级：同片切线路 → 跨站自动换源 ----------
const FALLBACK_KEY = 'fongmi_play_fallback'
const MAX_FALLBACK = 3
const FALLBACK_WATCHDOG_MS = 20000
let playErrorLatch = false
let fallbackWatchdog: ReturnType<typeof setTimeout> | null = null

function loadFallbackState(): { failed: string[]; count: number } {
  try {
    const s = JSON.parse(sessionStorage.getItem(FALLBACK_KEY) || '')
    return { failed: Array.isArray(s?.failed) ? s.failed : [], count: s?.count || 0 }
  } catch { return { failed: [], count: 0 } }
}

/** 长时间无画面也视为失败（地址悬挂不触发 error 事件的场景） */
function armFallbackWatchdog() {
  if (fallbackWatchdog) clearTimeout(fallbackWatchdog)
  fallbackWatchdog = setTimeout(() => {
    const el = videoRef.value
    if (el && !isPlaying.value && (el.currentTime || 0) < 1) onPlayError()
  }, FALLBACK_WATCHDOG_MS)
}

function disarmFallbackWatchdog() {
  if (fallbackWatchdog) { clearTimeout(fallbackWatchdog); fallbackWatchdog = null }
}

async function onPlayError() {
  if (playErrorLatch || !detail.value) return
  playErrorLatch = true
  disarmFallbackWatchdog()
  // 1) 同片换线路：按集名在其它线路找回同一集，其次退同序号
  const epName = currentEpName.value
  const curIdx = currentEpIdx.value
  for (const f of flags.value) {
    if (f.flag === activeFlag.value) continue
    let idx = f.episodes.findIndex(e => e.name === epName)
    if (idx < 0 && curIdx >= 0 && curIdx < f.episodes.length) idx = curIdx
    if (idx >= 0) {
      window.$message?.info(`当前线路播放失败，已切换到线路「${f.name}」`)
      playEpisode(f.flag, f.episodes[idx], idx)
      return
    }
  }
  // 2) 跨站自动换源：片名精确匹配其它站点（原版 VodFallbackPolicy 的 mismatch 策略），
  //    失败过的源记入 sessionStorage 防回环，整链最多 MAX_FALLBACK 次
  const state = loadFallbackState()
  if (state.count >= MAX_FALLBACK) {
    window.$message?.error('多次换源仍播放失败，请手动换源')
    return
  }
  try {
    const { vodAPI } = await import('@/api/vod')
    const res: any = await vodAPI.search(detail.value.vod_name || '')
    const list = Array.isArray(res) ? res : (res?.merged || [])
    const next = list.find((v: any) =>
      (v.vod_name || '').trim() === (detail.value.vod_name || '').trim() &&
      v._site_key && v._site_key !== siteKey.value &&
      !state.failed.includes(`${v._site_key}:${v.vod_id}`))
    if (!next) {
      window.$message?.error('播放失败，且没有其它可自动切换的源')
      return
    }
    state.failed.push(`${siteKey.value}:${detail.value.vod_id}`)
    state.count += 1
    sessionStorage.setItem(FALLBACK_KEY, JSON.stringify(state))
    window.$message?.info(`已自动切换到源「${next._site_name || next._site_key}」`)
    router.replace(`/detail/${next._site_key}/${next.vod_id}?autoplay=1&fallback=1`)
  } catch {
    window.$message?.error('播放失败，自动换源出错')
  }
}

// 播放成功即终结换源链
watch(isPlaying, (playing) => {
  if (playing) {
    disarmFallbackWatchdog()
    sessionStorage.removeItem(FALLBACK_KEY)
  }
})

async function playEpisode(flag: string, ep: { name: string; url: string }, idx?: number) {
  activeFlag.value = flag
  currentUrl.value = ep.url
  currentEpName.value = ep.name
  currentEpIdx.value = idx ?? -1
  cancelAutoNext()
  showSpeedMenu.value = false
  showQualityMenu.value = false
  showDanmakuMenu.value = false
  showSubtitleMenu.value = false
  resetVideoInfo()
  playErrorLatch = false
  if (danmakuEnabled.value) {
    destroyDanmaku()
    seekDanmaku(0)
  }
  setTimeout(async () => {
    setupVideoEvents()
    setupPositionTracking()
    const final = await resolvePlayUrl(ep.url)
    initPlayer(final.url, final.headers)
    checkHistoryPosition()
    autoNextCallback.value = onAutoNextTriggered
    playErrorCallback.value = onPlayError
    armFallbackWatchdog()
    if (danmakuVisible.value && videoRef.value) {
      initDanmaku(videoRef.value as HTMLElement)
      startDanmaku()
    }
  }, 100)
  saveHistory(ep.url, ep.name)
}

function playFirst() {
  if (flags.value.length && flags.value[bestFlagIndex()].episodes.length) {
    const f = flags.value[bestFlagIndex()]
    playEpisode(f.flag, f.episodes[0], 0)
  }
}

/** autoplay 模式：优先续看历史记录那一集，找不到再播第一集 */
async function autoPlayResume() {
  let played = false
  try {
    const { historyAPI } = await import('@/api/vod')
    const res: any = await historyAPI.check(siteKey.value, detail.value?.vod_id ?? '')
    if (res?.found && res.episode) {
      for (const f of flags.value) {
        const idx = f.episodes.findIndex(e => e.url === res.episode)
        if (idx >= 0) {
          playEpisode(f.flag, f.episodes[idx], idx)
          played = true
          break
        }
      }
    }
  } catch { /* ignore */ }
  if (!played) playFirst()
}

function onAutoNextTriggered() {
  const currentFlag = flags.value.find(f => f.flag === activeFlag.value)
  if (!currentFlag || currentEpIdx.value < 0) return
  const nextIdx = currentEpIdx.value + 1
  if (nextIdx < currentFlag.episodes.length) {
    showAutoNext.value = true
    autoNextCountdown.value = 5
    autoNextTimer = setInterval(() => {
      autoNextCountdown.value--
      if (autoNextCountdown.value <= 0) {
        cancelAutoNext()
        playEpisode(activeFlag.value, currentFlag.episodes[nextIdx], nextIdx)
      }
    }, 1000)
  }
}

function onAutoNext() {
  cancelAutoNext()
  const currentFlag = flags.value.find(f => f.flag === activeFlag.value)
  if (!currentFlag || currentEpIdx.value < 0) return
  const nextIdx = currentEpIdx.value + 1
  if (nextIdx < currentFlag.episodes.length) {
    playEpisode(activeFlag.value, currentFlag.episodes[nextIdx], nextIdx)
  }
}

function cancelAutoNext() {
  showAutoNext.value = false
  if (autoNextTimer) {
    clearInterval(autoNextTimer)
    autoNextTimer = null
  }
}

function importDanmaku() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xml,.txt'
  input.onchange = async (e: any) => {
    const file = e.target?.files?.[0]
    if (!file) return
    const text = await file.text()
    loadDanmaku(text)
    if (videoRef.value) {
      initDanmaku(videoRef.value as HTMLElement)
      if (!danmakuEnabled.value) {
        startDanmaku()
      }
    }
    showDanmakuMenu.value = false
    window.$message?.success(`已导入弹幕: ${danmakuItems.value.length} 条`)
  }
  input.click()
}

function onImportSubtitle() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.srt,.vtt'
  input.onchange = async (e: any) => {
    const file = e.target?.files?.[0]
    if (!file) return
    const ok = await importSubtitleFile(file)
    showSubtitleMenu.value = false
    if (ok) window.$message?.success(`字幕已加载: ${file.name}`)
    else window.$message?.error('字幕加载失败')
  }
  input.click()
}

async function saveHistory(url: string, _name: string) {
  const { historyAPI } = await import('@/api/vod')
  await historyAPI.add({
    site_key: siteKey.value,
    vod_id: detail.value.vod_id,
    name: detail.value.vod_name,
    pic: detail.value.vod_pic || '',
    episode: url,
  })
}

function setupPositionTracking() {
  const el = videoRef.value
  if (!el) return
  el.ontimeupdate = throttle(() => {
    if (el && el.duration > 0 && currentUrl.value) {
      savePosition(el.currentTime, el.duration)
    }
  }, 10000)
}

function savePosition(currentTime: number, duration: number) {
  import('@/api/vod').then(mod => {
    mod.historyAPI.add({
      site_key: siteKey.value,
      vod_id: detail.value.vod_id,
      position: Math.floor(currentTime * 1000),
      duration: Math.floor(duration * 1000),
    })
  }).catch(() => {})
}

async function checkHistoryPosition() {
  try {
    const { historyAPI } = await import('@/api/vod')
    const res: any = await historyAPI.check(siteKey.value, detail.value.vod_id)
    if (res && res.found && res.position) {
      setTimeout(() => {
        if (videoRef.value) {
          videoRef.value.currentTime = res.position / 1000
        }
      }, 500)
    }
  } catch { /* ignore */ }
}

function throttle(fn: (...args: any[]) => void, delay: number) {
  let last = 0
  return (...args: any[]) => {
    const now = Date.now()
    if (now - last >= delay) { last = now; fn(...args) }
  }
}
</script>

<style scoped>
.detail-page { padding: 20px; max-width: 1500px; margin: 0 auto; }
.detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  grid-template-areas: "player info" "episodes episodes";
  gap: 20px;
  align-items: start;
}

.player-column { grid-area: player; position: relative; }
.player-sticky { position: sticky; top: 20px; }
.info-column { grid-area: info; min-width: 0; }
.play-section { grid-area: episodes; }

/* 固定 16:9 视窗：元数据加载前后高度恒定，超高时按 62vh 限高并居中 */
.video-wrapper {
  position: relative;
  width: 100%;
  max-width: calc(62vh * 16 / 9);
  aspect-ratio: 16 / 9;
  margin: 0 auto;
  background: #000;
}
.detail-video {
  position: absolute; top: 0; left: 0;
  width: 100%; height: 100%;
  object-fit: contain;
  background: #000;
  border-radius: 8px;
}

/* 全屏：视频铺满整屏，比例不符时由 object-fit 留黑边，而不是压在小框里 */
.video-wrapper:fullscreen { background: #000; border-radius: 0; aspect-ratio: auto; max-width: none; }
.video-wrapper:fullscreen video {
  width: 100% !important;
  height: 100% !important;
  max-height: none !important;
  border-radius: 0 !important;
  object-fit: contain;
}

@media (max-width: 1024px) {
  .detail-layout { grid-template-columns: 1fr; grid-template-areas: "player" "info" "episodes"; }
  .player-sticky { position: static; }
  .video-wrapper { max-width: calc(60vh * 16 / 9); }
}
.player-container { background: #000; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.4); position: relative; }

.player-top-bar {
  position: absolute; top: 0; left: 0; right: 0; padding: 8px 12px;
  background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent);
  display: flex; gap: 8px; align-items: center; z-index: 20;
}
.resolution-tag { font-size: 11px; color: #aaa; background: rgba(0,0,0,0.5); padding: 2px 8px; border-radius: 8px; }
.speed-tag { font-size: 11px; color: #0ae; background: rgba(0,0,0,0.5); padding: 2px 8px; border-radius: 8px; }
.buffer-tag { font-size: 11px; color: #8f8; background: rgba(0,0,0,0.5); padding: 2px 8px; border-radius: 8px; margin-left: auto; }
.proxy-toggle {
  font-size: 10px; color: #0ae; background: rgba(0,0,0,0.5); border: 1px solid rgba(0,170,238,0.4);
  padding: 1px 8px; border-radius: 8px; cursor: pointer; line-height: 1.6;
}
.proxy-toggle:hover { background: rgba(0,170,238,0.2); }
.dashboard-toggle { font-size: 10px; color: #aaa; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.15); padding: 2px 6px; border-radius: 8px; cursor: pointer; line-height: 1.4; position: relative; }
.dashboard-toggle:hover { border-color: var(--n-primary-color); color: #fff; }
.dashboard-panel { position: absolute; top: 100%; right: 0; margin-top: 4px; background: rgba(20,20,30,0.95); border-radius: 8px; padding: 8px 12px; min-width: 200px; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); z-index: 30; }
.dashboard-row { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; font-size: 11px; }
.dashboard-row .d-label { color: #888; }
.dashboard-row .d-value { color: #ddd; }

.buffering-indicator {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  display: flex; flex-direction: column; align-items: center; gap: 8px; z-index: 10;
}
.buffering-spinner { width: 36px; height: 36px; border: 3px solid rgba(255,255,255,0.2); border-top-color: #fff; border-radius: 50%; animation: spin 0.8s linear infinite; }
.buffering-text { font-size: 11px; color: #aaa; }

.player-controls {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.85), transparent);
  padding: 8px 12px 4px; z-index: 20; transition: opacity 0.3s;
}
.controls-progress { margin-bottom: 4px; cursor: pointer; padding: 8px 0; }
.progress-track { position: relative; height: 4px; background: rgba(255,255,255,0.15); border-radius: 2px; transition: height 0.15s; }
.controls-progress:hover .progress-track, .controls-progress.dragging .progress-track { height: 6px; }
/* 已播放=主题蓝实心，已缓冲=半透明白，轨道=更暗的底色，三层颜色明显区分 */
.progress-played { position: absolute; left: 0; top: 0; height: 100%; background: var(--n-primary-color); border-radius: 2px; z-index: 3; transition: width 0.1s linear; }
.progress-buffered { position: absolute; left: 0; top: 0; height: 100%; background: rgba(255,255,255,0.4); border-radius: 2px; z-index: 2; transition: width 0.3s linear; }
.controls-progress.dragging .progress-played, .controls-progress.dragging .progress-buffered { transition: none; }
.progress-thumb { position: absolute; top: 50%; width: 12px; height: 12px; border-radius: 50%; background: #fff; transform: translate(-50%, -50%); z-index: 4; box-shadow: 0 0 4px rgba(0,0,0,0.5); display: none; }
.controls-progress:hover .progress-thumb, .controls-progress.dragging .progress-thumb { display: block; }
.controls-progress.dragging { cursor: grabbing; }

.controls-bottom { display: flex; align-items: center; gap: 8px; }
.controls-left { display: flex; align-items: center; gap: 8px; }
.controls-center { display: flex; gap: 4px; }
.controls-right { display: flex; align-items: center; gap: 4px; margin-left: auto; }
.ctrl-btn {
  background: transparent; border: none; color: #ddd; cursor: pointer; padding: 4px 8px;
  border-radius: 4px; font-size: 12px; display: flex; align-items: center; gap: 2px;
}
.ctrl-btn:hover { background: rgba(255,255,255,0.1); color: #fff; }
.ctrl-btn.active { color: var(--n-primary-color); }
.time-display { font-size: 12px; color: #aaa; }

.ctrl-group { position: relative; }
.ctrl-dropdown { position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); margin-bottom: 4px; background: rgba(30,30,40,0.95); border-radius: 8px; padding: 4px; display: flex; flex-direction: column; gap: 2px; min-width: 80px; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); z-index: 30; }
.dropdown-item { background: transparent; border: none; color: #bbb; padding: 4px 12px; cursor: pointer; font-size: 12px; border-radius: 4px; white-space: nowrap; }
.dropdown-item:hover { background: rgba(255,255,255,0.1); color: #fff; }
.dropdown-item.active { color: var(--n-primary-color); background: rgba(0,170,238,0.15); }

.current-ep { text-align: center; padding: 6px; font-size: 13px; color: #888; }

.auto-next-overlay {
  position: absolute; bottom: 60px; right: 12px; z-index: 25;
}
.auto-next-box {
  background: rgba(20,20,30,0.95); border-radius: 10px; padding: 14px 18px;
  text-align: center; border: 1px solid rgba(255,255,255,0.1);
}
.auto-next-info { font-size: 12px; color: #aaa; margin-bottom: 8px; }
.auto-next-btn { padding: 6px 20px; background: var(--n-primary-color); border: none; border-radius: 6px; color: #fff; cursor: pointer; font-size: 13px; }
.auto-next-btn:hover { opacity: 0.9; }
.auto-next-cancel { display: block; margin: 4px auto 0; background: transparent; border: none; color: #888; cursor: pointer; font-size: 11px; }

.player-placeholder { position: relative; aspect-ratio: 16/9; border-radius: 12px; overflow: hidden; cursor: pointer; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
.placeholder-bg { width: 100%; height: 100%; object-fit: cover; filter: brightness(0.3); }
.placeholder-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; }
.play-big { width: 64px; height: 64px; background: rgba(255,255,255,0.9); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px; color: #333; padding-left: 6px; transition: transform 0.2s; }
.player-placeholder:hover .play-big { transform: scale(1.1); }
.placeholder-overlay p { color: #ccc; font-size: 13px; }

.info-section { background: var(--n-card-color); border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.title-row { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
.title-row h1 { flex: 1; font-size: 22px; margin: 0; }
.change-btn { flex-shrink: 0; display: flex; align-items: center; gap: 2px; padding: 6px 12px; border: 1px solid var(--n-border-color); border-radius: 20px; background: transparent; cursor: pointer; transition: all 0.2s; font-size: 12px; color: #ccc; }
.change-btn:hover { border-color: #0ae; color: #0ae; }

.source-item { display: flex; gap: 12px; padding: 10px; border-radius: 8px; cursor: pointer; transition: background 0.2s; align-items: center; }
.source-item:hover { background: rgba(255,255,255,0.05); }
.source-pic { width: 48px; height: 64px; object-fit: cover; border-radius: 4px; background: #222; }
.source-info { flex: 1; min-width: 0; }
.source-name { font-size: 14px; color: #eee; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-site { font-size: 12px; color: #888; margin-top: 2px; }

.fav-btn { flex-shrink: 0; display: flex; align-items: center; gap: 4px; padding: 6px 12px; border: 1px solid var(--n-border-color); border-radius: 20px; background: transparent; cursor: pointer; transition: all 0.2s; font-size: 12px; }
.fav-btn:hover { border-color: #f5222d; color: #f5222d; }
.fav-btn.active { border-color: #f5222d; background: rgba(245,34,45,0.1); color: #f5222d; }
.fav-text { white-space: nowrap; }

.info-meta { display: flex; gap: 6px; margin-bottom: 12px; }
.info-row { font-size: 14px; color: #aaa; margin-bottom: 6px; }
.info-row .label { color: #666; }
.info-desc { font-size: 13px; color: #aaa; line-height: 1.6; margin-top: 8px; }

.play-section { background: var(--n-card-color); border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.episode-grid { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 0; }
.ep-btn { padding: 6px 14px; border: 1px solid var(--n-border-color); border-radius: 6px; background: transparent; cursor: pointer; font-size: 12px; transition: all 0.2s; color: #ccc; }
.ep-btn:hover { border-color: var(--n-primary-color); color: var(--n-primary-color); }
.ep-btn.active { background: var(--n-primary-color); border-color: var(--n-primary-color); color: #fff; }

.empty-tip { display: flex; justify-content: center; padding: 60px 0; }
.loading-fullscreen { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 60vh; gap: 16px; }
.loading-spinner { width: 40px; height: 40px; border: 3px solid rgba(255,255,255,0.1); border-top-color: var(--n-primary-color); border-radius: 50%; animation: spin 0.8s linear infinite; }
.loading-text { font-size: 14px; color: #888; }
.loading-area { padding: 20px; }
.skeleton-info { background: var(--n-card-color); border-radius: 12px; padding: 20px; }

.fade-in { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes spin { to { transform: rotate(360deg); } }
</style>