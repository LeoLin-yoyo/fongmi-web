import { describe, it, expect, vi, beforeEach } from 'vitest'

const { routerPush, routerResolve } = vi.hoisted(() => ({
  routerPush: vi.fn(),
  routerResolve: vi.fn((location: any) => ({ href: '/resolved#' + JSON.stringify(location) })),
}))

vi.mock('@/router', () => ({
  default: { push: routerPush, resolve: routerResolve },
}))

import { openPlayPage } from '@/utils/navigation'
import { playOpenPrefs } from '@/utils/playPrefs'

describe('openPlayPage', () => {
  beforeEach(() => {
    routerPush.mockClear()
    routerResolve.mockClear()
    localStorage.clear()
    playOpenPrefs.vod = true
    playOpenPrefs.local = true
  })

  it('开关开启（默认）时 window.open 新标签页，不当前页跳转', () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window)
    const loc = { path: '/detail/1/2' }
    openPlayPage(loc, 'vod')
    expect(openSpy).toHaveBeenCalledTimes(1)
    expect(openSpy.mock.calls[0][1]).toBe('_blank')
    expect(routerPush).not.toHaveBeenCalled()
    openSpy.mockRestore()
  })

  it('点播开关关闭时当前页跳转，不弹新窗', () => {
    playOpenPrefs.vod = false
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window)
    const loc = { path: '/detail/1/2' }
    openPlayPage(loc, 'vod')
    expect(routerPush).toHaveBeenCalledWith(loc)
    expect(openSpy).not.toHaveBeenCalled()
    openSpy.mockRestore()
  })

  it('本地开关与点播开关互不影响', () => {
    playOpenPrefs.local = false
    const openSpy = vi.spyOn(window, 'open').mockReturnValue({} as Window)

    openPlayPage({ path: '/local/player/9' }, 'local')
    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(openSpy).not.toHaveBeenCalled()

    openPlayPage({ path: '/detail/1/2' }, 'vod')
    expect(openSpy).toHaveBeenCalledTimes(1)
    openSpy.mockRestore()
  })

  it('不传 kind 默认按点播处理', () => {
    playOpenPrefs.vod = false
    openPlayPage({ path: '/detail/1/2' })
    expect(routerPush).toHaveBeenCalledTimes(1)
  })

  it('弹窗被拦截（window.open 返回 null）时回退当前页跳转', () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    const loc = { path: '/local/player/9' }
    openPlayPage(loc, 'local')
    expect(routerPush).toHaveBeenCalledWith(loc)
    openSpy.mockRestore()
  })
})
