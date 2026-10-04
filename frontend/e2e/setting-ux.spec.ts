import { test, expect } from '@playwright/test'

const sc = '.n-layout--absolute-positioned > .n-layout-scroll-container'

test('设置页锚点菜单：点击定位并高亮', async ({ page }) => {
  await page.goto('/setting')
  await expect(page.locator('.anchor-bar')).toBeVisible({ timeout: 15000 })

  const chips = page.locator('.anchor-chip')
  await expect(chips).toHaveCount(6)
  await expect(chips.first()).toHaveClass(/active/)  // 初始在顶部 → 订阅管理

  // 点击「本地视频」→ 容器滚到底、该 chip 高亮
  await chips.nth(5).click()
  await expect(chips.nth(5)).toHaveClass(/active/)
  await expect.poll(async () =>
    await page.locator(sc).evaluate((el: HTMLElement) => el.scrollTop)
  ).toBeGreaterThan(200)

  // 滚回顶部 → 高亮回到第一个
  await page.locator(sc).evaluate((el: HTMLElement) => el.scrollTo({ top: 0 }))
  await expect.poll(async () => await chips.first().getAttribute('class')).toContain('active')
})

test('设置页折叠：本地视频默认收起、可展开、状态持久化', async ({ page }) => {
  await page.goto('/setting')
  const localCard = page.locator('#sec-local')
  await expect(localCard).toBeVisible({ timeout: 15000 })

  const toggle = localCard.locator('.card-head button')
  const body = localCard.locator('.stats-row')
  await expect(body).toBeHidden()          // 默认收起
  await expect(toggle).toContainText('展开')

  await toggle.click()
  await expect(body).toBeVisible()
  await expect(toggle).toContainText('收起')

  // 刷新后仍保持展开
  await page.reload()
  await expect(localCard.locator('.stats-row')).toBeVisible({ timeout: 15000 })

  // 还原为默认收起，避免影响真实使用
  await page.evaluate(() => localStorage.removeItem('fongmi_setting_collapse'))
})

test('设置页：回到顶部按钮出现并可点击', async ({ page }) => {
  await page.goto('/setting')
  await page.locator('.anchor-bar').waitFor({ timeout: 15000 })
  if (!(await page.locator('#sec-local').isVisible())) {
    await page.locator('#sec-local .card-head button').click()
  }
  await page.locator(sc).evaluate((el: HTMLElement) => el.scrollTo({ top: 2000 }))
  const backTop = page.locator('.n-back-top')
  await expect(backTop).toBeVisible({ timeout: 8000 })
  await backTop.click()
  await expect.poll(async () =>
    await page.locator(sc).evaluate((el: HTMLElement) => el.scrollTop), { timeout: 8000 }
  ).toBeLessThan(50)
})
