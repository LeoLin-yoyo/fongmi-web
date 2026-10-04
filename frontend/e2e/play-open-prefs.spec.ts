import { test, expect, type Page } from '@playwright/test'

const PREFS_KEY = 'fongmi_play_open_prefs'

/** 预置 localStorage 偏好（默认两者均开，由模块兜底） */
async function initPrefs(page: Page, prefs: { vod?: boolean; local?: boolean }) {
  const val = JSON.stringify({ vod: true, local: true, ...prefs })
  await page.addInitScript(([k, v]: [string, string]) => localStorage.setItem(k, v), [PREFS_KEY, val])
}

const localSwitch = (page: Page) => page.locator('.pref-item', { hasText: '本地视频' }).locator('.n-switch')
const vodSwitch = (page: Page) => page.locator('.pref-item', { hasText: '点播视频' }).locator('.n-switch')

test('设置页两项开关默认全开、可独立切换并持久化', async ({ page }) => {
  await page.goto('/setting')
  await expect(vodSwitch(page)).toHaveClass(/n-switch--active/, { timeout: 15000 })
  await expect(localSwitch(page)).toHaveClass(/n-switch--active/)

  // 关本地 → 只影响 local
  await localSwitch(page).click()
  await expect(localSwitch(page)).not.toHaveClass(/n-switch--active/)
  await expect(vodSwitch(page)).toHaveClass(/n-switch--active/)
  const saved = JSON.parse(await page.evaluate((k) => localStorage.getItem(k), PREFS_KEY))
  expect(saved).toEqual({ vod: true, local: false })

  // 关点播 → 两项均关，互不影响
  await vodSwitch(page).click()
  const saved2 = JSON.parse(await page.evaluate((k) => localStorage.getItem(k), PREFS_KEY))
  expect(saved2).toEqual({ vod: false, local: false })
})

test('本地视频：默认新标签页播放', async ({ page }) => {
  await page.goto('/local')
  const card = page.locator('.video-card').first()
  await expect(card).toBeVisible({ timeout: 15000 })
  const [popup] = await Promise.all([page.context().waitForEvent('page'), card.click()])
  await expect(popup).toHaveURL(/\/local\/player\/\d+/)
})

test('本地视频：关闭开关后当前页跳转播放', async ({ page }) => {
  await initPrefs(page, { local: false })
  await page.goto('/local')
  const card = page.locator('.video-card').first()
  await expect(card).toBeVisible({ timeout: 15000 })
  await Promise.all([page.waitForURL(/\/local\/player\/\d+/), card.click()])
  expect(page.url()).toMatch(/\/local\/player\/\d+/)
})

test('点播视频：默认新标签页打开', async ({ page }) => {
  await page.goto('/history')
  const card = page.locator('.history-card').first()
  if ((await page.locator('.history-card').count()) === 0) test.skip(true, '无观看历史数据')
  await expect(card).toBeVisible({ timeout: 15000 })
  const [popup] = await Promise.all([page.context().waitForEvent('page'), card.click()])
  await expect(popup).toHaveURL(/\/(detail|play)/)
})

test('点播视频：关闭开关后当前页跳转', async ({ page }) => {
  await initPrefs(page, { vod: false })
  await page.goto('/history')
  const card = page.locator('.history-card').first()
  if ((await page.locator('.history-card').count()) === 0) test.skip(true, '无观看历史数据')
  await expect(card).toBeVisible({ timeout: 15000 })
  await Promise.all([page.waitForURL(/\/(detail|play)/), card.click()])
  expect(page.url()).toMatch(/\/(detail|play)/)
})
