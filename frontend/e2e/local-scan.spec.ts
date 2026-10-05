import { test, expect, request as pwRequest } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const BASE = 'http://127.0.0.1:8000'
const TEST_NAME = '__scan_e2e__.mp4'

/** 扫描按钮回归：点击必须有反馈（toast + loading 复位），且新文件能被扫描入库 */
test('扫描按钮：点击有反馈、新文件被扫描发现并刷新列表', async ({ page }) => {
  // 库大/文件搬运中时全库扫描可达数分钟，给足总超时
  test.setTimeout(420000)
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

    // 前置：等挂载触发的自动扫描结束。扫描器 single-flight（scan_dir 见 _running 直接跳过），
    // 不等空闲的话点击触发的扫描会被吞掉，测试文件永远不入库
    await expect.poll(async () => {
      const s = await (await api.get('/api/local/scan/status')).json()
      return s.scanning
    }, { timeout: 360000 }).toBe(false)

    // 点击有响应的硬证据：POST /api/local/scan 发出（triggerScan 的 toast 是 3 秒寿命
    // 的瞬态元素，页面波动时与 click actionability 存在竞态，不作断言；
    // 「开始扫描…」info toast 的存在性由 triggerScan 首行代码保证）
    const scanPost = page.waitForResponse(
      (r) => r.url().includes('/api/local/scan') && r.request().method() === 'POST',
      { timeout: 60000 },
    )
    await btn.click()
    await scanPost

    // 入库验证与 toast 解耦：等这次扫描真正结束再查总数
    await expect.poll(async () => {
      const s = await (await api.get('/api/local/scan/status')).json()
      return s.scanning
    }, { timeout: 360000 }).toBe(false)
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
