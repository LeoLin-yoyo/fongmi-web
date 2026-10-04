import { readFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import type { FullConfig } from '@playwright/test'
import { SNAPSHOT_FILE } from './global-setup'

// 还原 globalSetup 快照的真实数据（目录顺序/显示状态 + 聚合组）。
// 任何还原失败都抛错让整套 e2e 标记失败，避免静默吞掉用户数据丢失。
export default async function globalTeardown(config: FullConfig) {
  const base = config.use?.baseURL || 'http://127.0.0.1:8000'
  let snap: { dirs: any[]; groups: any[] }
  try {
    snap = JSON.parse(readFileSync(SNAPSHOT_FILE, 'utf-8'))
  } catch {
    console.warn('[e2e-teardown] 未找到数据快照，跳过还原')
    return
  }

  const api = async (p: string, init?: RequestInit) => {
    const res = await fetch(`${base}${p}`, init)
    if (!res.ok) throw new Error(`${init?.method || 'GET'} ${p} -> ${res.status} ${await res.text()}`)
    return res.json()
  }
  const json = (body: unknown): RequestInit => ({
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const errors: string[] = []

  // 目录顺序与显示状态（顺序校验要求 id 集合与现有目录一致，缺了就跳过顺序还原）
  try {
    const curDirs: any[] = await api('/api/local/dirs')
    const ids: number[] = snap.dirs.map(d => d.id)
    if (ids.length && ids.every(id => curDirs.some(d => d.id === id))) {
      await api('/api/local/dirs/order', { method: 'PUT', ...json({ ids }) })
    }
    for (const d of snap.dirs) {
      await api(`/api/local/dirs/${d.id}/visible`, { method: 'PATCH', ...json({ visible: !!d.visible }) })
    }
  } catch (e: any) {
    errors.push(`目录状态还原失败: ${e.message}`)
  }

  // 聚合组：全删后按快照重建（组 id 会变，引用方都是按 id 动态读取，无外部持久引用）
  try {
    const curGroups: any[] = await api('/api/local/groups')
    for (const g of curGroups) {
      await api(`/api/local/groups/${g.id}`, { method: 'DELETE' })
    }
    const curDirIds = new Set<number>(((await api('/api/local/dirs')) as any[]).map(d => d.id))
    for (const g of snap.groups) {
      const dirIds = (g.dir_ids || []).filter((id: number) => curDirIds.has(id))
      if (dirIds.length >= 2) {
        await api('/api/local/groups', { method: 'POST', ...json({ name: g.name, dir_ids: dirIds }) })
      }
    }
  } catch (e: any) {
    errors.push(`聚合组还原失败: ${e.message}`)
  }

  if (errors.length) {
    throw new Error(`[e2e-teardown] 真实数据还原失败，请手工检查：\n${errors.join('\n')}`)
  }
  console.log('[e2e-teardown] 已按快照还原目录顺序/显示状态与聚合组')
}
