<template>
  <div class="player-shell" :class="{ 'page-fullscreen': pageFullscreen }">
    <div v-if="loading" class="empty-state">
      <n-spin size="large" />
    </div>

    <div v-else-if="!video" class="empty-state">
      <n-empty description="视频不存在或已被移除">
        <template #extra>
          <n-button type="primary" @click="$router.push('/local')">返回片库</n-button>
        </template>
      </n-empty>
    </div>

    <template v-else>
      <div class="player-wrap">
        <video ref="videoEl" playsinline crossorigin="anonymous"></video>
        <div v-if="enableTouchSeek" ref="seekOverlay" class="seek-overlay">
          <div ref="seekFeedback" class="seek-toast" :class="{ show: feedbackShow, 'is-forward': feedbackMode === 'forward', 'is-back': feedbackMode === 'back' }">
            <svg viewBox="0 0 24 24" v-if="feedbackMode === 'forward'"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
            <svg viewBox="0 0 24 24" v-else><path d="M18 18L9.5 12 18 6v12zM6 6h2v12H6z"/></svg>
            <span>{{ feedbackMode === 'forward' ? '快进' : '后退' }}中</span>
            <span class="t-time">{{ feedbackTime }}</span>
          </div>
        </div>
      </div>

      <div class="player-info">
        <h1 class="player-title">{{ video.name }}</h1>
        <div class="player-sub">
          <span v-if="video.duration">时长 {{ formatDuration(video.duration) }}</span>
          <span v-if="video.width" class="sep">|</span>
          <span v-if="video.width">{{ video.width }}×{{ video.height }}</span>
          <span v-if="video.codec" class="sep">|</span>
          <span v-if="video.codec">{{ video.codec.toUpperCase() }}</span>
          <span v-if="video.size" class="sep">|</span>
          <span v-if="video.size">{{ formatSize(video.size) }}</span>
        </div>

        <div class="player-nav">
          <n-button size="small" @click="$router.push('/local')">← 返回片库</n-button>
          <n-button v-if="prev" size="small" @click="goto(prev)">← 上一个</n-button>
          <n-button v-if="next" size="small" @click="goto(next)">下一个 →</n-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NEmpty, NSpin } from 'naive-ui'
import Plyr from 'plyr'
import 'plyr/dist/plyr.css'
import { localAPI } from '@/api/local'

const props = defineProps<{ id: string }>()
const router = useRouter()

const videoEl = ref<HTMLVideoElement | null>(null)
const video = ref<any>(null)
const prev = ref<any>(null)
const next = ref<any>(null)
const loading = ref(true)
const enableTouchSeek = ref(false)
const seekOverlay = ref<HTMLDivElement | null>(null)
const seekFeedback = ref<HTMLDivElement | null>(null)
const feedbackShow = ref(false)
const feedbackMode = ref<'forward' | 'back'>('forward')
const feedbackTime = ref('')
const pageFullscreen = ref(false)
let player: any = null
let playlist: any[] = []
const touchState: { timer: number | null; seekTimer: number | null; mode: 'forward' | 'back' | null; startX: number } = { timer: null, seekTimer: null, mode: null, startX: 0 }
const keyboardState: { timer: number | null; mode: 'forward' | 'back' | null } = { timer: null, mode: null }

const FULLSCREEN_IN = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-5v2h5v-5h-2v3zm-2-7h-2v3h-3v2h5v-5z"/></svg>'
const FULLSCREEN_OUT = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/></svg>'

function formatDuration(seconds: number) {
  if (seconds === null || seconds === undefined || isNaN(seconds)) return '--:--'
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  return `${m}:${String(sec).padStart(2, '0')}`
}

function formatSize(bytes: number) {
  if (bytes === null || bytes === undefined) return ''
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

function stepSeek(direction: 'forward' | 'back') {
  const media = player?.media
  if (!media) return
  const d = media.duration
  if (direction === 'forward') {
    media.currentTime = Math.min(d, media.currentTime + 1)
  } else {
    media.currentTime = Math.max(0, media.currentTime - 1)
  }
  feedbackTime.value = formatDuration(media.currentTime)
}

function startSeek(media: HTMLMediaElement) {
  stepSeek(touchState.mode!)
  touchState.seekTimer = window.setInterval(() => stepSeek(touchState.mode!), 200)
  feedbackShow.value = true
}

function stopSeek() {
  clearTimeout(touchState.timer ?? undefined)
  clearInterval(touchState.seekTimer ?? undefined)
  clearInterval(keyboardState.timer ?? undefined)
  touchState.seekTimer = null
  touchState.mode = null
  keyboardState.timer = null
  keyboardState.mode = null
  feedbackShow.value = false
}

function cancelSeek() { stopSeek() }

function startKeyboardSeek(direction: 'forward' | 'back') {
  clearInterval(keyboardState.timer ?? undefined)
  keyboardState.mode = direction
  feedbackMode.value = direction
  stepSeek(direction)
  keyboardState.timer = window.setInterval(() => stepSeek(direction), 200)
  feedbackShow.value = true
}

function handleKeyDown(e: KeyboardEvent) {
  const target = e.target as HTMLElement
  const editable = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)
  if (editable) return
  if (e.key === 'Escape' && (pageFullscreen.value || document.fullscreenElement)) {
    e.preventDefault(); e.stopPropagation(); exitAllFullscreen(); return
  }
  if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    const dir = e.key === 'ArrowRight' ? 'forward' : 'back'
    if (keyboardState.mode === dir) return
    e.preventDefault(); e.stopPropagation(); startKeyboardSeek(dir)
  }
}

function togglePageFullscreen() {
  pageFullscreen.value = !pageFullscreen.value
  if (pageFullscreen.value) {
    requestAnimationFrame(() => { document.querySelector('.player-shell')?.getBoundingClientRect() })
  }
  updateFsIcon()
}

function exitAllFullscreen() {
  pageFullscreen.value = false
  updateFsIcon()
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {})
  }
}

function handleKeyUp(e: KeyboardEvent) {
  if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    clearInterval(keyboardState.timer ?? undefined)
    keyboardState.timer = null
    keyboardState.mode = null
    feedbackShow.value = false
  }
}

function setupTouchSeek() {
  const overlay = seekOverlay.value
  if (!overlay || !player) return
  const wrapper = videoEl.value?.closest('.plyr__video-wrapper')
  if (wrapper && overlay.parentElement !== wrapper) wrapper.appendChild(overlay)
  const media = player.media

  overlay.addEventListener('touchstart', (e: TouchEvent) => {
    const t = e.touches[0]
    touchState.startX = t.clientX
    touchState.mode = null
    clearTimeout(touchState.timer ?? undefined)
    touchState.timer = window.setTimeout(() => {
      touchState.mode = t.clientX < window.innerWidth / 2 ? 'back' : 'forward'
      feedbackMode.value = touchState.mode
      startSeek(media)
    }, 400)
  }, { passive: true })

  overlay.addEventListener('touchmove', (e: TouchEvent) => {
    if (touchState.mode) { e.preventDefault(); return }
    const dx = Math.abs(e.touches[0].clientX - touchState.startX)
    if (dx > 15) cancelSeek()
  }, { passive: false })

  overlay.addEventListener('touchend', () => { cancelSeek() })
  overlay.addEventListener('touchcancel', cancelSeek)
  overlay.addEventListener('contextmenu', (e: Event) => { e.preventDefault(); cancelSeek() })
  overlay.addEventListener('click', (e: Event) => { e.stopPropagation() })
  window.addEventListener('touchend', handleWindowTouchEnd)
  window.addEventListener('touchcancel', cancelSeek)
  window.addEventListener('keydown', handleKeyDown, true)
  window.addEventListener('keyup', handleKeyUp, true)
}

function handleWindowTouchEnd() {
  if (touchState.mode) cancelSeek()
}

function updateFsIcon() {
  const controls = player?.elements?.controls
  if (!controls) return
  const btn = [...controls.querySelectorAll('.plyr__control')].find(
    (b: Element) => b.getAttribute('aria-label') === '网页全屏',
  )
  if (btn) btn.innerHTML = pageFullscreen.value ? FULLSCREEN_OUT : FULLSCREEN_IN
}

function injectPageFullscreenButton() {
  const controlsEl = player?.elements?.controls
  if (!controlsEl) return
  const fullscreenBtn = controlsEl.querySelector('[data-plyr="fullscreen"]')
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = 'plyr__control'
  btn.setAttribute('aria-label', '网页全屏')
  btn.innerHTML = FULLSCREEN_IN
  btn.addEventListener('click', togglePageFullscreen)
  if (fullscreenBtn) controlsEl.insertBefore(btn, fullscreenBtn)
  else controlsEl.appendChild(btn)
}

function goto(v: any) {
  router.push(`/local/player/${v.id}`)
}

async function loadVideo() {
  if (player) { player.destroy(); player = null }
  loading.value = true
  video.value = null
  prev.value = null
  next.value = null
  cancelSeek()
  enableTouchSeek.value = 'ontouchstart' in window || navigator.maxTouchPoints > 0
  try {
    const v = await localAPI.video(props.id)
    video.value = v
    const data = await localAPI.videos({ sort: 'mtime', order: 'desc', limit: 1000 })
    playlist = data.items
    const idx = playlist.findIndex((x) => x.id === v.id)
    if (idx > 0) prev.value = playlist[idx - 1]
    if (idx < playlist.length - 1) next.value = playlist[idx + 1]
  } catch (e) {
    console.error(e)
    video.value = null
  } finally {
    loading.value = false
  }

  if (!video.value) return
  await nextTick()
  const el = videoEl.value
  if (!el) return
  el.src = localAPI.streamUrl(video.value.id)
  try {
    player = new Plyr(el, {
      controls: [
        'play-large', 'play', 'progress', 'current-time', 'duration',
        'mute', 'volume', 'settings', 'pip', 'fullscreen',
      ],
      settings: ['speed', 'quality'],
      speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
      keyboard: { focused: true, global: false },
      tooltips: { controls: true, seek: true },
      seekTime: 10,
      clickToPlay: false,
      disableContextMenu: true,
      resetOnEnd: false,
    })
  } catch (e) {
    console.error('Plyr 初始化失败，降级为原生播放器', e)
    player = null
  }
  if (player) injectPageFullscreenButton()
  player?.on('ended', () => {
    if (next.value) router.push(`/local/player/${next.value.id}`)
  })
  player?.on('enterfullscreen', () => { pageFullscreen.value = true; updateFsIcon() })
  player?.on('exitfullscreen', () => { pageFullscreen.value = false; updateFsIcon() })
  setupTouchSeek()
}

watch(() => props.id, () => { loadVideo() })

onMounted(async () => {
  await loadVideo()
})

onBeforeUnmount(() => {
  window.removeEventListener('touchend', handleWindowTouchEnd)
  window.removeEventListener('touchcancel', cancelSeek)
  window.removeEventListener('keydown', handleKeyDown, true)
  window.removeEventListener('keyup', handleKeyUp, true)
  if (player) player.destroy()
  player = null
  cancelSeek()
})
</script>

<style scoped>
.player-shell { max-width: 1200px; margin: 0 auto; padding: 20px; }
.player-shell.page-fullscreen { position: fixed; inset: 0; z-index: 1000; max-width: none; margin: 0; background: #000; display: flex; align-items: center; justify-content: center; padding: 0; }
.player-shell.page-fullscreen .player-wrap { width: 100vw; height: 100vh; max-height: none; border: none; border-radius: 0; box-shadow: none; display: flex; align-items: center; justify-content: center; background: #000; }
.player-shell.page-fullscreen :deep(.plyr) { width: 100%; height: 100%; max-width: 100vw; max-height: 100vh; }
.player-shell.page-fullscreen :deep(.plyr video) { width: 100%; height: 100%; max-height: none; object-fit: contain; }
.player-shell.page-fullscreen .player-info { display: none; }
.player-wrap { position: relative; border-radius: 14px; overflow: hidden; background: #000; border: 1px solid var(--n-border-color); box-shadow: 0 8px 30px rgba(0,0,0,0.45); max-height: calc(100vh - 200px); display: flex; align-items: center; justify-content: center; }
.player-wrap :deep(.plyr) { border-radius: 0; }
.player-wrap :deep(.plyr video) { object-fit: contain; height: auto; max-height: calc(100vh - 200px); }
.player-info { padding: 18px 6px 0; }
.player-title { font-size: 19px; font-weight: 600; margin-bottom: 6px; word-break: break-all; }
.player-sub { color: var(--n-text-color-3); font-size: 13px; display: flex; gap: 10px; flex-wrap: wrap; }
.player-sub .sep { opacity: 0.5; }
.player-nav { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
.seek-overlay { position: absolute; inset: 0; z-index: 1; touch-action: pan-y; -webkit-touch-callout: none; -webkit-user-select: none; user-select: none; }
@media (hover: hover) and (pointer: fine) { .seek-overlay { display: none; } }
.seek-toast { position: absolute; top: 14px; left: 50%; transform: translateX(-50%) translateY(-6px); display: flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 999px; background: rgba(10,10,16,0.66); border: 1px solid rgba(255,255,255,0.1); color: #fff; font-size: 12px; opacity: 0; transition: opacity 0.2s ease, transform 0.2s ease; pointer-events: none; z-index: 3; white-space: nowrap; }
.seek-toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
.seek-toast svg { width: 13px; height: 13px; }
.seek-toast.is-forward svg { fill: #c4b5fd; }
.seek-toast.is-back svg { fill: #67e8f9; }
.seek-toast .t-time { color: rgba(255,255,255,0.62); font-variant-numeric: tabular-nums; padding-left: 6px; border-left: 1px solid rgba(255,255,255,0.14); }
.empty-state { padding: 80px 0; display: flex; justify-content: center; align-items: center; flex-direction: column; gap: 16px; }
</style>
