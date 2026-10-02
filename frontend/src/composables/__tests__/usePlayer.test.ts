import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock hls.js and flv.js before importing usePlayer
vi.mock('hls.js', () => ({
  default: {
    isSupported: () => false,
  },
}))

vi.mock('flv.js', () => ({
  default: {
    isSupported: () => false,
    createPlayer: () => ({ destroy: vi.fn(), attachMediaElement: vi.fn(), load: vi.fn() }),
  },
}))

describe('usePlayer', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('should export all required functions', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()

    expect(player.videoRef).toBeDefined()
    expect(player.videoResolution).toBeDefined()
    expect(player.bufferPercent).toBeDefined()
    expect(player.isBuffering).toBeDefined()
    expect(player.downloadSpeed).toBeDefined()
    expect(player.isPlaying).toBeDefined()
    expect(player.useProxy).toBeDefined()
    expect(player.currentTime).toBeDefined()
    expect(player.duration).toBeDefined()
    expect(player.playbackRate).toBeDefined()
    expect(player.showControls).toBeDefined()
    expect(player.PLAYBACK_RATES).toBeDefined()
  })

  it('should have default playback rate of 1', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    expect(player.playbackRate.value).toBe(1)
  })

  it('should have default proxy enabled', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    expect(player.useProxy.value).toBe(true)
  })

  it('should provide all standard playback rates', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    expect(player.PLAYBACK_RATES).toEqual([0.5, 0.75, 1, 1.25, 1.5, 2, 3])
  })

  it('should change playback rate', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    player.setPlaybackRate(1.5)
    expect(player.playbackRate.value).toBe(1.5)
  })

  it('should persist playback rate to localStorage', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    player.setPlaybackRate(2)
    const saved = JSON.parse(localStorage.getItem('fongmi_player_prefs') || '{}')
    expect(saved.playbackRate).toBe(2)
  })

  it('should build proxy URL correctly', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    const url = 'https://example.com/video.mp4'
    const proxyUrl = player.buildProxyUrl(url, null)
    expect(proxyUrl).toContain('/api/player/proxy/')
    expect(proxyUrl).toContain(encodeURIComponent(url))
  })

  it('should build direct URL when proxy is disabled', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    player.useProxy.value = false
    const url = 'https://example.com/video.mp4'
    const directUrl = player.buildProxyUrl(url, null)
    expect(directUrl).toBe(url)
  })

  it('should reset video info correctly', async () => {
    const { usePlayer } = await import('@/composables/usePlayer')
    const player = usePlayer()
    player.videoResolution.value = '1920×1080'
    player.bufferPercent.value = 50
    player.isBuffering.value = true
    player.downloadSpeed.value = '10 MB/s'
    player.isPlaying.value = true
    player.currentTime.value = 100

    player.resetVideoInfo()

    expect(player.videoResolution.value).toBe('')
    expect(player.bufferPercent.value).toBe(0)
    expect(player.isBuffering.value).toBe(false)
    expect(player.downloadSpeed.value).toBe('')
    expect(player.currentTime.value).toBe(0)
    expect(player.duration.value).toBe(0)
    expect(player.isPlaying.value).toBe(false)
  })
})