import { test } from '@playwright/test'

test.describe('UI 截图测试', () => {

  test('首页-空状态', async ({ page }) => {
    await page.goto('/')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'test-screenshots/home-empty.png', fullPage: true })
  })

  test('设置页', async ({ page }) => {
    await page.goto('/setting')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'test-screenshots/setting.png', fullPage: true })
  })

  test('搜索页', async ({ page }) => {
    await page.goto('/search')
    await page.waitForTimeout(500)
    await page.screenshot({ path: 'test-screenshots/search.png', fullPage: true })
  })

  test('直播页', async ({ page }) => {
    await page.goto('/live')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'test-screenshots/live.png', fullPage: true })
  })

  test('本地页', async ({ page }) => {
    await page.goto('/local')
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'test-screenshots/local.png', fullPage: true })
  })

  test('历史页', async ({ page }) => {
    await page.goto('/history')
    await page.waitForTimeout(500)
    await page.screenshot({ path: 'test-screenshots/history.png', fullPage: true })
  })

  test('收藏页', async ({ page }) => {
    await page.goto('/keep')
    await page.waitForTimeout(500)
    await page.screenshot({ path: 'test-screenshots/keep.png', fullPage: true })
  })
})