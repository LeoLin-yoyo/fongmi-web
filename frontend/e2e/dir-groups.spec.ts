import { test, expect } from '@playwright/test'

// 「本地视频」卡片默认收起，用例需先展开才能操作目录/聚合区
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('fongmi_setting_collapse', JSON.stringify({ configs: true, local: false }))
  )
})

test('聚合选项卡全流程：创建→片库合并展示→编辑→删除', async ({ page }) => {
  // 前置：清掉可能残留的同名组，避免断言命中多个
  const existing = await (await page.request.get('/api/local/groups')).json()
  for (const g of existing) {
    if (String(g.name).startsWith('E2E聚合')) {
      await page.request.delete(`/api/local/groups/${g.id}`)
    }
  }

  // ── 设置页：创建聚合选项卡（前两个目录） ──
  await page.goto('/setting')
  await page.locator('.dir-item').first().waitFor({ timeout: 15000 })
  const dirs = await (await page.request.get('/api/local/dirs')).json()
  test.skip(dirs.length < 2, '需要至少两个目录')
  const expectedMerged = dirs[0].video_count + dirs[1].video_count

  await page.locator('.group-section .n-input input').fill('E2E聚合')
  const select = page.locator('.group-section .n-select')
  await select.click()
  await page.locator('.n-base-select-option').first().click()
  await page.locator('.n-base-select-option').nth(1).click()
  await page.keyboard.press('Escape')
  await page.locator('.group-actions button', { hasText: '创建聚合选项卡' }).click()
  await expect(page.locator('.group-section .group-item .dir-path', { hasText: 'E2E聚合' })).toBeVisible()

  // ── 片库页：聚合 tab 默认选中且合并两目录视频 ──
  await page.goto('/local')
  const groupChip = page.locator('.chip-group', { hasText: 'E2E聚合' })
  await expect(groupChip).toBeVisible({ timeout: 15000 })
  await expect(groupChip).toHaveClass(/active/)
  await expect(page.locator('.list-meta')).toHaveText(`共 ${expectedMerged} 个视频`)

  // 切到普通目录 tab → 只显示该目录数量；切回聚合 tab → 恢复合并数量
  const firstDirChip = page.locator('.chip:not(.chip-group)').first()
  await firstDirChip.click()
  await expect(page.locator('.list-meta')).toHaveText(`共 ${dirs[0].video_count} 个视频`)
  await groupChip.click()
  await expect(page.locator('.list-meta')).toHaveText(`共 ${expectedMerged} 个视频`)

  // ── 设置页：编辑改名 ──
  await page.goto('/setting')
  await page.locator('.group-section .group-item', { hasText: 'E2E聚合' }).locator('button', { hasText: '编辑' }).click()
  await page.locator('.group-section .n-input input').fill('E2E聚合改')
  await page.locator('.group-actions button', { hasText: '保存修改' }).click()
  await expect(page.locator('.group-section .group-item .dir-path', { hasText: 'E2E聚合改' })).toBeVisible()

  // ── 删除（接受 confirm 弹窗） ──
  page.on('dialog', (d) => d.accept())
  await page.locator('.group-section .group-item', { hasText: 'E2E聚合改' }).locator('button', { hasText: '删除' }).click()
  await expect(page.locator('.group-section .no-group')).toBeVisible()
})
