import { ref, computed, onBeforeUnmount } from 'vue'
import Hls from 'hls.js'
import flvjs from 'flv.js'
import { track } from '@/utils/metrics'

export function usePlayer() {
  const videoRef = ref<HTMLVideoElement | null>(null)
  const videoResolution = ref('')
  const bufferPercent = ref(0)
  const isBuffering = ref(false)
  const downloadSpeed = ref('')
  const isPlaying = ref(false)
  const useProxy = ref(true)
  const currentTime = ref(0)
  const duration = ref(0)
  // 进度条拖拽中：timeupdate 不回写 currentTime，避免锚点被播放进度拉回
  const uiSeeking = ref(false)
  const playbackRate = ref(1)
  const isFullscreen = ref(false)
  const showControls = ref(true)
  const subtitleTrack = ref('')
  const availableResolutions = ref<{ label: string; value: number }[]>([])
  const currentResolution = ref(-1)
  const autoNextCallback = ref<(() => void) | null>(null)
  // 播放失败回调（video error 事件触发，由页面注入自动换线路/换源逻辑）
  const playErrorCallback = ref<(() => void) | null>(null)
  // 字幕状态（T2-2）
  const embeddedSubtitles = ref<{ label: string; index: number }[]>([])
  const activeSubtitle = ref(-1)
  const subtitleSize = ref(18)

  let hls: Hls | null = null
  let flvPlayer: any = null
  let speedTimer: ReturnType<typeof setInterval> | null = null
  let lastLoadedBytes = 0
  let lastSpeedTime = 0
  let hideControlsTimer: ReturnType<typeof setTimeout> | null = null
  let keyboardHandler: ((e: KeyboardEvent) => void) | null = null

  // 埋点会话状态（T0-1）
  let initTs = 0
  let ttffReported = false
  let sessionReported = false
  let sessionCompleted = false
  let rebufferCount = 0
  let rebufferTotalMs = 0
  let waitingTs = 0

  const PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2, 3]
  const STORAGE_KEY = 'fongmi_player_prefs'

  function loadPrefs() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const prefs = JSON.parse(saved)
        if (prefs.playbackRate) playbackRate.value = prefs.playbackRate
        if (prefs.useProxy !== undefined) useProxy.value = prefs.useProxy
        if (prefs.subtitleSize) subtitleSize.value = prefs.subtitleSize
      }
    } catch {}
  }

  function savePrefs() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        playbackRate: playbackRate.value,
        useProxy: useProxy.value,
        subtitleSize: subtitleSize.value,
      }))
    } catch {}
  }

  function buildProxyUrl(url: string, headers: Record<string, string> | null | undefined): string {
    if (!useProxy.value) return url
    if (headers && Object.keys(headers).length > 0) {
      return `/api/player/proxy/${encodeURIComponent(url)}?extra_headers=${encodeURIComponent(JSON.stringify(headers))}`
    }
    return `/api/player/proxy/${encodeURIComponent(url)}`
  }

  function initPlayer(url: string, headers?: Record<string, string> | null) {
    destroyPlayer()
    if (!videoRef.value) return
    loadPrefs()

    initTs = performance.now()
    ttffReported = false
    sessionReported = false
    sessionCompleted = false
    rebufferCount = 0
    rebufferTotalMs = 0
    waitingTs = 0

    const finalUrl = buildProxyUrl(url, headers || null)

    if (finalUrl.includes('.m3u8') && Hls.isSupported()) {
      hls = new Hls({
        maxBufferLength: 60,
        maxMaxBufferLength: 120,
        maxBufferSize: 100 * 1000 * 1000,
        startFragPrefetch: true,
        enableWorker: true,
        backBufferLength: 60,
        fragLoadingMaxRetry: 6,
        manifestLoadingMaxRetry: 8,
        levelLoadingMaxRetry: 8,
        liveSyncDurationCount: 7,
        lowLatencyMode: false,
        capLevelToPlayerSize: true,
        startLevel: -1,
      })
      hls.loadSource(finalUrl)
      hls.attachMedia(videoRef.value)
      hls.on(Hls.Events.ERROR, (_: any, data: any) => {
        if (data.fatal) {
          console.error('HLS fatal error:', data)
          if (videoRef.value && hls) {
            hls.destroy()
            hls = null
            videoRef.value.src = finalUrl
          }
        }
      })
      hls.on(Hls.Events.MANIFEST_PARSED, (_: any, data: any) => {
        availableResolutions.value = (data.levels || []).map((level: any, idx: number) => ({
          label: level.height ? `${level.height}p` : `质量${idx}`,
          value: idx,
        }))
      })
    } else if ((finalUrl.includes('.flv') || finalUrl.includes('?format=flv')) && flvjs.isSupported()) {
      flvPlayer = flvjs.createPlayer({ type: 'flv', url: finalUrl })
      flvPlayer.attachMediaElement(videoRef.value)
      flvPlayer.load()
    } else {
      videoRef.value.src = finalUrl
    }
  }

  function reportSession() {
    if (sessionReported || !ttffReported) return
    sessionReported = true
    track('session', {
      play_ms: Math.round((videoRef.value?.currentTime || 0) * 1000),
      rebuffer_count: rebufferCount,
      rebuffer_ms: Math.round(rebufferTotalMs),
      completed: sessionCompleted,
    })
  }

  function destroyPlayer() {
    reportSession()
    if (hls) { hls.destroy(); hls = null }
    if (flvPlayer) { flvPlayer.destroy(); flvPlayer = null }
    // 清理外挂字幕
    if (externalSubtitleUrl) {
      URL.revokeObjectURL(externalSubtitleUrl)
      externalSubtitleUrl = ''
    }
    videoRef.value?.querySelectorAll('track[data-external]').forEach(t => t.remove())
    stopSpeedMonitor()
    removeKeyboardShortcuts()
  }

  function setupVideoEvents() {
    const el = videoRef.value
    if (!el) return
    el.onloadedmetadata = () => {
      videoResolution.value = el.videoWidth && el.videoHeight
        ? `${el.videoWidth} × ${el.videoHeight}` : ''
      duration.value = el.duration || 0
      detectEmbeddedSubtitles()
    }
    el.onresize = () => {
      videoResolution.value = el.videoWidth && el.videoHeight
        ? `${el.videoWidth} × ${el.videoHeight}` : ''
    }
    el.onprogress = () => {
      if (el.buffered.length > 0 && el.duration > 0) {
        bufferPercent.value = Math.round((el.buffered.end(el.buffered.length - 1) / el.duration) * 100)
      }
    }
    el.onwaiting = () => {
      isBuffering.value = true
      if (ttffReported && !waitingTs) {
        waitingTs = performance.now()
        rebufferCount++
      }
      if (!speedTimer) startSpeedMonitor()
    }
    el.oncanplay = () => {
      isBuffering.value = false
      if (waitingTs) {
        rebufferTotalMs += performance.now() - waitingTs
        waitingTs = 0
      }
    }
    el.onplaying = () => {
      isBuffering.value = false
      isPlaying.value = true
      if (waitingTs) {
        rebufferTotalMs += performance.now() - waitingTs
        waitingTs = 0
      }
      if (!ttffReported && initTs > 0) {
        ttffReported = true
        track('ttff', {
          ms: Math.round(performance.now() - initTs),
          resolution: el.videoWidth && el.videoHeight ? `${el.videoHeight}p` : '',
          via_hls: !!hls,
        })
      }
      stopSpeedMonitor()
      el.playbackRate = playbackRate.value
    }
    el.onpause = () => { isPlaying.value = false }
    el.onerror = () => {
      isBuffering.value = false
      stopSpeedMonitor()
      track('error', { message: `video error: ${el.error?.code || ''}` })
      if (playErrorCallback.value) {
        setTimeout(() => playErrorCallback.value!(), 100)
      }
    }
    el.ontimeupdate = () => {
      if (!uiSeeking.value) currentTime.value = el.currentTime || 0
      duration.value = el.duration || 0
    }
    el.onended = () => {
      isPlaying.value = false
      sessionCompleted = true
      track('complete', { duration_ms: Math.round((el.duration || 0) * 1000) })
      if (autoNextCallback.value) {
        setTimeout(() => autoNextCallback.value!(), 1500)
      }
    }
  }

  function startSpeedMonitor() {
    lastLoadedBytes = 0; lastSpeedTime = Date.now()
    speedTimer = setInterval(() => {
      const el = videoRef.value
      if (!el) return
      const now = Date.now()
      const elapsed = (now - lastSpeedTime) / 1000
      if (elapsed <= 0) return
      const loadedBytes = el.buffered.length > 0 ? el.buffered.end(el.buffered.length - 1) : 0
      const bytesDelta = loadedBytes - lastLoadedBytes
      if (bytesDelta > 0) {
        const speed = bytesDelta / elapsed
        downloadSpeed.value = speed >= 1024 * 1024
          ? `${(speed / 1024 / 1024).toFixed(1)} MB/s`
          : `${(speed / 1024).toFixed(0)} KB/s`
      }
      lastLoadedBytes = loadedBytes; lastSpeedTime = now
    }, 1000)
  }

  function stopSpeedMonitor() {
    if (speedTimer) { clearInterval(speedTimer); speedTimer = null }
    downloadSpeed.value = ''
  }

  function resetVideoInfo() {
    videoResolution.value = ''
    bufferPercent.value = 0
    isBuffering.value = false
    downloadSpeed.value = ''
    currentTime.value = 0
    duration.value = 0
    isPlaying.value = false
    availableResolutions.value = []
    currentResolution.value = -1
    embeddedSubtitles.value = []
    activeSubtitle.value = -1
    stopSpeedMonitor()
  }

  function setPlaybackRate(rate: number) {
    playbackRate.value = rate
    const el = videoRef.value
    if (el) el.playbackRate = rate
    savePrefs()
  }

  function togglePlay() {
    const el = videoRef.value
    if (!el) return
    if (el.paused) el.play().catch(() => {})
    else el.pause()
  }

  function seek(time: number) {
    const el = videoRef.value
    if (el) el.currentTime = time
  }

  function skip(seconds: number) {
    const el = videoRef.value
    if (el) el.currentTime = Math.max(0, Math.min(el.duration, el.currentTime + seconds))
  }

  // ---------- 进度条拖拽（PlayPage / DetailPage 共用） ----------
  const progressBoxRef = ref<HTMLElement | null>(null)
  const seekRatio = ref(0)

  const progressPercent = computed(() => {
    if (duration.value <= 0) return 0
    return (currentTime.value / duration.value) * 100
  })
  // 拖拽时以锚点位置为准，松手后回到播放进度
  const displayProgressPercent = computed(() => {
    const p = uiSeeking.value ? seekRatio.value * 100 : progressPercent.value
    return Math.min(100, Math.max(0, p))
  })
  const displayBufferPercent = computed(() => Math.min(100, Math.max(0, bufferPercent.value)))

  function seekRatioFromEvent(e: MouseEvent): number {
    const box = progressBoxRef.value
    if (!box) return 0
    const rect = box.getBoundingClientRect()
    if (rect.width <= 0) return 0
    return Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
  }

  function onProgressDown(e: MouseEvent) {
    if (!videoRef.value || duration.value <= 0) return
    uiSeeking.value = true
    seekRatio.value = seekRatioFromEvent(e)
    currentTime.value = seekRatio.value * duration.value // 锚点立即跟随点击位置
    window.addEventListener('mousemove', onProgressMove)
    window.addEventListener('mouseup', onProgressUp)
  }

  function onProgressMove(e: MouseEvent) {
    if (!uiSeeking.value) return
    seekRatio.value = seekRatioFromEvent(e)
    currentTime.value = seekRatio.value * duration.value
  }

  function onProgressUp() {
    window.removeEventListener('mousemove', onProgressMove)
    window.removeEventListener('mouseup', onProgressUp)
    if (!uiSeeking.value) return
    uiSeeking.value = false
    if (videoRef.value && duration.value > 0) {
      videoRef.value.currentTime = seekRatio.value * duration.value
    }
  }

  function toggleFullscreen() {
    const el = videoRef.value?.parentElement || videoRef.value
    if (!el) return
    if (!document.fullscreenElement) {
      el.requestFullscreen().catch(() => {})
      isFullscreen.value = true
    } else {
      document.exitFullscreen().catch(() => {})
      isFullscreen.value = false
    }
  }

  function togglePip() {
    const el = videoRef.value
    if (!el) return
    if (document.pictureInPictureElement) {
      document.exitPictureInPicture().catch(() => {})
    } else {
      el.requestPictureInPicture().catch(() => {})
    }
  }

  function setResolution(level: number) {
    if (hls) {
      hls.currentLevel = level
      currentResolution.value = level
    }
  }

  // ---------- 字幕（T2-2） ----------
  let externalSubtitleUrl = ''

  function applySubtitleSize() {
    let style = document.getElementById('fongmi-cue-style')
    if (!style) {
      style = document.createElement('style')
      style.id = 'fongmi-cue-style'
      document.head.appendChild(style)
    }
    style.textContent = `video::cue { font-size: ${subtitleSize.value}px; background: rgba(0,0,0,0.6); }`
  }

  function detectEmbeddedSubtitles() {
    const el = videoRef.value
    if (!el) return
    const tracks: { label: string; index: number }[] = []
    for (let i = 0; i < el.textTracks.length; i++) {
      const t = el.textTracks[i]
      if (t.kind === 'subtitles' || t.kind === 'captions') {
        tracks.push({ label: t.label || `字幕轨 ${tracks.length + 1}`, index: i })
      }
    }
    embeddedSubtitles.value = tracks
    applySubtitleSize()
  }

  function selectSubtitle(index: number) {
    const el = videoRef.value
    if (!el) return
    activeSubtitle.value = index
    for (let i = 0; i < el.textTracks.length; i++) {
      const t = el.textTracks[i]
      if (t.kind !== 'subtitles' && t.kind !== 'captions') continue
      t.mode = index >= 0 && embeddedSubtitles.value.some(s => s.index === i) && i === index
        ? 'showing' : 'disabled'
    }
  }

  function srtToVtt(srt: string): string {
    const body = srt.replace(/^\uFEFF/, '').replace(/\r/g, '')
    const converted = body.replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, '$1.$2')
    return converted.startsWith('WEBVTT') ? converted : 'WEBVTT\n\n' + converted
  }

  async function importSubtitleFile(file: File): Promise<boolean> {
    const el = videoRef.value
    if (!el) return false
    try {
      const text = await file.text()
      const isVtt = file.name.toLowerCase().endsWith('.vtt')
      const vtt = isVtt ? text : srtToVtt(text)
      // 移除上一次导入的外挂轨
      if (externalSubtitleUrl) {
        URL.revokeObjectURL(externalSubtitleUrl)
        externalSubtitleUrl = ''
      }
      el.querySelectorAll('track[data-external]').forEach(t => t.remove())
      const blob = new Blob([vtt], { type: 'text/vtt' })
      externalSubtitleUrl = URL.createObjectURL(blob)
      const trackEl = document.createElement('track')
      trackEl.kind = 'subtitles'
      trackEl.label = file.name
      trackEl.src = externalSubtitleUrl
      trackEl.setAttribute('data-external', '1')
      trackEl.default = true
      el.appendChild(trackEl)
      await new Promise<void>(resolve => {
        const done = () => { detectEmbeddedSubtitles(); resolve() }
        if (el.textTracks.length) {
          setTimeout(done, 100)
        } else {
          trackEl.addEventListener('load', done, { once: true })
          setTimeout(done, 400)
        }
      })
      // 新轨道位于列表末尾，选中它
      const lastIdx = el.textTracks.length - 1
      selectSubtitle(lastIdx)
      return true
    } catch (e) {
      console.error('Import subtitle failed:', e)
      return false
    }
  }

  function setSubtitleSize(px: number) {
    subtitleSize.value = px
    applySubtitleSize()
    savePrefs()
  }

  function setupKeyboardShortcuts() {
    removeKeyboardShortcuts()
    keyboardHandler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      switch (e.key) {
        case ' ':
          e.preventDefault()
          togglePlay()
          break
        case 'ArrowLeft':
          e.preventDefault()
          skip(-10)
          break
        case 'ArrowRight':
          e.preventDefault()
          skip(10)
          break
        case 'ArrowUp':
          e.preventDefault()
          if (videoRef.value) videoRef.value.volume = Math.min(1, videoRef.value.volume + 0.1)
          break
        case 'ArrowDown':
          e.preventDefault()
          if (videoRef.value) videoRef.value.volume = Math.max(0, videoRef.value.volume - 0.1)
          break
        case 'f':
        case 'F':
          toggleFullscreen()
          break
        case 'm':
        case 'M':
          if (videoRef.value) videoRef.value.muted = !videoRef.value.muted
          break
      }
    }
    document.addEventListener('keydown', keyboardHandler)
  }

  function removeKeyboardShortcuts() {
    if (keyboardHandler) {
      document.removeEventListener('keydown', keyboardHandler)
      keyboardHandler = null
    }
  }

  function startControlsTimer() {
    stopControlsTimer()
    showControls.value = true
    hideControlsTimer = setTimeout(() => {
      if (isPlaying.value) showControls.value = false
    }, 3000)
  }

  function stopControlsTimer() {
    if (hideControlsTimer) {
      clearTimeout(hideControlsTimer)
      hideControlsTimer = null
    }
  }

  function toggleControls() {
    if (showControls.value) {
      showControls.value = false
      stopControlsTimer()
    } else {
      startControlsTimer()
    }
  }

  onBeforeUnmount(() => {
    destroyPlayer()
    removeKeyboardShortcuts()
    stopControlsTimer()
    window.removeEventListener('mousemove', onProgressMove)
    window.removeEventListener('mouseup', onProgressUp)
  })

  // 页面直接关闭时兜底上报当前会话
  if (typeof window !== 'undefined') {
    window.addEventListener('pagehide', reportSession)
  }

  return {
    videoRef, videoResolution, bufferPercent, isBuffering, downloadSpeed, isPlaying, useProxy,
    currentTime, duration, uiSeeking, playbackRate, isFullscreen, showControls,
    subtitleTrack, availableResolutions, currentResolution, autoNextCallback, playErrorCallback,
    embeddedSubtitles, activeSubtitle, subtitleSize,
    progressBoxRef, progressPercent, displayProgressPercent, displayBufferPercent,
    onProgressDown,
    PLAYBACK_RATES,
    initPlayer, destroyPlayer, setupVideoEvents, resetVideoInfo,
    setPlaybackRate, togglePlay, seek, skip, toggleFullscreen, togglePip,
    setResolution, setupKeyboardShortcuts, removeKeyboardShortcuts,
    startControlsTimer, stopControlsTimer, toggleControls,
    detectEmbeddedSubtitles, selectSubtitle, importSubtitleFile, setSubtitleSize,
    buildProxyUrl, savePrefs,
  }
}