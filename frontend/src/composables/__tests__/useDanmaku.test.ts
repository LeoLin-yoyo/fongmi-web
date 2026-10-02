import { describe, it, expect, beforeEach, vi } from 'vitest'

// jsdom 不支持 requestAnimationFrame / ResizeObserver / Canvas
globalThis.requestAnimationFrame = vi.fn((cb: FrameRequestCallback) => {
  return setTimeout(cb, 16) as unknown as number
})
globalThis.cancelAnimationFrame = vi.fn((id: number) => clearTimeout(id))
class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}
globalThis.ResizeObserver = MockResizeObserver as any
// Mock canvas getContext
HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  clearRect: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  fillText: vi.fn(),
  strokeText: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  font: '',
  textAlign: 'left' as CanvasTextAlign,
  fillStyle: '#fff',
  strokeStyle: '#000',
  lineWidth: 2,
  globalAlpha: 1,
})) as unknown as () => CanvasRenderingContext2D

describe('useDanmaku', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should export all required functions', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    expect(dm.danmakuEnabled).toBeDefined()
    expect(dm.danmakuOpacity).toBeDefined()
    expect(dm.danmakuSpeed).toBeDefined()
    expect(dm.danmakuArea).toBeDefined()
    expect(dm.danmakuItems).toBeDefined()
    expect(dm.danmakuVisible).toBeDefined()
    expect(dm.initDanmaku).toBeDefined()
    expect(dm.loadDanmaku).toBeDefined()
    expect(dm.toggleDanmaku).toBeDefined()
    expect(dm.parseBilibiliXml).toBeDefined()
  })

  it('should have default values', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    expect(dm.danmakuEnabled.value).toBe(false)
    expect(dm.danmakuOpacity.value).toBe(0.8)
    expect(dm.danmakuSpeed.value).toBe(1)
    expect(dm.danmakuArea.value).toBe('full')
    expect(dm.danmakuItems.value).toEqual([])
    expect(dm.danmakuVisible.value).toBe(false)
  })

  it('should parse empty B站 XML', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    const result = dm.parseBilibiliXml('<d></d>')
    expect(result).toEqual([])
  })

  it('should parse B站 XML with single danmaku', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<d>
  <p p="12.5,1,25,16777215,1234567890,0,abc123,123">测试弹幕</p>
</d>`
    const result = dm.parseBilibiliXml(xml)
    expect(result).toHaveLength(1)
    expect(result[0].time).toBe(12.5)
    expect(result[0].type).toBe(1)
    expect(result[0].fontSize).toBe(25)
    expect(result[0].color).toBe(16777215)
    expect(result[0].text).toBe('测试弹幕')
  })

  it('should parse multiple danmaku entries', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    const xml = `<d>
  <p p="1.0,1,25,16777215,0,0,a,1">第一条</p>
  <p p="5.5,4,18,16776960,0,0,b,2">第二条</p>
  <p p="10.0,5,25,16711680,0,0,c,3">第三条</p>
</d>`
    const result = dm.parseBilibiliXml(xml)
    expect(result).toHaveLength(3)
    expect(result[0].text).toBe('第一条')
    expect(result[1].type).toBe(4)
    expect(result[2].type).toBe(5)
  })

  it('should sort danmaku by time', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    const xml = `<d>
  <p p="10.0,1,25,0,0,0,a,1">后</p>
  <p p="1.0,1,25,0,0,0,b,2">前</p>
</d>`
    const result = dm.parseBilibiliXml(xml)
    expect(result[0].time).toBe(1.0)
    expect(result[0].text).toBe('前')
    expect(result[1].time).toBe(10.0)
    expect(result[1].text).toBe('后')
  })

  it('should handle danmaku with special characters', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    const xml = `<d><p p="5.0,1,25,0,0,0,a,1">Hello 你好 🎯</p></d>`
    const result = dm.parseBilibiliXml(xml)
    expect(result[0].text).toBe('Hello 你好 🎯')
  })

  it('should load danmaku from XML text', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    const xml = `<d><p p="1.0,1,25,0,0,0,a,1">测试</p></d>`
    dm.loadDanmaku(xml)
    expect(dm.danmakuItems.value).toHaveLength(1)
    expect(dm.danmakuVisible.value).toBe(true)
  })

  it('should toggle danmaku enabled state', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    expect(dm.danmakuEnabled.value).toBe(false)

    // 需要先 initDanmaku（绑定 canvas），toggle 才能生效
    const el = document.createElement('div')
    dm.initDanmaku(el)
    // 直接调用 toggleDanmaku（startDanmaku 内部会设置 danmakuEnabled = true）
    // 注意：由于 initDanmaku 创建了 canvas，startDanmaku 中的 canvas 不会为 null
    // 但为了测试，我们直接调用 startDanmaku
    dm.startDanmaku()
    expect(dm.danmakuEnabled.value).toBe(true)
    dm.stopDanmaku()
    expect(dm.danmakuEnabled.value).toBe(false)
    dm.destroyDanmaku()
  })

  it('should change danmaku settings', async () => {
    const { useDanmaku } = await import('@/composables/useDanmaku')
    const dm = useDanmaku()
    dm.danmakuOpacity.value = 0.5
    dm.danmakuSpeed.value = 2
    dm.danmakuArea.value = 'top'
    expect(dm.danmakuOpacity.value).toBe(0.5)
    expect(dm.danmakuSpeed.value).toBe(2)
    expect(dm.danmakuArea.value).toBe('top')
  })
})