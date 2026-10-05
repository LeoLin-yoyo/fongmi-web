import { describe, it, expect, vi, afterEach } from 'vitest'

import { isMobileDevice } from '../device'

function stubNavigator(ua: string, maxTouchPoints = 0) {
  vi.stubGlobal('navigator', { userAgent: ua, maxTouchPoints })
}

afterEach(() => vi.unstubAllGlobals())

describe('isMobileDevice', () => {
  it('iPhone UA 识别为移动终端', () => {
    stubNavigator('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
    expect(isMobileDevice()).toBe(true)
  })

  it('Android 手机 UA 识别为移动终端', () => {
    stubNavigator('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
    expect(isMobileDevice()).toBe(true)
  })

  it('iPad 经典 UA 识别为移动终端', () => {
    stubNavigator('Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1', 5)
    expect(isMobileDevice()).toBe(true)
  })

  it('iPadOS 13+ 桌面模式 UA（Macintosh + 多点触控）识别为移动终端', () => {
    stubNavigator('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15', 5)
    expect(isMobileDevice()).toBe(true)
  })

  it('Windows 桌面 UA 不是移动终端', () => {
    stubNavigator('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    expect(isMobileDevice()).toBe(false)
  })

  it('Windows 触屏笔记本（Touch UA、多点触控）不是移动终端，可调用本机播放器', () => {
    stubNavigator('Mozilla/5.0 (Windows NT 10.0; Win64; x64; Touch) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 10)
    expect(isMobileDevice()).toBe(false)
  })

  it('Mac 桌面 UA 不是移动终端', () => {
    stubNavigator('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15')
    expect(isMobileDevice()).toBe(false)
  })
})
