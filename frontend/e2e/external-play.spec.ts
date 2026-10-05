import { test, expect, request as pwRequest } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:8000'
const ROOT = path.resolve(process.cwd(), 'test-results')
const BAT = path.join(ROOT, 'e2e-fake-player.bat')
const MARK = path.join(ROOT, 'e2e-ext-launch-marker.txt')

const DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
const MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

// 外部播放器全流程：未配置不显示角标 → 配置路径 → 卡片角标一键调用
test.describe('桌面端', () => {
  test('卡片角标调用外部播放器播放', async ({ page }) => {
  test.setTimeout(420000)
  const api = await pwRequest.newContext({ baseURL: BASE })
  // 边界校验：bat 与标记文件都必须落在 test-results 内
  expect(BAT.startsWith(ROOT + path.sep)).toBe(true)
  expect(MARK.startsWith(ROOT + path.sep)).toBe(true)

  // 预热：先经 API 把片库扫描跑完。页面挂载会自动触发扫描，库里新文件多时
  // 扫描写事务会阻塞视频列表查询导致卡片迟迟不渲染；预热后自动扫描为增量空跑
  await api.post('/api/local/scan', { timeout: 360000 })
  await expect.poll(async () => {
    const s = await (await api.get('/api/local/scan/status')).json()
    return s.scanning
  }, { timeout: 30000 }).toBe(false)

  // 前置重置为未配置，保证「无角标」断言的确定性（globalTeardown 会还原真实值）
  await api.post('/api/system/config', { data: { external_player_path: '' } })
  fs.rmSync(MARK, { force: true })

  try {
    await page.goto('/local')
    await page.locator('.chip').first().waitFor({ timeout: 15000 })
    await expect(page.locator('.card-ext')).toHaveCount(0)

    // 假播放器：被调用即把传入的视频路径追加进标记文件（cmd 批处理需 CRLF）
    const bat = `@echo off\r\n(echo %~1)>>"${MARK}"\r\n`
    fs.writeFileSync(BAT, bat)
    await api.post('/api/system/config', { data: { external_player_path: BAT } })

    await page.goto('/local')
    const btn = page.locator('.card-ext').first()
    await expect(btn).toBeVisible({ timeout: 15000 })
    await btn.click()
    await expect(page.locator('.n-message', { hasText: '已调用外部播放器' })).toBeVisible({ timeout: 15000 })

    // 标记文件出现且含视频路径 = 播放器进程被真实拉起并收到了文件参数
    await expect.poll(async () => {
      return fs.existsSync(MARK) ? fs.readFileSync(MARK, 'utf-8') : ''
    }, { timeout: 15000 }).toContain('.mp4')
  } finally {
    await api.post('/api/system/config', { data: { external_player_path: '' } }).catch(() => {})
    fs.rmSync(BAT, { force: true })
    fs.rmSync(MARK, { force: true })
    await api.dispose()
  }
  })
})

// 移动终端浏览器无法调起本机 exe 播放器，即使已配置路径也不显示角标
test.describe('移动端', () => {
  test.use({ userAgent: MOBILE_UA })

  test('已配置播放器路径时仍不显示角标', async ({ page }) => {
    const api = await pwRequest.newContext({ baseURL: BASE })
    // 预热：页面挂载自动扫描的写事务会阻塞视频列表查询（同桌面端用例说明）
    await api.post('/api/local/scan', { timeout: 360000 })
    await expect.poll(async () => {
      const s = await (await api.get('/api/local/scan/status')).json()
      return s.scanning
    }, { timeout: 30000 }).toBe(false)

    await api.post('/api/system/config', { data: { external_player_path: 'C:\\Windows\\System32\\notepad.exe' } })
    try {
      await page.goto('/local')
      await page.locator('.chip').first().waitFor({ timeout: 15000 })
      await expect(page.locator('.card-ext')).toHaveCount(0)
    } finally {
      await api.post('/api/system/config', { data: { external_player_path: '' } }).catch(() => {})
      await api.dispose()
    }
  })
})
