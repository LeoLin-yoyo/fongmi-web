import { writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import type { FullConfig } from '@playwright/test'

// e2e 直连真实后端，聚合/显示开关等用例会改动真实配置（清空聚合组、强制目录可见）。
// 整套用例开始前快照目录与聚合组状态，globalTeardown 负责还原；
// 快照放在系统临时目录：globalSetup 与 globalTeardown 是两个独立进程，靠文件传递。
export const SNAPSHOT_FILE = join(tmpdir(), 'fongmi-web-e2e-data-snapshot.json')

export default async function globalSetup(config: FullConfig) {
  const base = config.use?.baseURL || 'http://127.0.0.1:8000'
  let dirs: unknown
  let groups: unknown
  try {
    dirs = await (await fetch(`${base}/api/local/dirs`)).json()
    groups = await (await fetch(`${base}/api/local/groups`)).json()
  } catch (e: any) {
    throw new Error(`e2e 需要后端已运行于 ${base}（快照真实数据失败）：${e.message}`)
  }
  writeFileSync(SNAPSHOT_FILE, JSON.stringify({ dirs, groups }, null, 2))
}
