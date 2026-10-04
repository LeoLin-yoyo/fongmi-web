import { test, expect } from '@playwright/test'

test('设置页目录顺序可调整', async ({ page }) => {
  await page.goto('/setting')
  const items = page.locator('.dir-item')
  await expect(items.first()).toBeVisible({ timeout: 15000 })
  const paths = async () => await items.locator('.dir-path').allTextContents()
  const before = await paths()
  test.skip(before.length < 2, '需要至少两个目录才能验证排序')

  try {
    // 第一个目录下移 → 与第二个互换
    await items.first().locator('button[title="下移"]').click()
    await expect.poll(async () => (await paths())[0], { timeout: 5000 }).toBe(before[1])
    expect((await paths())[1]).toBe(before[0])
  } finally {
    // 还原顺序，避免用例失败时留下调整后的真实数据；
    // 互换后原第二目录位于首位（其上移按钮禁用），故用下移还原
    if ((await paths())[0] === before[1]) {
      await items.first().locator('button[title="下移"]').click()
      await expect.poll(async () => (await paths())[0], { timeout: 5000 }).toBe(before[0])
    }
  }

  // 首个目录的上移、末个目录的下移应为禁用态
  await expect(items.first().locator('button[title="上移"]')).toBeDisabled()
  await expect(items.last().locator('button[title="下移"]')).toBeDisabled()
})
