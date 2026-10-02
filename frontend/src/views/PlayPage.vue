<template>
  <div class="play-page">
    <div class="player-box" @mousemove="onMouseMove" @click="toggleControls">
      <div class="video-wrapper">
        <video ref="videoRef" autoplay preload="auto" class="play-video"
          @click="togglePlay"></video>
        <div class="player-top-bar" v-if="showControls">
          <span class="resolution-tag" v-if="videoResolution">{{ videoResolution }}</span>
          <span class="speed-tag" v-if="playbackRate !== 1">{{ playbackRate }}x</span>
          <span class="buffer-tag" v-if="downloadSpeed">{{ downloadSpeed }}</span>
          <button class="proxy-toggle" @click.stop="toggleProxy" :title="useProxy ? '代理加速' : '直连'">
            {{ useProxy ? '加速' : '直连' }}
          </button>
        </div>
        <div v-if="isBuffering" class="buffering-indicator">
          <div class="buffering-spinner"></div>
          <span class="buffering-text" v-if="downloadSpeed">{{ downloadSpeed }}</span>
        </div>

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
              <button class="ctrl-btn" @click="skip(-10)">↺ 10</button>
              <button class="ctrl-btn" @click="skip(10)">10 ↻</button>
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
              <button class="ctrl-btn" @click="togglePip" title="画中画">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="3" width="20" height="14" rx="2" /><rect x="11" y="9" width="9" height="6" rx="1" />
                </svg>
              </button>
              <button class="ctrl-btn" @click="toggleFullscreen" title="全屏">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="play-controls">
      <n-button text @click="$router.back()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px;margin-right:4px">
          <path d="m15 18-6-6 6-6"/>
        </svg>
        返回
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { NButton } from 'naive-ui'
import { usePlayer } from '@/composables/usePlayer'

const route = useRoute()
const {
  videoRef, videoResolution, isBuffering, downloadSpeed,
  initPlayer, setupVideoEvents, useProxy,
  currentTime, duration, uiSeeking, playbackRate, isPlaying, showControls,
  availableResolutions, currentResolution,
  embeddedSubtitles, activeSubtitle, subtitleSize,
  progressBoxRef, displayProgressPercent, displayBufferPercent, onProgressDown,
  PLAYBACK_RATES,
  setPlaybackRate, togglePlay, skip, toggleFullscreen, togglePip,
  setResolution,
  setupKeyboardShortcuts, removeKeyboardShortcuts,
  startControlsTimer, toggleControls,
  selectSubtitle, importSubtitleFile, setSubtitleSize,
} = usePlayer()

const showSpeedMenu = ref(false)
const showQualityMenu = ref(false)
const showSubtitleMenu = ref(false)

const currentResLabel = computed(() => {
  if (currentResolution.value === -1) return '自动'
  const found = availableResolutions.value.find(r => r.value === currentResolution.value)
  return found ? found.label : '自动'
})

function toggleProxy() {
  useProxy.value = !useProxy.value
  window.$message?.info(useProxy.value ? '已切换为代理加速' : '已切换为直连播放')
  const url = route.query.url as string
  if (url && videoRef.value) {
    setupVideoEvents()
    initPlayer(url)
  }
}

function onMouseMove() {
  startControlsTimer()
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

function formatTime(t: number): string {
  if (!t || isNaN(t)) return '00:00'
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = Math.floor(t % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

onMounted(() => {
  const url = route.query.url as string
  if (!url || !videoRef.value) return
  setupVideoEvents()
  initPlayer(url)
  setupKeyboardShortcuts()
})

onBeforeUnmount(() => {
  removeKeyboardShortcuts()
})
</script>

<style scoped>
.play-page { padding: 20px; max-width: 1400px; margin: 0 auto; }
.player-box { border-radius: 12px; overflow: hidden; background: #000; position: relative; }
/* 固定 16:9 视窗：封面/视频元数据未加载时高度不抖动，超高时按 74vh 限高并居中 */
.video-wrapper {
  position: relative;
  width: 100%;
  max-width: calc(74vh * 16 / 9);
  aspect-ratio: 16 / 9;
  margin: 0 auto;
  background: #000;
}
.play-video {
  position: absolute; top: 0; left: 0;
  width: 100%; height: 100%;
  object-fit: contain;
  background: #000;
}

/* 全屏：视频铺满整屏，比例不符时由 object-fit 留黑边 */
.video-wrapper:fullscreen { background: #000; border-radius: 0; aspect-ratio: auto; max-width: none; }
.video-wrapper:fullscreen video {
  width: 100% !important;
  height: 100% !important;
  max-height: none !important;
  border-radius: 0 !important;
  object-fit: contain;
}

.player-top-bar {
  position: absolute; top: 0; left: 0; right: 0; padding: 10px 14px;
  background: linear-gradient(to bottom, rgba(0,0,0,0.6), transparent);
  display: flex; gap: 8px; align-items: center; z-index: 20; pointer-events: none;
}
.resolution-tag { font-size: 11px; color: #aaa; background: rgba(0,0,0,0.5); padding: 2px 8px; border-radius: 8px; }
.speed-tag { font-size: 11px; color: #0ae; background: rgba(0,0,0,0.5); padding: 2px 8px; border-radius: 8px; }
.buffer-tag { font-size: 11px; color: #8f8; background: rgba(0,0,0,0.5); padding: 2px 8px; border-radius: 8px; margin-left: auto; }
.proxy-toggle { font-size: 10px; color: #0ae; background: rgba(0,0,0,0.5); border: 1px solid rgba(0,170,238,0.4); padding: 1px 8px; border-radius: 8px; cursor: pointer; pointer-events: auto; line-height: 1.6; }
.proxy-toggle:hover { background: rgba(0,170,238,0.2); }

.buffering-indicator { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); display: flex; flex-direction: column; align-items: center; gap: 8px; z-index: 10; }
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
.ctrl-btn { background: transparent; border: none; color: #ddd; cursor: pointer; padding: 4px 8px; border-radius: 4px; font-size: 12px; display: flex; align-items: center; gap: 2px; }
.ctrl-btn:hover { background: rgba(255,255,255,0.1); color: #fff; }
.time-display { font-size: 12px; color: #aaa; }

.ctrl-group { position: relative; }
.ctrl-dropdown { position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); margin-bottom: 4px; background: rgba(30,30,40,0.95); border-radius: 8px; padding: 4px; display: flex; flex-direction: column; gap: 2px; min-width: 80px; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); z-index: 30; }
.dropdown-item { background: transparent; border: none; color: #bbb; padding: 4px 12px; cursor: pointer; font-size: 12px; border-radius: 4px; white-space: nowrap; }
.dropdown-item:hover { background: rgba(255,255,255,0.1); color: #fff; }
.dropdown-item.active { color: var(--n-primary-color); background: rgba(0,170,238,0.15); }

@keyframes spin { to { transform: rotate(360deg); } }
.play-controls { margin-top: 12px; }
</style>