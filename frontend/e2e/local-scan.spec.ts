import { test, expect, request as pwRequest } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const BASE = 'http://127.0.0.1:8000'
const TEST_NAME = '__scan_e2e__.mp4'

/** 扫描按钮回归：点击必须有反馈（toast + loading 复位），且新文件能被扫描入库 */
test('扫描按钮：点击有反馈、新文件被扫描发现并刷新列表', async ({ page }) => {
  test.setTimeout(90000)
  const api = await pwRequest.newContext({ baseURL: BASE })
  const dirs = await (await api.get('/api/local/dirs')).json()
  test.skip(dirs.length === 0, '无目录可测')

  const root = path.resolve(dirs[0].path)
  const testPath = path.join(root, TEST_NAME)
  // 边界校验：目标必须位于被测目录内
  expect(testPath.startsWith(root + path.sep)).toBe(true)
  fs.writeFileSync(testPath, Buffer.alloc(1024))  // 内容无关，扫描按扩展名发现

  try {
    await page.goto('/local')
    const btn = page.locator('.page-header button', { hasText: '扫描' })
    await expect(btn).toBeVisible({ timeout: 15000 })
    await page.waitForTimeout(2000)  // 等 onMounted 自带的后台扫描结束

    await btn.click()
    await expect(page.locator('.n-message', { hasText: '扫描完成' })).toBeVisible({ timeout: 60000 })
    await expect(btn).not.toHaveClass(/n-button--loading/)

    await expect.poll(async () => {
      const r = await (await api.get('/api/local/videos', { params: { search: '__scan_e2e__' } })).json()
      return r.total
    }, { timeout: 15000 }).toBeGreaterThan(0)
  } finally {
    if (testPath.startsWith(root + path.sep)) fs.rmSync(testPath, { force: true })
    const rows = await (await api.get('/api/local/videos', { params: { search: '__scan_e2e__' } })).json()
    for (const v of rows.items || []) await api.delete(`/api/local/videos?ids=${v.id}`)
    await api.dispose()
  }
})
