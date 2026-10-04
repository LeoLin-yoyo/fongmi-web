import { test, expect } from '@playwright/test'

test('目录显示/隐藏：设置页开关 → 片库页选项卡增减 → 恢复', async ({ page }) => {
  // ── 设置页：隐藏第二个目录 ──
  await page.goto('/setting')
  const items = page.locator('.dir-item')
  await expect(items.first()).toBeVisible({ timeout: 15000 })
  const dirs = await (await page.request.get('/api/local/dirs')).json()
  test.skip(dirs.length < 2, '需要至少两个目录')
  const target = dirs[1]

  const row = items.nth(1)
  await expect(row.locator('.n-switch')).toHaveClass(/n-switch--active/)  // 默认显示
  await row.locator('.n-switch').click()
  await expect(row.locator('.n-switch')).not.toHaveClass(/n-switch--active/)
  await expect(row.locator('.dir-off-tag')).toBeVisible()
  await expect.poll(async () => {
    const list = await (await page.request.get('/api/local/dirs')).json()
    return list.find((d: any) => d.id === target.id)?.visible
  }).toBe(0)

  try {
    // ── 片库页：普通目录选项卡数量减少 1 ──
    await page.goto('/local')
    await page.locator('.chip').first().waitFor({ timeout: 15000 })
    await expect(page.locator('.chip:not(.chip-group)')).toHaveCount(dirs.length - 1)

    // ── 设置页：恢复显示 ──
    await page.goto('/setting')
    await items.nth(1).locator('.n-switch').click()
    await expect.poll(async () => {
      const list = await (await page.request.get('/api/local/dirs')).json()
      return list.find((d: any) => d.id === target.id)?.visible
    }).toBe(1)

    // ── 片库页：选项卡数量恢复 ──
    await page.goto('/local')
    await expect(page.locator('.chip:not(.chip-group)')).toHaveCount(dirs.length)
  } finally {
    // 兜底还原，避免用例失败时留下隐藏状态
    await page.request.patch(`/api/local/dirs/${target.id}/visible`, { data: { visible: true } })
  }
})
