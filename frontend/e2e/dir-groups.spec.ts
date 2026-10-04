import { test, expect } from '@playwright/test'

// 「本地视频」卡片默认收起，用例需先展开才能操作目录/聚合区
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem('fongmi_setting_collapse', JSON.stringify({ configs: true, local: false }))
  )
})

/** 实时读取目录列表——库在扫描/文件移动时计数会变，断言须与 API 同源自洽而非冻结在测试开始时 */
async function liveDirs(page: import('@playwright/test').Page) {
  return (await (await page.request.get('/api/local/dirs')).json()) as any[]
}

/** 片库页只渲染可见目录，聚合断言须基于可见目录而非全部目录 */
async function liveVisibleDirs(page: import('@playwright/test').Page) {
  const ds = await liveDirs(page)
  return ds.filter(d => d.visible === undefined || !!d.visible)
}

async function expectedMerged(page: import('@playwright/test').Page): Promise<string> {
  const ds = await liveVisibleDirs(page)
  return `共 ${ds[0].video_count + ds[1].video_count} 个视频`
}

test('聚合选项卡全流程：创建→片库合并展示→编辑→删除', async ({ page }) => {
  // 前置：等片库扫描空闲（页面挂载会触发自动扫描，扫描期间计数波动会干扰计数断言）
  await expect.poll(async () => {
    const s = await (await page.request.get('/api/local/scan/status')).json()
    return s.scanning
  }, { timeout: 180000 }).toBe(false)

  // 前置：库稳定才继续——用户同步/搬运文件时计数会来回跳，此时计数断言无意义
  const mergedAt = async () => {
    const ds = await liveVisibleDirs(page)
    return ds.length >= 2 ? ds[0].video_count + ds[1].video_count : -1
  }
  const m1 = await mergedAt()
  await page.waitForTimeout(3000)
  const m2 = await mergedAt()
  test.skip(m1 !== m2, `媒体库正在变更（${m1} → ${m2}），稍后重试`)

  // 前置：清空所有聚合组，从干净状态出发（片库页默认选中首个组；globalTeardown 会还原真实组）
  const existing = await (await page.request.get('/api/local/groups')).json()
  for (const g of existing) {
    await page.request.delete(`/api/local/groups/${g.id}`)
  }

  // ── 设置页：创建聚合选项卡（前两个可见目录） ──
  await page.goto('/setting')
  await page.locator('.dir-item').first().waitFor({ timeout: 15000 })
  const visible = await liveVisibleDirs(page)
  test.skip(visible.length < 2, '需要至少两个可见目录')
  let createdId: number | null = null

  try {
  await page.locator('.group-section .n-input input').fill('E2E聚合')
  const select = page.locator('.group-section .n-select')
  await select.click()
  // 下拉选项按目录全量渲染（含隐藏目录），按路径精确选前两个可见目录
  await page.locator('.n-base-select-option', { hasText: visible[0].path }).click()
  await page.locator('.n-base-select-option', { hasText: visible[1].path }).click()
  await page.keyboard.press('Escape')
  await page.locator('.group-actions button', { hasText: '创建聚合选项卡' }).click()
  await expect(page.locator('.group-section .group-item .dir-path', { hasText: 'E2E聚合' })).toBeVisible()
  createdId = ((await (await page.request.get('/api/local/groups')).json())[0] || {}).id ?? null

  // ── 片库页：聚合 tab 默认选中且合并两目录视频 ──
  await page.goto('/local')
  const groupChip = page.locator('.chip-group', { hasText: 'E2E聚合' })
  await expect(groupChip).toBeVisible({ timeout: 15000 })
  await expect(groupChip).toHaveClass(/active/)
  await expect.poll(async () => (await page.locator('.list-meta').textContent())?.trim(), { timeout: 60000 })
    .toBe(await expectedMerged(page))

  // 切到普通目录 tab → 只显示该目录数量；切回聚合 tab → 恢复合并数量
  const firstDirChip = page.locator('.chip:not(.chip-group)').first()
  await firstDirChip.click()
  await expect.poll(async () => (await page.locator('.list-meta').textContent())?.trim(), { timeout: 60000 })
    .toBe(`共 ${(await liveVisibleDirs(page))[0].video_count} 个视频`)
  await groupChip.click()
  await expect.poll(async () => (await page.locator('.list-meta').textContent())?.trim(), { timeout: 60000 })
    .toBe(await expectedMerged(page))

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
  createdId = null
  } finally {
    // 兜底：清理用例可能遗留的聚合组，避免污染真实数据与后续用例
    if (createdId !== null) {
      await page.request.delete(`/api/local/groups/${createdId}`).catch(() => {})
    }
    for (const g of await (await page.request.get('/api/local/groups')).json()) {
      if (String(g.name).startsWith('E2E聚合')) await page.request.delete(`/api/local/groups/${g.id}`)
    }
  }
})
