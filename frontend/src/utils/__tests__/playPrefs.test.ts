import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

// playOpenPrefs 是模块级单例，每个用例重置模块以重新读取 localStorage
async function importFresh() {
  vi.resetModules()
  return await import('@/utils/playPrefs')
}

describe('playPrefs', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('无存储时默认两者都开（新标签页，保持历史行为）', async () => {
    const { playOpenPrefs } = await importFresh()
    expect(playOpenPrefs.vod).toBe(true)
    expect(playOpenPrefs.local).toBe(true)
  })

  it('从 localStorage 恢复已保存的偏好', async () => {
    localStorage.setItem('fongmi_play_open_prefs', JSON.stringify({ vod: false, local: false }))
    const { playOpenPrefs } = await importFresh()
    expect(playOpenPrefs.vod).toBe(false)
    expect(playOpenPrefs.local).toBe(false)
  })

  it('半份数据时缺失字段回退默认 true', async () => {
    localStorage.setItem('fongmi_play_open_prefs', JSON.stringify({ vod: false }))
    const { playOpenPrefs } = await importFresh()
    expect(playOpenPrefs.vod).toBe(false)
    expect(playOpenPrefs.local).toBe(true)
  })

  it('损坏数据不抛错并回退默认', async () => {
    localStorage.setItem('fongmi_play_open_prefs', '{broken')
    const { playOpenPrefs } = await importFresh()
    expect(playOpenPrefs.vod).toBe(true)
    expect(playOpenPrefs.local).toBe(true)
  })

  it('修改偏好自动持久化到 localStorage，两项互不影响', async () => {
    const { playOpenPrefs } = await importFresh()
    playOpenPrefs.vod = false
    await nextTick()
    playOpenPrefs.local = false
    await nextTick()
    playOpenPrefs.local = true
    await nextTick()

    const saved = JSON.parse(localStorage.getItem('fongmi_play_open_prefs') || '{}')
    expect(saved).toEqual({ vod: false, local: true })
  })
})
