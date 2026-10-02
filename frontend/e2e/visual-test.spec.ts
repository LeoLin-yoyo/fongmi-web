import { test, expect } from '@playwright/test'

test.describe('FongMi TV Web 前端视觉测试', () => {

  test('首页加载-正常显示', async ({ page }) => {
    await page.goto('/')
    // 导航栏总是可见的
    await expect(page.locator('.nav-links')).toBeVisible({ timeout: 10000 })
    // 页面内容：空状态引导页 或 正常视频内容，只要有一种出现即可
    try {
      await page.waitForSelector('.empty-state', { timeout: 4000 })
    } catch {
      await page.waitForSelector('.home-header, .video-section, .home-section', { timeout: 6000 })
    }
  })

  test('导航栏-5个Tab', async ({ page }) => {
    await page.goto('/')
    const navLinks = page.locator('.nav-links a')
    await expect(navLinks).toHaveCount(5)
    const texts = await navLinks.allTextContents()
    expect(texts.map(t => t.trim())).toEqual(['首页', '直播', '本地', '我的', '设置'])
  })

  test('导航栏-全局搜索框', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.header-search input')).toBeVisible()
  })

  test('导航栏-主题切换按钮', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.theme-toggle')).toBeVisible()
  })

  test('主题切换-点击切换主题', async ({ page }) => {
    await page.goto('/')
    const themeToggle = page.locator('.theme-toggle')
    // 默认暗色
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await themeToggle.click()
    // 切换到亮色
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
    await themeToggle.click()
    // 切回暗色
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  })

  test('设置页-可访问', async ({ page }) => {
    await page.goto('/setting')
    await expect(page).toHaveURL(/\/setting/)
  })

  test('搜索页-输入关键词并搜索', async ({ page }) => {
    await page.goto('/search')
    const searchInput = page.locator('.search-input input')
    await expect(searchInput).toBeVisible()
    await searchInput.fill('测试')
    await searchInput.press('Enter')
    await expect(page.locator('.loading-area, .search-layout, .no-result').first()).toBeVisible({ timeout: 10000 })
  })

  test('搜索页-搜索历史', async ({ page }) => {
    await page.goto('/search')
    await page.evaluate(() => localStorage.removeItem('fongmi_search_history'))
    await page.reload()
    const searchInput = page.locator('.search-input input')
    await searchInput.fill('测试电影')
    await searchInput.press('Enter')
    await page.waitForTimeout(2000)
    await page.goto('/search')
    await page.waitForTimeout(500)
    await expect(page.getByText('测试电影').first()).toBeVisible()
  })

  test('直播页-可访问', async ({ page }) => {
    await page.goto('/live')
    await expect(page.locator('.live-page')).toBeVisible({ timeout: 10000 })
  })

  test('本地页-可访问', async ({ page }) => {
    await page.goto('/local')
    await expect(page.locator('.local-home, .local-page, [class*="local"]').first()).toBeVisible({ timeout: 10000 })
  })

  test('历史页-可访问', async ({ page }) => {
    await page.goto('/history')
    await expect(page.locator('.history-page')).toBeVisible({ timeout: 10000 })
  })

  test('收藏页-可访问', async ({ page }) => {
    await page.goto('/keep')
    await expect(page.locator('.keep-page')).toBeVisible({ timeout: 10000 })
  })

  test('API 健康检查', async ({ page }) => {
    const response = await page.request.get('/api/health')
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(data.code).toBe(0)
    expect(data.status).toBe('ok')
  })

  test('历史 API 返回正确格式', async ({ page }) => {
    const response = await page.request.get('/api/history')
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    expect(data).toHaveProperty('total')
    expect(data).toHaveProperty('page')
    expect(data).toHaveProperty('size')
    expect(data).toHaveProperty('items')
  })
})