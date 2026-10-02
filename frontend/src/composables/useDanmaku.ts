import { ref, onBeforeUnmount } from 'vue'

interface DanmakuItem {
  time: number
  type: number
  fontSize: number
  color: number
  text: string
}

export function useDanmaku() {
  const danmakuEnabled = ref(false)
  const danmakuOpacity = ref(0.8)
  const danmakuSpeed = ref(1)
  const danmakuArea = ref<'full' | 'top' | 'bottom'>('full')
  const danmakuItems = ref<DanmakuItem[]>([])
  const danmakuVisible = ref(false)

  let canvas: HTMLCanvasElement | null = null
  let ctx: CanvasRenderingContext2D | null = null
  let animationId: number | null = null
  let activeDanmaku: { text: string; x: number; y: number; color: string; fontSize: number; opacity: number; speed: number }[] = []
  let lastTime = 0
  let currentPlayTime = 0
  let nextIndex = 0
  let parentEl: HTMLElement | null = null

  function parseBilibiliXml(xmlText: string): DanmakuItem[] {
    const items: DanmakuItem[] = []
    const regex = /<p\s+p="([^"]*)">([^<]*)<\/p>/g
    let match
    while ((match = regex.exec(xmlText)) !== null) {
      const attrs = match[1].split(',')
      const text = match[2].trim()
      if (!text) continue
      items.push({
        time: parseFloat(attrs[0]) || 0,
        type: parseInt(attrs[1]) || 1,
        fontSize: parseInt(attrs[2]) || 25,
        color: parseInt(attrs[3]) || 0xffffff,
        text,
      })
    }
    return items.sort((a, b) => a.time - b.time)
  }

  function initDanmaku(videoEl: HTMLElement) {
    parentEl = videoEl
    canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:5'
    canvas.width = videoEl.clientWidth || videoEl.offsetWidth
    canvas.height = videoEl.clientHeight || videoEl.offsetHeight
    videoEl.style.position = 'relative'
    videoEl.appendChild(canvas)
    ctx = canvas.getContext('2d')!

    const ro = new ResizeObserver(() => {
      if (canvas && parentEl) {
        canvas.width = parentEl.clientWidth
        canvas.height = parentEl.clientHeight
      }
    })
    ro.observe(videoEl)
  }

  function loadDanmaku(xmlText: string) {
    danmakuItems.value = parseBilibiliXml(xmlText)
    nextIndex = 0
    activeDanmaku = []
    danmakuVisible.value = true
  }

  function startDanmaku() {
    if (!canvas || !ctx) return
    danmakuEnabled.value = true
    lastTime = performance.now()
    loop()
  }

  function stopDanmaku() {
    danmakuEnabled.value = false
    if (animationId) {
      cancelAnimationFrame(animationId)
      animationId = null
    }
    activeDanmaku = []
    if (ctx && canvas) {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    }
  }

  function toggleDanmaku() {
    if (danmakuEnabled.value) stopDanmaku()
    else startDanmaku()
  }

  function seekDanmaku(time: number) {
    currentPlayTime = time
    nextIndex = 0
    activeDanmaku = []
    if (ctx && canvas) {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    }
  }

  function loop() {
    if (!danmakuEnabled.value || !canvas || !ctx) return
    const now = performance.now()
    const delta = (now - lastTime) / 1000
    lastTime = now
    currentPlayTime += delta

    const w = canvas.width
    const h = canvas.height
    ctx.clearRect(0, 0, w, h)

    while (nextIndex < danmakuItems.value.length && danmakuItems.value[nextIndex].time <= currentPlayTime) {
      const item = danmakuItems.value[nextIndex]
      const color = `#${item.color.toString(16).padStart(6, '0')}`
      const fontSize = item.fontSize === 18 ? 14 : item.fontSize === 25 ? 18 : 16
      const speed = 150 * danmakuSpeed.value

      if (item.type === 1 || item.type === 6) {
        activeDanmaku.push({
          text: item.text,
          x: w,
          y: 0,
          color,
          fontSize,
          opacity: danmakuOpacity.value,
          speed,
        })
      } else if (item.type === 4 && danmakuArea.value !== 'top') {
        activeDanmaku.push({
          text: item.text,
          x: w / 2,
          y: h * 0.85,
          color,
          fontSize,
          opacity: danmakuOpacity.value,
          speed: 0,
        })
      } else if (item.type === 5 && danmakuArea.value !== 'bottom') {
        activeDanmaku.push({
          text: item.text,
          x: w / 2,
          y: h * 0.15 + (nextIndex % 3) * 24,
          color,
          fontSize,
          opacity: danmakuOpacity.value,
          speed: 0,
        })
      }
      nextIndex++
    }

    const lanes = new Array(Math.floor(h / 26)).fill(0)
    activeDanmaku = activeDanmaku.filter(d => {
      if (d.speed > 0) {
        d.x -= d.speed * delta
        return d.x > -200
      } else {
        return true
      }
    })

    for (const d of activeDanmaku) {
      ctx.save()
      ctx.globalAlpha = d.opacity
      ctx.font = `${d.fontSize}px sans-serif`
      ctx.textAlign = d.speed > 0 ? 'left' : 'center'
      ctx.fillStyle = d.color
      ctx.strokeStyle = 'rgba(0,0,0,0.5)'
      ctx.lineWidth = 2

      if (d.speed > 0) {
        const laneIdx = Math.floor(Math.random() * lanes.length)
        d.y = laneIdx * 26 + 20
        ctx.strokeText(d.text, d.x, d.y)
        ctx.fillText(d.text, d.x, d.y)
      } else {
        ctx.strokeText(d.text, d.x, d.y)
        ctx.fillText(d.text, d.x, d.y)
      }
      ctx.restore()
    }

    animationId = requestAnimationFrame(loop)
  }

  function destroyDanmaku() {
    stopDanmaku()
    if (canvas && canvas.parentElement) {
      canvas.parentElement.removeChild(canvas)
    }
    canvas = null
    ctx = null
    parentEl = null
  }

  onBeforeUnmount(() => {
    destroyDanmaku()
  })

  return {
    danmakuEnabled, danmakuOpacity, danmakuSpeed, danmakuArea, danmakuItems, danmakuVisible,
    initDanmaku, loadDanmaku, startDanmaku, stopDanmaku, toggleDanmaku, seekDanmaku, destroyDanmaku,
    parseBilibiliXml,
  }
}